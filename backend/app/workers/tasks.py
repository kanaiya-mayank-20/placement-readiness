"""Background pipelines.

- jd_pipeline:        raw JD -> structured data -> embedding -> saved
- analysis_pipeline:  resume + GitHub -> candidate profile -> retrieve -> score -> explain
"""

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Optional

from app.core.config import settings
from app.core.logging import get_logger
from app.db.database import SessionLocal
from app.db.models import Analysis, CandidateProfile, GithubProfile, MatchResult, Resume
from app.services.github.analyzer import analyze_github
from app.services.jd.jd_ingest import process_jd
from app.services.llm.client import llm
from app.services.matching.profile import build_candidate_profile
from app.services.matching.reranker import apply_adjustment, explain, template_explanation
from app.services.matching.retrieval import hybrid_retrieve
from app.services.matching.scoring import score_jd
from app.services.resume.pdf_extract import extract_text
from app.services.resume.resume_parser import parse_resume
from app.workers.runner import runner

log = get_logger("workers.tasks")

_progress_lock = threading.Lock()


def _update_progress(analysis_id: int, **steps) -> None:
    with _progress_lock:
        db = SessionLocal()
        try:
            analysis = db.get(Analysis, analysis_id)
            if analysis is None:
                return
            progress = dict(analysis.progress or {})
            progress.update(steps)
            analysis.progress = progress
            db.commit()
        finally:
            db.close()


def _set_status(analysis_id: int, status: str, error: Optional[str] = None) -> None:
    db = SessionLocal()
    try:
        analysis = db.get(Analysis, analysis_id)
        if analysis is None:
            return
        analysis.status = status
        analysis.error = error
        if status in ("done", "failed"):
            analysis.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.commit()
    finally:
        db.close()


def handle_jd_job(payload: dict) -> None:
    jd_id = int(payload["jd_id"])
    db = SessionLocal()
    try:
        process_jd(db, jd_id)
    finally:
        db.close()


def _resume_step(analysis_id: int) -> dict:
    db = SessionLocal()
    try:
        analysis = db.get(Analysis, analysis_id)
        path = analysis.resume_path if analysis else ""
        filename = analysis.resume_filename if analysis else ""
        _update_progress(analysis_id, resume="running")
        text = extract_text(path) if path else ""
        profile, strategy = parse_resume(text, filename)
        existing = db.query(Resume).filter(Resume.analysis_id == analysis_id).first()
        if existing:
            db.delete(existing)
        db.add(
            Resume(
                analysis_id=analysis_id,
                raw_text=text[:200000],
                parsed_json=profile,
                parser_version=strategy,
            )
        )
        db.commit()
        _update_progress(analysis_id, resume="done")
        return {"text": text, "profile": profile, "strategy": strategy, "error": None}
    except Exception as exc:
        log.exception("resume step failed for analysis %s", analysis_id)
        _update_progress(analysis_id, resume="failed")
        return {"text": "", "profile": {}, "strategy": "none", "error": str(exc)}
    finally:
        db.close()


def _github_step(analysis_id: int) -> dict:
    db = SessionLocal()
    try:
        analysis = db.get(Analysis, analysis_id)
        username = analysis.github_username if analysis else ""
        if not username:
            _update_progress(analysis_id, github="skipped")
            return {"derived": None, "raw": {}, "error": None, "skipped": True}
        _update_progress(analysis_id, github="running")
        result = analyze_github(username)
        existing = db.query(GithubProfile).filter(GithubProfile.analysis_id == analysis_id).first()
        if existing:
            db.delete(existing)
        db.add(
            GithubProfile(
                analysis_id=analysis_id,
                username=username,
                raw_json=result.get("raw") or {},
                derived_json=result.get("derived") or {},
            )
        )
        db.commit()
        _update_progress(analysis_id, github="done")
        return {"derived": result.get("derived"), "raw": result.get("raw"), "error": None, "skipped": False}
    except Exception as exc:
        log.warning("github step failed for analysis %s: %s", analysis_id, exc)
        _update_progress(analysis_id, github="failed")
        return {"derived": None, "raw": {}, "error": str(exc), "skipped": False}
    finally:
        db.close()


def handle_analysis_job(payload: dict) -> None:
    analysis_id = int(payload["analysis_id"])
    _set_status(analysis_id, "running")
    try:
        # idempotency: clear previous outputs of this analysis
        db = SessionLocal()
        try:
            for model in (Resume, GithubProfile, CandidateProfile, MatchResult):
                db.query(model).filter(model.analysis_id == analysis_id).delete()
            analysis = db.get(Analysis, analysis_id)
            if analysis is None:
                raise ValueError(f"analysis {analysis_id} not found")
            role = analysis.role
            company_id = analysis.target_company_id
            resume_path = analysis.resume_path
        finally:
            db.close()

        if not resume_path:
            raise ValueError("no resume file attached to this analysis")

        resume_result: dict = {}
        github_result: dict = {}
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = {
                pool.submit(_resume_step, analysis_id): "resume",
                pool.submit(_github_step, analysis_id): "github",
            }
            for future in as_completed(futures):
                result = future.result()
                if futures[future] == "resume":
                    resume_result = result
                else:
                    github_result = result

        warnings: list[str] = []
        if resume_result.get("error"):
            raise RuntimeError(f"resume parsing failed: {resume_result['error']}")
        if github_result.get("error"):
            warnings.append(f"GitHub analysis failed ({github_result['error']}) - scores use resume only.")
        if github_result.get("skipped"):
            warnings.append("No GitHub URL provided - scores use resume only.")

        _update_progress(analysis_id, profile="running")
        profile = build_candidate_profile(
            resume_result["profile"], resume_result["text"], github_result.get("derived"), role
        )
        profile["embedding"] = llm.embed_or_hash(profile["summary_text"])

        db = SessionLocal()
        try:
            db.add(CandidateProfile(analysis_id=analysis_id, profile_json=profile,
                                    embedding_json=profile["embedding"]))
            analysis = db.get(Analysis, analysis_id)
            analysis.warnings = warnings
            db.commit()
        finally:
            db.close()
        _update_progress(analysis_id, profile="done", matching="running")

        db = SessionLocal()
        try:
            candidates = hybrid_retrieve(db, profile, role, company_id=company_id)
            scored: list[dict] = []
            for item in candidates:
                jd = item["jd"]
                struct = jd.structured_json or {}
                jd_dict = {
                    "id": jd.id,
                    "company_id": jd.company_id,
                    "company": jd.company.name if jd.company else "",
                    "title": jd.title,
                    "role_family": jd.role_family,
                    "seniority": jd.seniority,
                    "min_years": jd.min_years,
                    "must_have": jd.must_have or [],
                    "nice_to_have": jd.nice_to_have or [],
                    "structured": struct,
                    "text": struct.get("summary_text") or jd.raw_text[:1200],
                }
                scores = score_jd(profile, jd_dict, role)
                scores["retrieval_score"] = item["retrieval_score"]
                scored.append({"jd": jd_dict, "scores": scores})

            scored.sort(key=lambda s: s["scores"]["overall_score"], reverse=True)
            top_k = max(1, settings.EXPLAIN_TOP_K)
            _update_progress(analysis_id, matching="done", explanation="running")
            for entry in scored[:top_k]:
                try:
                    explanation = explain(profile, entry["jd"], entry["scores"])
                    entry["scores"]["overall_score"] = apply_adjustment(
                        entry["scores"]["overall_score"], explanation
                    )
                    entry["scores"]["breakdown"]["score_adjustment"] = explanation.get("score_adjustment", 0)
                    entry["explanation"] = explanation
                except Exception as exc:
                    log.warning("explanation failed for jd %s: %s", entry["jd"]["id"], exc)
                    entry["explanation"] = {"summary": "", "source": "none"}
            for entry in scored[top_k:]:
                entry["explanation"] = template_explanation(profile, entry["jd"], entry["scores"])

            scored.sort(key=lambda s: s["scores"]["overall_score"], reverse=True)
            for rank, entry in enumerate(scored, start=1):
                scores = entry["scores"]
                db.add(
                    MatchResult(
                        analysis_id=analysis_id,
                        jd_id=entry["jd"]["id"],
                        company_id=entry["jd"]["company_id"],
                        overall_score=scores["overall_score"],
                        resume_score=scores["resume_score"],
                        github_score=scores["github_score"] if scores["github_score"] is not None else 0.0,
                        breakdown_json=scores["breakdown"],
                        explanation_json=entry["explanation"],
                        rank=rank,
                    )
                )
            db.commit()
        finally:
            db.close()

        _update_progress(analysis_id, matching="done", explanation="done")
        _set_status(analysis_id, "done")
        log.info("analysis %s done - %d matches", analysis_id, len(scored))
    except Exception as exc:
        log.exception("analysis %s failed", analysis_id)
        _set_status(analysis_id, "failed", str(exc)[:2000])


def register_handlers() -> None:
    runner.register("jd_pipeline", handle_jd_job)
    runner.register("analysis_pipeline", handle_analysis_job)

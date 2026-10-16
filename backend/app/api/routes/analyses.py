"""Student flow: run an analysis, read the matches, score / readiness for one company."""

import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_owned_analysis
from app.api.schemas import FeedbackIn, ReadinessIn, ScoreIn
from app.core.config import ROLES, UPLOAD_DIR, settings
from app.db.database import get_db
from app.db.models import (
    Analysis,
    CandidateProfile,
    Company,
    Feedback,
    JobDescription,
    MatchResult,
    ReadinessReport,
)
from app.db.repositories import company_summary
from app.services.matching.retrieval import load_ready_jds
from app.services.matching.scoring import score_jd
from app.services.readiness.gap_analysis import build_gap_report
from app.services.readiness.report_generator import build_report
from app.services.resume.pdf_extract import is_pdf
from app.workers.runner import runner

router = APIRouter(prefix="/api", tags=["analyses"], dependencies=[Depends(get_current_user)])

GITHUB_USER_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$")


def _username_from_url(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    value = value.rstrip("/").split("?")[0].split("#")[0]
    if "github.com" in value.lower():
        parts = value.split("github.com", 1)[-1].strip("/").split("/")
        candidate = parts[0] if parts else ""
    else:
        candidate = value.strip("@/")
    candidate = candidate.strip("/")
    return candidate if GITHUB_USER_RE.match(candidate) else ""


def _jd_dict(jd: JobDescription) -> dict:
    struct = jd.structured_json or {}
    return {
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
        "text": struct.get("summary_text") or (jd.raw_text or "")[:1200],
    }


def _load_profile(db: Session, analysis: Analysis) -> dict:
    row = db.scalar(select(CandidateProfile).where(CandidateProfile.analysis_id == analysis.id))
    if row is None or not row.profile_json:
        raise HTTPException(status_code=409, detail="Analysis is not finished yet")
    return row.profile_json


def _require_done(analysis: Analysis) -> None:
    if analysis.status != "done":
        raise HTTPException(status_code=409, detail=f"Analysis status is '{analysis.status}', waiting for it to finish")


def _scores_for(db: Session, profile: dict, analysis: Analysis, jd: JobDescription) -> dict:
    return score_jd(profile, _jd_dict(jd), analysis.role)


def _rank_and_scores(db: Session, profile: dict, analysis: Analysis, target_jd_id: int) -> dict:
    """Score every JD in the analysis scope and return the target's rank."""
    jds = load_ready_jds(db, analysis.role, analysis.target_company_id)
    target_scores: Optional[dict] = None
    ranked: list[tuple[int, float]] = []
    for jd in jds:
        scores = score_jd(profile, _jd_dict(jd), analysis.role)
        ranked.append((jd.id, scores["overall_score"]))
        if jd.id == target_jd_id:
            target_scores = scores
    ranked.sort(key=lambda pair: pair[1], reverse=True)
    if target_scores is None:
        return {"rank": None, "total": len(ranked), "scores": None}
    rank = next((idx + 1 for idx, (jd_id, _) in enumerate(ranked) if jd_id == target_jd_id), None)
    return {"rank": rank, "total": len(ranked), "scores": target_scores}


def _match_item(result: MatchResult, jd: Optional[JobDescription]) -> dict:
    breakdown = result.breakdown_json or {}
    explanation = result.explanation_json or {}
    github_unavailable = breakdown.get("github") is None
    return {
        "rank": result.rank,
        "jd_id": result.jd_id,
        "company_id": result.company_id,
        "company": jd.company.name if jd and jd.company else None,
        "title": jd.title if jd else None,
        "role_family": jd.role_family if jd else None,
        "seniority": jd.seniority if jd else None,
        "min_years": jd.min_years if jd else None,
        "overall_score": result.overall_score,
        "resume_score": result.resume_score,
        "github_score": None if github_unavailable else result.github_score,
        "github_evidence": "low" if github_unavailable else "ok",
        "summary": explanation.get("summary", ""),
        "strengths": explanation.get("strengths", []),
        "gaps": explanation.get("gaps", []),
        "explanation_source": explanation.get("source", "template"),
    }


# ------------------------------------------------------------------ create


@router.post("/analyses", status_code=202)
async def create_analysis(
    role: str = Form(...),
    github_url: str = Form(""),
    company_id: Optional[int] = Form(None),
    resume: UploadFile = File(...),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    role = role.strip().lower()
    if role not in ROLES:
        raise HTTPException(status_code=400, detail=f"role must be one of {ROLES}")

    company = None
    if company_id is not None:
        company = db.get(Company, company_id)
        if company is None:
            raise HTTPException(status_code=404, detail="Company not found")
        if not load_ready_jds(db, role, company_id):
            raise HTTPException(
                status_code=400,
                detail=f"{company.name} has no processed job descriptions for this role.",
            )

    content = await resume.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty resume file")
    if len(content) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"Resume larger than {settings.MAX_UPLOAD_MB} MB")
    if not is_pdf(content):
        raise HTTPException(status_code=400, detail="Resume must be a PDF file")

    username = _username_from_url(github_url)
    if github_url.strip() and not username:
        raise HTTPException(status_code=400, detail="Could not read a GitHub username from github_url")

    filename = (resume.filename or "resume.pdf").replace("\\", "/").split("/")[-1]
    path = UPLOAD_DIR / f"{user.id}_{uuid.uuid4().hex}.pdf"
    path.write_bytes(content)

    analysis = Analysis(
        user_id=user.id,
        role=role,
        target_company_id=company_id,
        github_url=github_url.strip()[:512],
        github_username=username,
        resume_path=str(path),
        resume_filename=filename[:255],
        status="queued",
        progress={"resume": "queued", "github": "queued", "profile": "queued", "matching": "queued", "explanation": "queued"},
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    runner.submit("analysis_pipeline", {"analysis_id": analysis.id})

    return {
        "analysis_id": analysis.id,
        "status": analysis.status,
        "role": role,
        "company_id": company_id,
        "company": company.name if company else None,
        "github_username": username,
        "top_n_companies": settings.TOP_N_COMPANIES,
    }


# ------------------------------------------------------------------ read


@router.get("/analyses")
def list_my_analyses(user=Depends(get_current_user), db: Session = Depends(get_db)):
    rows = list(db.scalars(select(Analysis).where(Analysis.user_id == user.id).order_by(Analysis.id.desc())))
    return {
        "items": [
            {
                "id": a.id,
                "role": a.role,
                "company_id": a.target_company_id,
                "company": a.target_company.name if a.target_company else None,
                "github_username": a.github_username,
                "resume_filename": a.resume_filename,
                "status": a.status,
                "progress": a.progress,
                "warnings": a.warnings,
                "error": a.error,
                "created_at": a.created_at.isoformat() if a.created_at else None,
                "finished_at": a.finished_at.isoformat() if a.finished_at else None,
            }
            for a in rows
        ]
    }


@router.get("/analyses/{analysis_id}")
def get_analysis(analysis_id: int, user=Depends(get_current_user), db: Session = Depends(get_db)):
    analysis = get_owned_analysis(analysis_id, user, db)
    matches = db.scalar(
        select(MatchResult.id).where(MatchResult.analysis_id == analysis_id).limit(1)
    )
    return {
        "analysis_id": analysis.id,
        "status": analysis.status,
        "role": analysis.role,
        "company_id": analysis.target_company_id,
        "company": analysis.target_company.name if analysis.target_company else None,
        "github_username": analysis.github_username,
        "resume_filename": analysis.resume_filename,
        "progress": analysis.progress,
        "warnings": analysis.warnings,
        "error": analysis.error,
        "has_results": matches is not None,
        "top_n_companies": settings.TOP_N_COMPANIES,
        "created_at": analysis.created_at.isoformat() if analysis.created_at else None,
        "finished_at": analysis.finished_at.isoformat() if analysis.finished_at else None,
    }


@router.get("/analyses/{analysis_id}/matches")
def get_matches(analysis_id: int, user=Depends(get_current_user), db: Session = Depends(get_db)):
    analysis = get_owned_analysis(analysis_id, user, db)
    _require_done(analysis)
    results = list(
        db.scalars(
            select(MatchResult)
            .where(MatchResult.analysis_id == analysis_id)
            .order_by(MatchResult.rank)
        )
    )
    if not results:
        raise HTTPException(status_code=404, detail="No matches were produced for this analysis")

    top_n = max(1, settings.TOP_N_COMPANIES)
    top = results[:top_n]
    jds = {
        jd.id: jd
        for jd in db.scalars(select(JobDescription).where(JobDescription.id.in_([r.jd_id for r in top])))
    }
    return {
        "analysis_id": analysis_id,
        "role": analysis.role,
        "company_id": analysis.target_company_id,
        "company": analysis.target_company.name if analysis.target_company else None,
        "top_n": len(top),
        "total_scored": len(results),
        "items": [_match_item(r, jds.get(r.jd_id)) for r in top],
    }


@router.get("/analyses/{analysis_id}/matches/{jd_id}")
def get_match_detail(analysis_id: int, jd_id: int, user=Depends(get_current_user), db: Session = Depends(get_db)):
    analysis = get_owned_analysis(analysis_id, user, db)
    _require_done(analysis)
    jd = db.get(JobDescription, jd_id)
    if jd is None or not jd.is_active:
        raise HTTPException(status_code=404, detail="JD not found")
    if analysis.target_company_id is not None and jd.company_id != analysis.target_company_id:
        raise HTTPException(status_code=404, detail="JD not found")

    stored = db.scalar(
        select(MatchResult).where(MatchResult.analysis_id == analysis_id, MatchResult.jd_id == jd_id)
    )
    profile = _load_profile(db, analysis)

    if stored is not None:
        scores = {
            "resume_score": stored.resume_score,
            "github_score": None if (stored.breakdown_json or {}).get("github") is None else stored.github_score,
            "overall_score": stored.overall_score,
            "breakdown": stored.breakdown_json,
            "explanation": stored.explanation_json,
        }
        rank = stored.rank
        total = db.scalar(
            select(func.count(MatchResult.id)).where(MatchResult.analysis_id == analysis_id)
        )
    else:
        computed = _scores_for(db, profile, analysis, jd)
        scores = {
            "resume_score": computed["resume_score"],
            "github_score": computed["github_score"],
            "overall_score": computed["overall_score"],
            "breakdown": computed["breakdown"],
            "explanation": {"summary": "Scored on demand (outside the ranked list).", "source": "computed"},
        }
        ranked = _rank_and_scores(db, profile, analysis, jd.id)
        rank = ranked["rank"]
        total = ranked["total"]

    return {
        "analysis_id": analysis_id,
        "jd_id": jd_id,
        "company": company_summary(jd.company) if jd.company else None,
        "job": _jd_dict(jd),
        "rank": rank,
        "ranked_pool_size": total,
        "resume_score": scores["resume_score"],
        "github_score": scores["github_score"],
        "overall_score": scores["overall_score"],
        "breakdown": scores["breakdown"],
        "explanation": scores["explanation"],
    }


@router.post("/analyses/{analysis_id}/score")
def score_specific_company(
    analysis_id: int,
    body: ScoreIn,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Check the score for one specific company against ALL available companies."""
    analysis = get_owned_analysis(analysis_id, user, db)
    _require_done(analysis)
    jd = db.get(JobDescription, body.jd_id)
    if jd is None or not jd.is_active or jd.status != "ready":
        raise HTTPException(status_code=404, detail="JD not found or not processed yet")
    if analysis.target_company_id is not None and jd.company_id != analysis.target_company_id:
        raise HTTPException(status_code=404, detail="JD not found")

    profile = _load_profile(db, analysis)
    ranked = _rank_and_scores(db, profile, analysis, jd.id)
    scores = ranked["scores"]

    stored = db.scalar(
        select(MatchResult).where(MatchResult.analysis_id == analysis_id, MatchResult.jd_id == jd.id)
    )
    skill_info = scores["breakdown"]["skill_match"]

    return {
        "analysis_id": analysis_id,
        "jd_id": jd.id,
        "company": jd.company.name if jd.company else None,
        "title": jd.title,
        "role_family": jd.role_family,
        "seniority": jd.seniority,
        "rank": ranked["rank"],
        "total_companies_scored": ranked["total"],
        "in_ranked_results": stored is not None,
        "resume_score": scores["resume_score"],
        "github_score": scores["github_score"],
        "overall_score": scores["overall_score"],
        "breakdown": scores["breakdown"],
        "matched_skills": skill_info["matched"],
        "missing_must": skill_info["missing_must"],
        "missing_nice": skill_info["missing_nice"],
        "partial_skills": skill_info["partial"],
    }


@router.post("/analyses/{analysis_id}/readiness")
def readiness_for_company(
    analysis_id: int,
    body: ReadinessIn,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Qualitative report only: strengths, suggestions to improve, next steps.

    No numeric score is returned to the student on purpose.
    """
    analysis = get_owned_analysis(analysis_id, user, db)
    _require_done(analysis)
    jd = db.get(JobDescription, body.jd_id)
    if jd is None or not jd.is_active or jd.status != "ready":
        raise HTTPException(status_code=404, detail="JD not found or not processed yet")
    if analysis.target_company_id is not None and jd.company_id != analysis.target_company_id:
        raise HTTPException(status_code=404, detail="JD not found")

    profile = _load_profile(db, analysis)
    stored = db.scalar(
        select(MatchResult).where(MatchResult.analysis_id == analysis_id, MatchResult.jd_id == jd.id)
    )
    if stored is not None:
        scores = {
            "resume_score": stored.resume_score,
            "github_score": stored.github_score,
            "overall_score": stored.overall_score,
            "breakdown": stored.breakdown_json or {},
        }
    else:
        scores = _scores_for(db, profile, analysis, jd)

    jd_dict = _jd_dict(jd)
    gap_report = build_gap_report(profile, jd_dict, scores, analysis.role)
    report = build_report(profile, jd_dict, gap_report)
    report.update(
        {
            "analysis_id": analysis_id,
            "jd_id": jd.id,
            "company": jd.company.name if jd.company else None,
            "job_title": jd.title,
            "role_family": jd.role_family,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    )

    db.add(
        ReadinessReport(
            analysis_id=analysis_id,
            jd_id=jd.id,
            report_json={
                **report,
                "internal_score": gap_report["internal_score"],
            },
        )
    )
    db.commit()
    return report


@router.post("/analyses/{analysis_id}/feedback")
def leave_feedback(
    analysis_id: int,
    body: FeedbackIn,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    analysis = get_owned_analysis(analysis_id, user, db)
    if body.analysis_id != analysis_id:
        raise HTTPException(status_code=400, detail="analysis_id mismatch")
    db.add(
        Feedback(
            analysis_id=analysis.id,
            jd_id=body.jd_id,
            helpful=body.helpful,
            comment=(body.comment or "")[:1000],
        )
    )
    db.commit()
    return {"saved": True}

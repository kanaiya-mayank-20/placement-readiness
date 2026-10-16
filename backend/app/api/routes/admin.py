"""Admin endpoints: upload JDs, watch the pipeline, inspect companies."""

import os
import re

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.api.schemas import JDCreateIn, JDUpdateIn
from app.core.config import ROLES, settings
from app.db.database import get_db
from app.db.models import Analysis, Company, Job, JobDescription, MatchResult, User
from app.db.repositories import company_summary, get_or_create_company
from app.services.jd.jd_extractor import extract_structured_jd
from app.services.resume.pdf_extract import extract_text, is_pdf
from app.workers.runner import runner

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


def _jd_out(jd: JobDescription) -> dict:
    struct = jd.structured_json or {}
    return {
        "id": jd.id,
        "company_id": jd.company_id,
        "company": jd.company.name if jd.company else None,
        "title": jd.title,
        "role_family": jd.role_family,
        "seniority": jd.seniority,
        "min_years": jd.min_years,
        "must_have": jd.must_have or [],
        "nice_to_have": jd.nice_to_have or [],
        "status": jd.status,
        "error": jd.error,
        "is_active": jd.is_active,
        "source": jd.source,
        "parser": struct.get("parser"),
        "responsibilities": struct.get("responsibilities", []),
        "education": struct.get("education", ""),
        "location": struct.get("location", ""),
        "remote": struct.get("remote", ""),
        "industry": struct.get("industry", ""),
        "employment_type": struct.get("employment_type", ""),
        "compensation": struct.get("compensation", ""),
        "work_mode": struct.get("work_mode", ""),
        "duration": struct.get("duration", ""),
        "conversion": struct.get("conversion", ""),
        "eligibility": struct.get("eligibility", ""),
        "selection_process": struct.get("selection_process", []),
        "perks": struct.get("perks", []),
        "about": struct.get("about", ""),
        "raw_text_preview": (jd.raw_text or "")[:400],
        "created_at": jd.created_at.isoformat() if jd.created_at else None,
        "updated_at": jd.updated_at.isoformat() if jd.updated_at else None,
    }


def _create_jd(
    db: Session,
    company_name: str,
    title: str,
    raw_text: str,
    role_family: str | None = None,
    website: str | None = None,
    location: str | None = None,
    industry: str | None = None,
    source: str = "admin_upload",
    structured: dict | None = None,
) -> JobDescription:
    company = get_or_create_company(
        db, company_name, industry=industry, website=website, location=location
    )
    overrides = {k: v for k, v in (structured or {}).items() if v not in (None, "", [], {})}
    jd = JobDescription(
        company_id=company.id,
        title=(title or "").strip()[:255],
        raw_text=raw_text,
        role_family=role_family if role_family in ROLES else None,
        status="pending",
        source=source,
        structured_json={"_admin_overrides": overrides} if overrides else None,
    )
    db.add(jd)
    db.commit()
    db.refresh(jd)
    runner.submit("jd_pipeline", {"jd_id": jd.id})
    return jd


@router.post("/jds", status_code=202)
def create_jd(body: JDCreateIn, db: Session = Depends(get_db)):
    jd = _create_jd(
        db,
        company_name=body.company_name,
        title=body.title,
        raw_text=body.raw_text,
        role_family=body.role_family,
        website=body.website,
        location=body.location,
        industry=body.industry,
        structured={
            "employment_type": body.employment_type,
            "compensation": body.compensation,
            "work_mode": body.work_mode,
            "duration": body.duration,
            "conversion": body.conversion,
            "eligibility": body.eligibility,
            "selection_process": body.selection_process or [],
            "perks": body.perks or [],
            "about": body.about,
        },
    )
    return {"jd_id": jd.id, "status": jd.status, "job_queued": True, "detail": _jd_out(jd)}


def _extract_file_text(file: UploadFile) -> tuple[str, str]:
    content = file.file.read() if hasattr(file.file, "read") else None
    if content is None:
        raise HTTPException(status_code=400, detail="Could not read file")
    if len(content) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File larger than {settings.MAX_UPLOAD_MB} MB")
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    name = (file.filename or "jd.txt").lower()
    text = ""
    if name.endswith(".pdf") or is_pdf(content):
        import uuid

        from app.core.config import UPLOAD_DIR

        tmp = str(UPLOAD_DIR / f"jd_{uuid.uuid4().hex}.pdf")
        with open(tmp, "wb") as fh:
            fh.write(content)
        try:
            text = extract_text(tmp)
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
    else:
        try:
            text = content.decode("utf-8", errors="replace")
        except Exception:
            raise HTTPException(status_code=400, detail="Unsupported file encoding")

    text = (text or "").strip()
    if len(text) < 30:
        raise HTTPException(status_code=400, detail="Could not extract enough text from the file")
    return text, (file.filename or "jd.txt")


def _company_hint_from_filename(filename: str) -> str:
    stem = re.sub(r"\.(pdf|txt|docx?)$", "", filename or "", flags=re.I)
    parts = re.split(r"[\s\-–—_/|]+", stem)
    hint = " ".join(
        p
        for p in parts
        if p.lower()
        not in {
            "job", "jobs", "jd", "jds", "description", "descriptions", "campus", "recruitment",
            "internship", "internships", "intern", "details", "opportunity", "summer", "2027",
            "for", "the", "pdf", "profile", "template", "copy", "interim",
        }
        and not p.isdigit()
    ).strip()
    return hint[:120]


@router.post("/jds/parse")
async def parse_jd_file(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Extract a JD from an uploaded PDF/text file WITHOUT saving anything."""
    text, filename = _extract_file_text(file)
    hints = {"company": _company_hint_from_filename(filename)}
    struct, strategy = extract_structured_jd(text, hints)
    return {"filename": filename, "raw_text": text, "structured": struct, "strategy": strategy, "saved": False}


@router.post("/jds/upload", status_code=202)
async def upload_jd_file(
    file: UploadFile = File(...),
    company_name: str = Form(""),
    title: str = Form(""),
    role_family: str = Form(""),
    website: str = Form(""),
    location: str = Form(""),
    industry: str = Form(""),
    db: Session = Depends(get_db),
):
    text, filename = _extract_file_text(file)
    company_name = (company_name or "").strip()
    if not company_name:
        company_name = _company_hint_from_filename(filename) or "Untitled Company"

    jd = _create_jd(
        db,
        company_name=company_name,
        title=title,
        raw_text=text,
        role_family=role_family or None,
        website=website or None,
        location=location or None,
        industry=industry or None,
        source="admin_file_upload",
    )
    return {"jd_id": jd.id, "status": jd.status, "job_queued": True, "filename": filename}


@router.get("/jds")
def list_jds(
    status: str | None = None,
    role: str | None = None,
    company_id: int | None = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    stmt = select(JobDescription).order_by(JobDescription.id.desc())
    if status:
        stmt = stmt.where(JobDescription.status == status)
    if role:
        stmt = stmt.where(JobDescription.role_family == role)
    if company_id:
        stmt = stmt.where(JobDescription.company_id == company_id)
    jds = list(db.scalars(stmt.offset(offset).limit(min(limit, 500))))
    total = db.scalar(select(func.count(JobDescription.id)))
    return {"total": total, "items": [_jd_out(j) for j in jds]}


@router.get("/jds/{jd_id}")
def get_jd(jd_id: int, db: Session = Depends(get_db)):
    jd = db.get(JobDescription, jd_id)
    if jd is None:
        raise HTTPException(status_code=404, detail="JD not found")
    out = _jd_out(jd)
    out["raw_text"] = jd.raw_text
    out["structured"] = jd.structured_json
    out["company_details"] = company_summary(jd.company, [jd]) if jd.company else None
    return out


@router.put("/jds/{jd_id}")
def update_jd(jd_id: int, body: JDUpdateIn, db: Session = Depends(get_db)):
    jd = db.get(JobDescription, jd_id)
    if jd is None:
        raise HTTPException(status_code=404, detail="JD not found")
    changed = False
    if body.raw_text is not None and body.raw_text.strip():
        jd.raw_text = body.raw_text
        jd.status = "pending"
        changed = True
    if body.title is not None:
        jd.title = body.title.strip()[:255]
        changed = True
    if body.role_family is not None:
        jd.role_family = body.role_family if body.role_family in ROLES else None
        changed = True
    db.commit()
    if changed:
        runner.submit("jd_pipeline", {"jd_id": jd.id})
    db.refresh(jd)
    return {"jd_id": jd.id, "status": jd.status, "reprocessed": changed}


@router.post("/jds/{jd_id}/reprocess", status_code=202)
def reprocess_jd(jd_id: int, db: Session = Depends(get_db)):
    jd = db.get(JobDescription, jd_id)
    if jd is None:
        raise HTTPException(status_code=404, detail="JD not found")
    jd.status = "pending"
    jd.error = None
    db.commit()
    job_id = runner.submit("jd_pipeline", {"jd_id": jd.id})
    return {"jd_id": jd.id, "job_id": job_id, "status": "pending"}


@router.delete("/jds/{jd_id}")
def delete_jd(jd_id: int, db: Session = Depends(get_db)):
    jd = db.get(JobDescription, jd_id)
    if jd is None:
        raise HTTPException(status_code=404, detail="JD not found")
    references = db.scalar(select(func.count(MatchResult.id)).where(MatchResult.jd_id == jd_id)) or 0
    if references:
        jd.is_active = False
        jd.status = "archived"
        db.commit()
        return {"jd_id": jd_id, "deleted": False, "archived": True, "reason": "referenced by match results"}
    db.delete(jd)
    db.commit()
    return {"jd_id": jd_id, "deleted": True}


@router.get("/companies")
def list_companies(db: Session = Depends(get_db)):
    companies = list(db.scalars(select(Company).order_by(Company.name)))
    return {"total": len(companies), "items": [company_summary(c) for c in companies]}


@router.get("/companies/{company_id}")
def get_company(company_id: int, db: Session = Depends(get_db)):
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    summary = company_summary(company)
    summary["job_descriptions"] = [
        _jd_out(jd) for jd in company.job_descriptions if jd.is_active
    ]
    return summary


@router.get("/analyses")
def list_analyses(limit: int = 100, offset: int = 0, db: Session = Depends(get_db)):
    rows = list(
        db.scalars(select(Analysis).order_by(Analysis.id.desc()).offset(offset).limit(min(limit, 500))))
    users = {u.id: u.email for u in db.scalars(select(User))}
    return {
        "total": db.scalar(select(func.count(Analysis.id))),
        "items": [
            {
                "id": a.id,
                "user_id": a.user_id,
                "user_email": users.get(a.user_id),
                "role": a.role,
                "github_username": a.github_username,
                "status": a.status,
                "progress": a.progress,
                "warnings": a.warnings,
                "error": a.error,
                "created_at": a.created_at.isoformat() if a.created_at else None,
                "finished_at": a.finished_at.isoformat() if a.finished_at else None,
            }
            for a in rows
        ],
    }


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    by_status = dict(
        db.execute(select(JobDescription.status, func.count()).group_by(JobDescription.status)).all()
    )
    analysis_status = dict(
        db.execute(select(Analysis.status, func.count()).group_by(Analysis.status)).all()
    )
    jobs = dict(db.execute(select(Job.status, func.count()).group_by(Job.status)).all())
    return {
        "companies": db.scalar(select(func.count(func.distinct(JobDescription.company_id)))),
        "job_descriptions": db.scalar(select(func.count(JobDescription.id))),
        "jd_by_status": by_status,
        "users": db.scalar(select(func.count(User.id))),
        "analyses": db.scalar(select(func.count(Analysis.id))),
        "analyses_by_status": analysis_status,
        "match_results": db.scalar(select(func.count(MatchResult.id))),
        "jobs": jobs,
        "config": {
            "top_n_companies": settings.TOP_N_COMPANIES,
            "candidate_pool_size": settings.CANDIDATE_POOL_SIZE,
            "explain_top_k": settings.EXPLAIN_TOP_K,
            "llm_enabled": bool(settings.GEMINI_API_KEY),
            "github_token_set": bool(settings.GITHUB_TOKEN),
        },
    }


@router.get("/jobs")
def list_jobs(limit: int = 50, db: Session = Depends(get_db)):
    rows = list(db.scalars(select(Job).order_by(Job.id.desc()).limit(min(limit, 200))))
    return {
        "items": [
            {
                "id": j.id,
                "kind": j.kind,
                "status": j.status,
                "attempts": j.attempts,
                "error": (j.error or "")[:400],
                "payload": j.payload_json,
                "created_at": j.created_at.isoformat() if j.created_at else None,
                "updated_at": j.updated_at.isoformat() if j.updated_at else None,
            }
            for j in rows
        ]
    }

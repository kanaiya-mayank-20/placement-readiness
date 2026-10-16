"""Student-facing browse endpoints: all companies and their structured JDs."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db
from app.db.models import Company, JobDescription
from app.db.repositories import company_summary

router = APIRouter(prefix="/api", tags=["companies"], dependencies=[Depends(get_current_user)])


def _jd_brief(jd: JobDescription) -> dict:
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
        "location": struct.get("location", ""),
        "remote": struct.get("remote", ""),
        "responsibilities": (struct.get("responsibilities") or [])[:6],
    }


@router.get("/companies")
def list_companies(
    role: str | None = Query(default=None),
    q: str | None = Query(default=None, max_length=100),
    db: Session = Depends(get_db),
):
    stmt = select(Company).order_by(Company.name)
    companies = list(db.scalars(stmt))
    items = []
    for company in companies:
        summary = company_summary(company)
        if role and role not in summary["roles"]:
            continue
        if q and q.lower() not in company.name.lower():
            continue
        items.append(summary)
    return {"total": len(items), "items": items}


@router.get("/companies/{company_id}")
def get_company(company_id: int, db: Session = Depends(get_db)):
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    summary = company_summary(company)
    summary["job_descriptions"] = [_jd_brief(jd) for jd in company.job_descriptions if jd.is_active]
    return summary


@router.get("/jds")
def list_jds(
    role: str | None = Query(default=None),
    company_id: int | None = Query(default=None),
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
):
    stmt = (
        select(JobDescription)
        .where(JobDescription.is_active.is_(True), JobDescription.status == "ready")
        .order_by(JobDescription.id.desc())
    )
    if role:
        stmt = stmt.where(JobDescription.role_family == role)
    if company_id:
        stmt = stmt.where(JobDescription.company_id == company_id)
    jds = list(db.scalars(stmt.limit(limit)))
    return {"total": len(jds), "items": [_jd_brief(j) for j in jds]}


@router.get("/jds/{jd_id}")
def get_jd(jd_id: int, db: Session = Depends(get_db)):
    jd = db.get(JobDescription, jd_id)
    if jd is None or not jd.is_active:
        raise HTTPException(status_code=404, detail="JD not found")
    out = _jd_brief(jd)
    struct = jd.structured_json or {}
    out["education"] = struct.get("education", "")
    out["industry"] = struct.get("industry", "")
    out["description_preview"] = (jd.raw_text or "")[:600]
    return out

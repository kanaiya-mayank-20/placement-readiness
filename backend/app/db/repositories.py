"""Small repository helpers shared by API routes and workers."""

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Company, JobDescription


def get_or_create_company(
    db: Session,
    name: str,
    industry: Optional[str] = None,
    website: Optional[str] = None,
    location: Optional[str] = None,
) -> Company:
    clean = (name or "").strip()
    company = db.scalar(select(Company).where(func.lower(Company.name) == clean.lower()))
    if company is None:
        company = Company(name=clean, industry=industry, website=website, location=location)
        db.add(company)
        db.flush()
    else:
        company.industry = industry or company.industry
        company.website = website or company.website
        company.location = location or company.location
    return company


def company_summary(company: Company, jds: Optional[list[JobDescription]] = None) -> dict:
    jds = jds if jds is not None else list(company.job_descriptions)
    active = [j for j in jds if j.is_active]
    ready = [j for j in active if j.status == "ready"]
    roles: dict[str, int] = {}
    must: dict[str, int] = {}
    nice: dict[str, int] = {}
    seniorities: dict[str, int] = {}
    locations: set[str] = set()
    for jd in ready:
        struct = jd.structured_json or {}
        rf = jd.role_family or struct.get("role_family") or "unknown"
        roles[rf] = roles.get(rf, 0) + 1
        for s in jd.must_have or []:
            must[s] = must.get(s, 0) + 1
        for s in jd.nice_to_have or []:
            nice[s] = nice.get(s, 0) + 1
        sen = jd.seniority or struct.get("seniority")
        if sen:
            seniorities[sen] = seniorities.get(sen, 0) + 1
        loc = struct.get("location")
        if loc:
            locations.add(str(loc))
    top_skills = sorted(
        {**{k: v * 3 for k, v in must.items()}, **nice}.items(), key=lambda kv: kv[1], reverse=True
    )
    return {
        "id": company.id,
        "name": company.name,
        "industry": company.industry,
        "website": company.website,
        "location": company.location,
        "size": company.size,
        "jd_count": len(active),
        "ready_jd_count": len(ready),
        "roles": roles,
        "seniority_mix": seniorities,
        "top_skills": [{"skill": k, "weight": round(v, 2)} for k, v in top_skills[:20]],
        "must_have_frequency": dict(sorted(must.items(), key=lambda kv: kv[1], reverse=True)),
        "nice_to_have_frequency": dict(sorted(nice.items(), key=lambda kv: kv[1], reverse=True)),
        "locations": sorted(locations),
    }

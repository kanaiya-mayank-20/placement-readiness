"""Offline JD pipeline: raw text -> clean -> extract -> normalise -> embed -> save."""

from typing import Optional

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models import JobDescription
from app.services.jd.jd_extractor import extract_structured_jd
from app.services.llm.client import llm

log = get_logger("jd.ingest")


def process_jd(db: Session, jd_id: int) -> JobDescription:
    jd = db.get(JobDescription, jd_id)
    if jd is None:
        raise ValueError(f"jd {jd_id} not found")

    jd.status = "processing"
    jd.error = None
    db.commit()

    try:
        hints = {
            "company": jd.company.name if jd.company else "",
            "title": jd.title,
            "role": jd.role_family,
            "industry": jd.company.industry if jd.company else None,
        }
        struct, strategy = extract_structured_jd(jd.raw_text or "", hints)

        previous = jd.structured_json or {}
        overrides = previous.get("_admin_overrides") or {}

        jd.title = struct.get("title") or jd.title
        jd.role_family = struct.get("role_family")
        jd.seniority = struct.get("seniority")
        jd.min_years = float(struct.get("min_years") or 0.0)
        jd.must_have = struct.get("must_have") or []
        jd.nice_to_have = struct.get("nice_to_have") or []
        merged = {**struct, "parser": strategy, **overrides, "_admin_overrides": overrides}
        jd.structured_json = merged
        jd.embedding_json = llm.embed_or_hash(struct.get("summary_text") or jd.raw_text or jd.title)
        jd.status = "ready"
        jd.error = None
        db.commit()
        log.info("JD %s processed (%s): %s | %s", jd.id, strategy, jd.role_family, jd.must_have)
        return jd
    except Exception as exc:
        db.rollback()
        jd = db.get(JobDescription, jd_id)
        if jd is not None:
            jd.status = "failed"
            jd.error = str(exc)[:2000]
            db.commit()
        log.exception("JD %s failed", jd_id)
        raise

"""Stage 0 + Stage 1 of the funnel: role filter then hybrid retrieval (RRF)."""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import JobDescription
from app.services.llm.client import cosine, hash_embed
from app.services.matching.scoring import load_weights, skill_match
from app.services.skills.normalizer import extract_known_skills

RELATED_ROLE_FILTER: dict[str, list[str]] = {
    "frontend": ["frontend", "fullstack"],
    "backend": ["backend", "fullstack"],
    "fullstack": ["fullstack", "frontend", "backend"],
    "data": ["data", "ml"],
    "ml": ["ml", "data"],
    "devops": ["devops", "backend", "fullstack"],
    "mobile": ["mobile", "frontend", "fullstack"],
}


def role_filter(role: str) -> list[str]:
    return RELATED_ROLE_FILTER.get(role, [role])


def load_ready_jds(
    db: Session, role: Optional[str] = None, company_id: Optional[int] = None
) -> list[JobDescription]:
    stmt = select(JobDescription).where(JobDescription.is_active.is_(True), JobDescription.status == "ready")
    if role:
        allowed = role_filter(role)
        stmt = stmt.where(JobDescription.role_family.in_(allowed))
    if company_id is not None:
        stmt = stmt.where(JobDescription.company_id == company_id)
    jds = list(db.scalars(stmt))
    if role and not jds and company_id is None:
        jds = list(
            db.scalars(
                select(JobDescription)
                .where(JobDescription.is_active.is_(True), JobDescription.status == "ready")
            )
        )
    return jds


def _jd_text(jd: JobDescription) -> str:
    struct = jd.structured_json or {}
    return struct.get("summary_text") or " ".join(
        [jd.title or "", " ".join(jd.must_have or []), " ".join(jd.nice_to_have or []),
         " ".join(struct.get("responsibilities") or [])[:800], jd.raw_text[:600]]
    )


def _keyword_score(candidate: dict, jd: JobDescription) -> float:
    skill_part = skill_match(candidate.get("skills") or {}, {"must_have": jd.must_have or [], "nice_to_have": jd.nice_to_have or []})
    title_tokens = set(extract_known_skills(jd.title or ""))
    title_part = 1.0 if title_tokens and title_tokens & set(candidate.get("skills") or {}) else 0.0
    role_bonus = 0.15 if jd.role_family == candidate.get("role") else 0.0
    return skill_part + 0.1 * title_part + role_bonus


def _embedding_score(candidate: dict, jd: JobDescription) -> float:
    cand_vec = candidate.get("embedding")
    jd_vec = jd.embedding_json
    if not cand_vec or not jd_vec or len(cand_vec) != len(jd_vec):
        # consistent offline fallback: hash both summary texts with the same space
        cand_vec = hash_embed(candidate.get("summary_text", ""))
        jd_vec = hash_embed(_jd_text(jd))
    return max(0.0, cosine(cand_vec, jd_vec))


def rrf(rank_lists: list[list[int]], k: int = 60) -> list[int]:
    scores: dict[int, float] = {}
    for ranks in rank_lists:
        for position, jd_id in enumerate(ranks, start=1):
            scores[jd_id] = scores.get(jd_id, 0.0) + 1.0 / (k + position)
    return sorted(scores, key=scores.get, reverse=True)  # type: ignore[arg-type]


def hybrid_retrieve(
    db: Session,
    candidate: dict,
    role: str,
    pool_size: Optional[int] = None,
    company_id: Optional[int] = None,
) -> list[dict]:
    """Returns [{jd, retrieval_score}] limited to `pool_size`, best first."""
    pool_size = pool_size or settings.CANDIDATE_POOL_SIZE
    jds = load_ready_jds(db, role, company_id)
    if not jds:
        return []

    keyword_ranked = sorted(jds, key=lambda j: _keyword_score(candidate, j), reverse=True)
    embedding_ranked = sorted(jds, key=lambda j: _embedding_score(candidate, j), reverse=True)

    conf = load_weights()["retrieval"]
    order = rrf([[j.id for j in keyword_ranked], [j.id for j in embedding_ranked]], k=int(conf["rrf_k"]))

    # blend RRF position with the raw keyword score so skill match dominates ties
    rrf_pos = {jd_id: idx for idx, jd_id in enumerate(order)}
    by_id = {j.id: j for j in jds}
    blended = []
    for jd in jds:
        blend = (
            conf["embedding_share"] * (1.0 - rrf_pos[jd.id] / len(jds))
            + conf["keyword_share"] * min(1.0, _keyword_score(candidate, jd))
        )
        blended.append((jd, blend))
    blended.sort(key=lambda pair: (rrf_pos[pair[0].id], -pair[1]))

    return [{"jd": jd, "retrieval_score": round(score, 4)} for jd, score in blended[:pool_size]]

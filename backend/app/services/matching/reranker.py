"""Stage 3: LLM re-check + explanation for the top results only.

Math decides the score; the LLM may nudge it by at most +-5 points and every
claim it makes must be verifiable against data we already have.
"""

import json
from typing import Optional

from app.core.config import settings
from app.core.logging import get_logger
from app.services.llm.client import llm, load_prompt
from app.services.skills.normalizer import extract_known_skills

log = get_logger("reranker")
MAX_ADJUSTMENT = 5


def template_explanation(candidate: dict, jd: dict, scores: dict) -> dict:
    skill_info = scores["breakdown"]["skill_match"]
    strengths = [f"{s} - strong evidence on resume/GitHub" for s in skill_info["matched"][:5]]
    gaps = [f"{s} - required but weak or missing" for s in skill_info["missing_must"][:5]]
    gaps += [f"{s} - good-to-have, not found" for s in skill_info["missing_nice"][:3]]
    if not strengths:
        strengths = ["Profile aligned with the " + (jd.get("role_family") or "target") + " role"]
    title = jd.get("title") or "this role"
    summary = (
        f"Match for {title}: resume {scores['resume_score']}, "
        f"github {scores.get('github_score') if scores.get('github_score') is not None else 'n/a'}, "
        f"overall {scores['overall_score']}. "
        f"Matched {len(skill_info['matched'])} of "
        f"{len(skill_info['matched']) + len(skill_info['missing_must']) + len(skill_info['partial'])} key skills."
    )
    return {
        "summary": summary,
        "strengths": strengths,
        "gaps": gaps,
        "red_flags": [],
        "score_adjustment": 0,
        "adjustment_reason": "",
        "source": "template",
    }


def _validate(explanation: dict, candidate: dict, jd: dict) -> Optional[dict]:
    if not isinstance(explanation, dict):
        return None
    try:
        adjustment = int(explanation.get("score_adjustment") or 0)
    except (TypeError, ValueError):
        adjustment = 0
    adjustment = max(-MAX_ADJUSTMENT, min(MAX_ADJUSTMENT, adjustment))

    allowed = set(candidate.get("skills") or {}) | set(jd.get("must_have") or []) | set(
        jd.get("nice_to_have") or []
    )
    for key in ("strengths", "gaps", "red_flags"):
        values = [str(v) for v in (explanation.get(key) or []) if str(v).strip()][:8]
        for value in values:
            mentioned = set(extract_known_skills(value))
            if mentioned - allowed:
                log.warning("LLM cited unknown skills %s - rejecting explanation", mentioned - allowed)
                return None
        explanation[key] = values

    explanation["score_adjustment"] = adjustment
    explanation["adjustment_reason"] = str(explanation.get("adjustment_reason") or "")[:300]
    explanation["summary"] = str(explanation.get("summary") or "")[:600]
    explanation["source"] = "llm"
    return explanation


def explain(candidate: dict, jd: dict, scores: dict) -> dict:
    explanation = template_explanation(candidate, jd, scores)
    if not llm.enabled:
        return explanation

    payload = {
        "candidate": {
            "role": candidate.get("role"),
            "years_experience": candidate.get("years_experience"),
            "skills": {k: v for k, v in sorted((candidate.get("skills") or {}).items())},
            "evidence_sample": dict(list((candidate.get("evidence") or {}).items())[:25]),
            "projects": (candidate.get("project_text") or "")[:800],
            "github_metrics": candidate.get("github_metrics"),
            "consistency": candidate.get("consistency"),
        },
        "jd": {
            "title": jd.get("title"),
            "role_family": jd.get("role_family"),
            "seniority": jd.get("seniority"),
            "min_years": jd.get("min_years"),
            "must_have": jd.get("must_have"),
            "nice_to_have": jd.get("nice_to_have"),
            "responsibilities": (jd.get("structured") or {}).get("responsibilities", [])[:8],
        },
        "scores": {
            "resume_score": scores["resume_score"],
            "github_score": scores.get("github_score"),
            "overall_score": scores["overall_score"],
            "matched_skills": scores["breakdown"]["skill_match"]["matched"],
            "missing_must": scores["breakdown"]["skill_match"]["missing_must"],
        },
    }
    prompt = load_prompt(
        "explain_match.txt",
        candidate=json.dumps(payload["candidate"], indent=1),
        jd=json.dumps(payload["jd"], indent=1),
        scores=json.dumps(payload["scores"], indent=1),
    )
    raw = llm.generate_json(prompt, temperature=0.2)
    validated = _validate(raw, candidate, jd) if raw else None
    if not validated:
        return explanation

    validated["score_adjustment"] = int(validated.get("score_adjustment") or 0)
    return validated


def apply_adjustment(base_overall: float, explanation: dict) -> float:
    adjustment = int(explanation.get("score_adjustment") or 0)
    return round(max(0.0, min(100.0, base_overall + adjustment)), 1)

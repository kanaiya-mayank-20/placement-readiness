"""Deterministic scoring. Math decides the score; the LLM only explains it."""

from functools import lru_cache
from typing import Optional

import yaml

from app.core.config import settings
from app.services.github.signals import github_component_weights
from app.services.llm.client import cosine, hash_embed
from app.services.skills.normalizer import extract_known_skills, skill_credit

SENIORITY_ORDER = ["intern", "junior", "mid", "senior", "lead"]


@lru_cache(maxsize=4)
def load_weights(path: Optional[str] = None) -> dict:
    target = path or str(settings.WEIGHTS_PATH)
    with open(target, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def skill_match_detailed(candidate_skills: dict[str, float], jd: dict) -> dict:
    weights = load_weights()
    w_must = float(weights["jd_weights"]["must"])
    w_nice = float(weights["jd_weights"]["nice"])
    must = jd.get("must_have") or []
    nice = jd.get("nice_to_have") or []

    if not must and not nice:
        return {
            "score": 0.5,
            "matched": [],
            "missing_must": [],
            "missing_nice": [],
            "partial": [],
            "total_weight": 0.0,
            "got": 0.0,
        }

    total = 0.0
    got = 0.0
    matched: list[str] = []
    missing_must: list[str] = []
    missing_nice: list[str] = []
    partial: list[dict] = []

    for skill in must:
        credit = skill_credit(candidate_skills, skill)
        total += w_must
        got += w_must * credit
        if credit >= 0.7:
            matched.append(skill)
        elif credit <= 0.05:
            missing_must.append(skill)
        else:
            partial.append({"skill": skill, "credit": round(credit, 2), "requirement": "must"})

    for skill in nice:
        credit = skill_credit(candidate_skills, skill)
        total += w_nice
        got += w_nice * credit
        if credit >= 0.7:
            matched.append(skill)
        elif credit <= 0.05:
            missing_nice.append(skill)
        else:
            partial.append({"skill": skill, "credit": round(credit, 2), "requirement": "nice"})

    return {
        "score": round(got / total, 4) if total else 0.0,
        "matched": matched,
        "missing_must": missing_must,
        "missing_nice": missing_nice,
        "partial": partial,
        "total_weight": total,
        "got": round(got, 3),
    }


def skill_match(candidate_skills: dict[str, float], jd: dict) -> float:
    return float(skill_match_detailed(candidate_skills, jd)["score"])


def experience_fit(candidate_years: float, jd_min_years: float) -> float:
    candidate_years = float(candidate_years or 0.0)
    jd_min_years = float(jd_min_years or 0.0)
    if jd_min_years <= 0:
        return 1.0
    if candidate_years >= jd_min_years:
        return 1.0
    return max(0.0, candidate_years / jd_min_years)


def seniority_of(years: float) -> str:
    years = float(years or 0)
    if years < 1:
        return "intern"
    if years < 3:
        return "junior"
    if years < 5:
        return "mid"
    if years < 8:
        return "senior"
    return "lead"


def seniority_fit(candidate_years: float, jd_seniority: str) -> float:
    jd_sen = jd_seniority if jd_seniority in SENIORITY_ORDER else "mid"
    diff = SENIORITY_ORDER.index(seniority_of(candidate_years)) - SENIORITY_ORDER.index(jd_sen)
    if diff == 0:
        return 1.0
    if diff == 1:
        return 0.9
    if diff > 1:
        return max(0.5, 1.0 - 0.125 * diff)  # over-qualified: small penalty
    if diff == -1:
        return 0.75
    return max(0.2, 0.75 + 0.25 * diff)


def project_relevance(candidate: dict, jd: dict) -> float:
    project_skills = candidate.get("project_skills") or {}
    skill_part = skill_match(project_skills, jd) if project_skills else 0.0
    jd_text = candidate.get("_jd_text_cache") or ""
    text_part = 0.0
    if jd_text:
        text_part = max(0.0, cosine(hash_embed(candidate.get("project_text", "")), hash_embed(jd_text)))
    return round(0.6 * skill_part + 0.4 * text_part, 4)


def education_fit(candidate_education: list[str], jd_education: str) -> float:
    if not (jd_education or "").strip():
        return 1.0
    if not candidate_education:
        return 0.3
    want = (jd_education or "").lower()
    have = " ".join(candidate_education).lower()
    degree_tokens = ["bachelor", "b.tech", "b.e", "master", "m.tech", "m.e", "mca", "bca", "b.sc", "m.sc", "mba", "phd"]
    field_tokens = ["computer", "cs", "it", "information technology", "engineering", "science", "data", "software"]
    degree_ok = any(t in want for t in degree_tokens) and any(t in have for t in degree_tokens)
    field_ok = any(t in want for t in field_tokens) and any(t in have for t in field_tokens)
    if degree_ok and field_ok:
        return 1.0
    if degree_ok or field_ok:
        return 0.8
    return 0.5


def resume_score(candidate: dict, jd: dict) -> dict:
    w = load_weights()["resume_score"]
    skill = skill_match(candidate.get("resume_skills") or {}, jd)
    exp = experience_fit(candidate.get("years_experience", 0.0), jd.get("min_years", 0.0))
    proj = project_relevance(candidate, jd)
    edu = education_fit(candidate.get("education") or [], (jd.get("structured") or {}).get("education", ""))
    quality = float(candidate.get("resume_quality", 0.5))
    total = (
        w["skills"] * skill
        + w["experience"] * exp
        + w["projects"] * proj
        + w["education"] * edu
        + w["quality"] * quality
    )
    return {
        "score": round(100.0 * total, 1),
        "components": {
            "skill_match": round(skill, 3),
            "experience_fit": round(exp, 3),
            "project_relevance": round(proj, 3),
            "education_fit": round(edu, 3),
            "resume_quality": round(quality, 3),
        },
    }


def github_score(candidate: dict, jd: dict, role: str) -> dict:
    if not candidate.get("github_available"):
        return {"score": None, "components": None, "reason": "no usable GitHub profile"}
    metrics = candidate.get("github_metrics") or {}
    gh_skills = candidate.get("github_skills") or {}
    w = github_component_weights(role)
    evidence = skill_match(gh_skills, jd)
    total = (
        w["skill_evidence"] * evidence
        + w["project_quality"] * float(metrics.get("project_quality", 0.0))
        + w["activity_recency"] * float(metrics.get("activity_recency", 0.0))
        + w["collaboration"] * float(metrics.get("collaboration", 0.0))
        + w["depth"] * float(metrics.get("depth", 0.0))
    )
    return {
        "score": round(100.0 * total, 1),
        "components": {
            "skill_evidence": round(evidence, 3),
            "project_quality": round(float(metrics.get("project_quality", 0.0)), 3),
            "activity_recency": round(float(metrics.get("activity_recency", 0.0)), 3),
            "collaboration": round(float(metrics.get("collaboration", 0.0)), 3),
            "depth": round(float(metrics.get("depth", 0.0)), 3),
            "weights_used": {k: round(v, 2) for k, v in w.items()},
        },
    }


def role_fit(candidate: dict, jd: dict, role: str) -> dict:
    jd_role = (jd.get("role_family") or (jd.get("structured") or {}).get("role_family") or "").lower()
    same = 1.0 if jd_role == role else 0.0
    if same == 0.0:
        related = [
            {"frontend", "fullstack"},
            {"backend", "fullstack"},
            {"data", "ml"},
            {"fullstack", "mobile"},
            {"backend", "devops"},
        ]
        for pair in related:
            if {jd_role, role} <= pair:
                same = 0.8
                break
        else:
            same = 0.4
    sen = seniority_fit(candidate.get("years_experience", 0.0), jd.get("seniority") or "mid")
    return {"score": round(0.6 * same + 0.4 * sen, 3), "role_match": same, "seniority_fit": round(sen, 3)}


def overall_score(resume_s: float, github_s: Optional[float], role_s: float, role: str) -> tuple[float, dict]:
    weights = load_weights()
    mix = dict(weights["role_overrides"].get(role, weights["overall"]))
    if github_s is None:
        mix = dict(weights["overall_no_github"])
    total = mix["resume"] * resume_s + mix["github"] * (github_s or 0.0) + mix["role_fit"] * role_s
    return round(max(0.0, min(100.0, total)), 1), {k: round(v, 2) for k, v in mix.items()}


def score_jd(candidate: dict, jd: dict, role: str) -> dict:
    """Full structured score of one candidate against one JD.

    `jd` keys: must_have, nice_to_have, role_family, seniority, min_years, structured,
               text (summary text used for project relevance).
    """
    candidate = dict(candidate)
    candidate["_jd_text_cache"] = jd.get("text", "")

    res = resume_score(candidate, jd)
    gh = github_score(candidate, jd, role)
    rf = role_fit(candidate, jd, role)
    overall, mix = overall_score(res["score"], gh.get("score"), rf["score"], role)

    skill_info = skill_match_detailed(candidate.get("resume_skills") or {}, jd)
    gh_skill_info = skill_match_detailed(candidate.get("github_skills") or {}, jd)
    merged_info = skill_match_detailed(candidate.get("skills") or {}, jd)

    return {
        "resume_score": res["score"],
        "github_score": gh.get("score"),
        "overall_score": overall,
        "breakdown": {
            "resume": res["components"],
            "github": gh.get("components"),
            "github_reason": gh.get("reason"),
            "role_fit": rf,
            "overall_mix": mix,
            "skill_match": skill_info,
            "github_skill_match": gh_skill_info,
            "merged_skill_match": merged_info,
            "scoring_version": settings.SCORING_VERSION,
        },
    }

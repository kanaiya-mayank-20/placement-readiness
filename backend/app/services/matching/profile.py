"""Step C: merge resume + GitHub into one Candidate Profile.

Every skill carries a confidence (0..1) plus the evidence that produced it,
and we flag resume claims that GitHub cannot back up ("unverified").
"""

import re
from typing import Optional

from app.services.resume.resume_parser import resume_quality
from app.services.skills.normalizer import extract_known_skills, normalize_many

SKILLS_SECTION_POINTS = 0.30
PROJECT_POINTS = 0.30
EXPERIENCE_POINTS = 0.35
METRIC_POINTS = 0.10
GITHUB_POINTS = 0.20


def _resume_skills(resume_profile: dict) -> tuple[dict[str, float], dict[str, list[str]]]:
    strengths: dict[str, float] = {}
    evidence: dict[str, list[str]] = {}

    def add(skill: str, points: float, tag: str) -> None:
        if not skill:
            return
        strengths[skill] = min(1.0, strengths.get(skill, 0.0) + points)
        evidence.setdefault(skill, [])
        if tag not in evidence[skill]:
            evidence[skill].append(tag)

    for skill in normalize_many(resume_profile.get("skills") or []):
        add(skill, SKILLS_SECTION_POINTS, "resume:skills-list")

    for exp in resume_profile.get("experience") or []:
        title = exp.get("title") or "job"
        company = exp.get("company") or ""
        for skill in normalize_many(list(exp.get("skills_used") or []) + extract_known_skills(exp.get("summary") or "")):
            add(skill, EXPERIENCE_POINTS, f"resume:job@{company or title}"[:80])
        # skills named in the job title itself (e.g. "React Developer")
        for skill in normalize_many(extract_known_skills(title)):
            add(skill, 0.2, f"resume:title@{company or title}"[:80])

    for project in resume_profile.get("projects") or []:
        skills = normalize_many(list(project.get("tech") or []) + extract_known_skills(project.get("description") or ""))
        points = PROJECT_POINTS + (METRIC_POINTS if project.get("has_metrics") else 0.0)
        for skill in skills:
            add(skill, points, f"resume:project:{project.get('name', '')}"[:80])

    for cert in resume_profile.get("certifications") or []:
        for skill in normalize_many(extract_known_skills(str(cert))):
            add(skill, 0.1, "resume:certification")

    return strengths, evidence


def build_candidate_profile(
    resume_profile: dict,
    resume_text: str,
    github_derived: Optional[dict],
    role: str,
) -> dict:
    resume_skills, resume_evidence = _resume_skills(resume_profile)

    github_derived = github_derived or {}
    github_skills = {k: float(v) for k, v in (github_derived.get("skills") or {}).items()}
    github_evidence: dict[str, list[str]] = {}
    for skill in github_skills:
        repos = [r.get("name") for r in (github_derived.get("repos") or [])][:8]
        github_evidence[skill] = [f"github:{r}" for r in repos if r][:5] or ["github:profile"]

    merged: dict[str, float] = {}
    evidence: dict[str, list[str]] = {}
    for skill in set(resume_skills) | set(github_skills):
        r = resume_skills.get(skill, 0.0)
        g = github_skills.get(skill, 0.0)
        value = max(r, g) + (0.10 if r > 0 and g > 0 else 0.0)
        merged[skill] = round(min(1.0, value), 3)
        evidence[skill] = list(resume_evidence.get(skill, [])) + list(github_evidence.get(skill, []))

    unverified = sorted([s for s, v in resume_skills.items() if v >= 0.3 and github_skills.get(s, 0.0) == 0.0])
    not_on_resume = sorted([s for s in github_skills if s not in resume_skills])

    projects = resume_profile.get("projects") or []
    project_text = " ".join(
        f"{p.get('name', '')} {p.get('description', '')} {' '.join(p.get('tech') or [])}" for p in projects
    )
    project_skills: dict[str, float] = {}
    for p in projects:
        for skill in normalize_many(list(p.get("tech") or []) + extract_known_skills(p.get("description") or "")):
            project_skills[skill] = max(project_skills.get(skill, 0.0), 0.8)

    years = float(resume_profile.get("years_experience") or 0.0)
    if not years and resume_profile.get("experience"):
        years = float(len(resume_profile["experience"])) * 1.0

    github_available = bool(github_skills) or bool((github_derived.get("stats") or {}).get("public_repos"))

    top_skills = sorted(merged.items(), key=lambda kv: kv[1], reverse=True)[:20]
    summary_text = (
        f"{role} developer. Skills: {', '.join(s for s, _ in top_skills)}. "
        f"{years} years experience. "
        f"Projects: {project_text[:600]}. "
        f"Education: {'; '.join(resume_profile.get('education') or [])}."
    )

    return {
        "role": role,
        "name": resume_profile.get("name", ""),
        "years_experience": years,
        "education": list(resume_profile.get("education") or []),
        "certifications": list(resume_profile.get("certifications") or []),
        "links": list(resume_profile.get("links") or []),
        "resume_skills": resume_skills,
        "github_skills": github_skills,
        "skills": merged,
        "evidence": evidence,
        "project_skills": project_skills,
        "project_text": project_text[:4000],
        "resume_quality": resume_quality(resume_profile, resume_text),
        "github_available": github_available,
        "github_metrics": (github_derived.get("metrics") or {}) if github_derived else {},
        "github_stats": (github_derived.get("stats") or {}) if github_derived else {},
        "consistency": {
            "unverified_resume_claims": unverified[:20],
            "github_only_skills": not_on_resume[:20],
        },
        "summary_text": summary_text,
        "resume_quality_notes": _quality_notes(resume_profile, resume_text),
    }


def _quality_notes(resume_profile: dict, resume_text: str) -> list[str]:
    notes: list[str] = []
    low = (resume_text or "").lower()
    if len(resume_text or "") < 900:
        notes.append("Resume is quite short - add detail to experience and projects.")
    if not re.search(r"\d+\s*%|\b\d+(\.\d+)?\s*(k|m)?\s*(users|requests|req|ms|x)\b", low):
        notes.append("No measurable results found - add numbers (%, latency, users, throughput).")
    if not resume_profile.get("links"):
        notes.append("No links found - add your GitHub / portfolio URL.")
    if not resume_profile.get("experience"):
        notes.append("No work experience detected - add internships, freelance work or college projects.")
    return notes

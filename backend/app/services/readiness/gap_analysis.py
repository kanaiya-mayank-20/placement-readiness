"""Deterministic gap analysis (code computes the facts, the LLM only writes the plan)."""

import copy
from typing import Optional

from app.services.matching.scoring import score_jd, skill_match_detailed, seniority_of
from app.services.skills.normalizer import skill_credit

BANDS = [
    (85, "Ready - apply now"),
    (70, "Almost ready - fix 1 or 2 gaps"),
    (50, "Needs work - 1 to 3 months of focused effort"),
    (0, "Not yet - build the fundamentals first"),
]


def band_label(score: float) -> str:
    for threshold, label in BANDS:
        if score >= threshold:
            return label
    return BANDS[-1][1]


def _level(credit: float) -> str:
    if credit >= 0.7:
        return "strong"
    if credit >= 0.4:
        return "partial"
    if credit >= 0.05:
        return "weak"
    return "none"


def _simulate(candidate: dict, jd: dict, role: str, fill_skills: list[str]) -> float:
    sim = copy.deepcopy(candidate)
    sim["resume_skills"] = dict(sim.get("resume_skills") or {})
    sim["skills"] = dict(sim.get("skills") or {})
    for skill in fill_skills:
        sim["resume_skills"][skill] = max(sim["resume_skills"].get(skill, 0.0), 0.7)
        sim["skills"][skill] = max(sim["skills"].get(skill, 0.0), 0.7)
    return float(score_jd(sim, jd, role)["overall_score"])


def build_gap_report(candidate: dict, jd: dict, scores: dict, role: str) -> dict:
    merged = candidate.get("skills") or {}
    must = jd.get("must_have") or []
    nice = jd.get("nice_to_have") or []

    gap_rows: list[dict] = []
    for requirement, skills in (("must", must), ("nice", nice)):
        for skill in skills:
            credit = skill_credit(merged, skill)
            gap_rows.append(
                {
                    "skill": skill,
                    "requirement": requirement,
                    "you_have": round(float(credit), 2),
                    "you_have_label": _level(float(credit)),
                    "evidence": (candidate.get("evidence") or {}).get(skill, [])[:4],
                    "gap": "none" if credit >= 0.7 else "small" if credit >= 0.4 else "medium" if credit >= 0.05 else "missing",
                    "impact": round((3.0 if requirement == "must" else 1.0) * (1.0 - float(credit)), 3),
                }
            )
    gap_rows.sort(key=lambda row: -row["impact"])

    open_must = [g for g in gap_rows if g["requirement"] == "must" and g["you_have"] < 0.7]
    open_nice = [g for g in gap_rows if g["requirement"] == "nice" and g["you_have"] < 0.7]

    years = float(candidate.get("years_experience") or 0.0)
    min_years = float(jd.get("min_years") or 0.0)
    experience_ok = years >= min_years if min_years > 0 else True

    project_skill_score = skill_match_detailed(candidate.get("project_skills") or {}, jd)["score"]
    project_gap = "" if project_skill_score >= 0.4 else (
        "Your projects do not clearly cover this job's core work - build one project in this domain."
    )

    # ---------- resume fixes ----------
    resume_fixes: list[str] = list(candidate.get("resume_quality_notes") or [])
    for row in open_must[:5]:
        if row["you_have"] <= 0.05:
            resume_fixes.append(
                f"Add {row['skill']} to your skills / project sections only if you have genuinely used it - it is a must-have for this role."
            )
    for skill in (candidate.get("consistency") or {}).get("unverified_resume_claims", [])[:5]:
        resume_fixes.append(f"'{skill}' appears on your resume with no proof - add a project or repo that uses it.")

    # ---------- github fixes ----------
    github_fixes: list[str] = []
    gh_available = bool(candidate.get("github_available"))
    metrics = candidate.get("github_metrics") or {}
    gh_stats = candidate.get("github_stats") or {}
    if not gh_available:
        github_fixes.append("Create a GitHub profile and push 2-3 finished projects - recruiters check it.")
    else:
        if float(metrics.get("project_quality", 0)) < 0.5:
            github_fixes.append("Add a README, tests and a CI workflow to your main repositories.")
        if float(metrics.get("activity_recency", 0)) < 0.5:
            github_fixes.append("Push commits more consistently - recent activity matters more than old commits.")
        if float(metrics.get("depth", 0)) < 0.5:
            github_fixes.append("Grow 2-3 substantial repositories instead of many tiny ones.")
        for skill in (candidate.get("consistency") or {}).get("github_only_skills", [])[:4]:
            github_fixes.append(f"Add {skill} to your resume - your GitHub proves it but your resume does not mention it.")

    # ---------- what-if simulation ----------
    what_if: list[dict] = []
    base_overall = float(scores["overall_score"])
    base_band = band_label(base_overall)
    if open_must:
        top_one = [open_must[0]["skill"]]
        top_all = [g["skill"] for g in open_must[:3]]
        if top_one:
            after = _simulate(candidate, jd, role, top_one)
            what_if.append(
                {
                    "action": f"Get real evidence for {', '.join(top_one)} (project + resume + repo)",
                    "from": base_band,
                    "to": band_label(after),
                    "moves_up": after > base_overall + 0.5,
                }
            )
        if len(top_all) > 1:
            after_all = _simulate(candidate, jd, role, top_all)
            what_if.append(
                {
                    "action": f"Close your top {len(top_all)} must-have gaps: {', '.join(top_all)}",
                    "from": base_band,
                    "to": band_label(after_all),
                    "moves_up": after_all > base_overall + 0.5,
                }
            )

    strengths: list[str] = []
    for row in gap_rows:
        if row["requirement"] == "must" and row["you_have"] >= 0.7:
            ev = row["evidence"]
            strengths.append(f"{row['skill']} - {', '.join(ev[:3]) if ev else 'clear evidence on your resume'}")
    if experience_ok and min_years > 0:
        strengths.append(f"Experience fits: the role asks for {min_years:g} years and you have {years:g}.")
    elif experience_ok:
        strengths.append("No minimum experience barrier for this role.")
    strong_projects = [p for p in (candidate.get("project_skills") or {}) if p in set(must)]
    if strong_projects:
        strengths.append("Projects already use some of the required stack: " + ", ".join(strong_projects[:5]))
    if float(metrics.get("project_quality", 0)) >= 0.6:
        strengths.append("GitHub repos show good engineering hygiene (tests / docs / structure).")
    if float(metrics.get("activity_recency", 0)) >= 0.6:
        strengths.append("Consistent recent GitHub activity.")
    top_resume_skills = sorted((candidate.get("resume_skills") or {}).items(), key=lambda kv: -kv[1])[:5]
    if top_resume_skills:
        strengths.append("Strongest resume skills: " + ", ".join(s for s, _ in top_resume_skills))

    match_info = scores["breakdown"]["skill_match"]
    interview_topics: list[str] = []
    for topic in (jd.get("structured") or {}).get("responsibilities", [])[:6]:
        interview_topics.append(str(topic)[:160])
    interview_topics.extend(match_info["matched"][:4])
    interview_topics.extend(match_info["missing_must"][:4])
    seen: set[str] = set()
    interview_topics = [t for t in interview_topics if not (t.lower() in seen or seen.add(t.lower()))][:8]

    return {
        "band": base_band,
        "internal_score": base_overall,
        "gap_rows": gap_rows,
        "open_must": [g["skill"] for g in open_must],
        "open_nice": [g["skill"] for g in open_nice],
        "experience": {
            "required_years": min_years,
            "candidate_years": years,
            "candidate_seniority": seniority_of(years),
            "jd_seniority": jd.get("seniority"),
            "status": "meets" if experience_ok else "below",
        },
        "project_gap": project_gap,
        "project_relevance": project_skill_score,
        "resume_fixes": resume_fixes[:8],
        "github_fixes": github_fixes[:8],
        "what_if": what_if,
        "strengths": strengths[:8],
        "interview_topics": interview_topics,
    }

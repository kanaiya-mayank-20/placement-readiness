"""Turns the deterministic gap report into the student-facing readiness report.

IMPORTANT: the student-facing payload contains NO numeric score - only
strengths, suggestions to improve and next steps (plus a plain-language status).
"""

import json
from typing import Optional

from app.core.logging import get_logger
from app.services.llm.client import llm, load_prompt
from app.services.skills.normalizer import extract_known_skills

log = get_logger("readiness.report")

WEEK_PLAN_TEMPLATES = [
    "Close your biggest must-have skill gap",
    "Fix your resume and back every claim with proof",
    "Build one domain project and push it to GitHub",
    "Polish your GitHub, rehearse interviews and apply",
]


def _template_plan(candidate: dict, jd: dict, gap_report: dict) -> dict:
    open_must = gap_report["open_must"]
    open_nice = gap_report["open_nice"]
    title = jd.get("title") or "this role"

    strengths = list(gap_report.get("strengths") or [])
    if not strengths:
        strengths = ["You are targeting the right role family - start with one solid project."]

    suggestions: list[str] = []
    for skill in open_must[:4]:
        suggestions.append(
            f"Learn {skill} properly and prove it in a project - it is a must-have for {title}."
        )
    for skill in open_nice[:2]:
        suggestions.append(f"{skill} is a nice-to-have here; a small demo project would make you stand out.")
    for fix in (gap_report.get("resume_fixes") or [])[:3]:
        suggestions.append(fix)
    for fix in (gap_report.get("github_fixes") or [])[:3]:
        suggestions.append(fix)
    if not suggestions:
        suggestions = [
            f"You already cover the core stack for {title} - focus on depth, system design and interview practice.",
        ]

    week_focus: list[tuple[str, list[str]]] = []
    if open_must:
        week_focus.append(
            (
                f"Skill sprint: {', '.join(open_must[:2])}",
                [
                    f"Follow one structured course / docs track for {open_must[0]}",
                    f"Build a small working demo that uses {open_must[0]}",
                    f"Write down what you learned and add it to your resume",
                ],
            )
        )
    if len(open_must) > 2:
        week_focus.append(
            (
                f"Skill sprint: {', '.join(open_must[2:4])}",
                [
                    f"Implement {open_must[2]} in a real project",
                    "Add tests and a README to prove you can ship",
                    "Update your skills and project sections",
                ],
            )
        )
    week_focus.append(
        (
            WEEK_PLAN_TEMPLATES[1],
            (gap_report.get("resume_fixes") or ["Add measurable results to your best 3 bullets"])[:3],
        )
    )
    week_focus.append(
        (
            WEEK_PLAN_TEMPLATES[2],
            (gap_report.get("github_fixes") or ["Push your best work to GitHub with a clear README"])[:3],
        )
    )
    week_focus.append(
        (
            WEEK_PLAN_TEMPLATES[3],
            [
                f"Revise {title} fundamentals: " + ", ".join((jd.get("must_have") or [])[:5]),
                "Do 2 mock interviews / 10 practice questions",
                f"Apply to {title} roles with a tailored resume",
            ],
        )
    )
    week_focus = week_focus[:4]

    next_steps = [
        {"week": idx + 1, "focus": focus, "actions": actions[:4]}
        for idx, (focus, actions) in enumerate(week_focus)
    ]

    return {
        "strengths": strengths[:6],
        "suggestions_to_improve": suggestions[:6],
        "next_steps": next_steps,
        "interview_topics": (gap_report.get("interview_topics") or [])[:8],
        "source": "template",
    }


def _validate_plan(plan: dict, jd: dict, candidate: dict, gap_report: dict) -> Optional[dict]:
    if not isinstance(plan, dict):
        return None
    jd_skills = set(jd.get("must_have") or []) | set(jd.get("nice_to_have") or [])
    candidate_skills = set(candidate.get("skills") or {})
    gap_skills = set(gap_report.get("open_must") or []) | set(gap_report.get("open_nice") or [])

    def allowed_for_suggestion(text: str) -> bool:
        return not (set(extract_known_skills(text)) - jd_skills - gap_skills)

    def allowed_for_strength(text: str) -> bool:
        return not (set(extract_known_skills(text)) - jd_skills - candidate_skills)

    strengths = [str(s) for s in (plan.get("strengths") or []) if str(s).strip()][:8]
    suggestions = [str(s) for s in (plan.get("suggestions_to_improve") or []) if str(s).strip()][:8]
    topics = [str(s) for s in (plan.get("interview_topics") or []) if str(s).strip()][:10]

    steps = []
    for item in (plan.get("next_steps") or [])[:6]:
        if not isinstance(item, dict):
            continue
        actions = [str(a) for a in (item.get("actions") or []) if str(a).strip()][:5]
        if not actions:
            continue
        steps.append(
            {
                "week": int(item.get("week") or len(steps) + 1),
                "focus": str(item.get("focus") or "Improve your fit")[:160],
                "actions": actions,
            }
        )
    if len(steps) < 3:
        return None

    if any(not allowed_for_suggestion(s) for s in suggestions):
        log.warning("readiness LLM recommended unknown skills - using template")
        return None
    if any(not allowed_for_strength(s) for s in strengths):
        log.warning("readiness LLM invented a strength - using template")
        return None
    for step in steps:
        for action in step["actions"]:
            if not allowed_for_suggestion(action):
                log.warning("readiness LLM step mentions unknown skills - using template")
                return None

    return {
        "strengths": strengths,
        "suggestions_to_improve": suggestions,
        "next_steps": steps[:4],
        "interview_topics": topics,
        "source": "llm",
    }


def build_report(candidate: dict, jd: dict, gap_report: dict) -> dict:
    template = _template_plan(candidate, jd, gap_report)
    plan = template
    if llm.enabled:
        payload = {
            "role": candidate.get("role"),
            "years_experience": candidate.get("years_experience"),
            "has_github": candidate.get("github_available"),
            "title": jd.get("title"),
            "must_have": jd.get("must_have"),
            "nice_to_have": jd.get("nice_to_have"),
            "open_gaps": gap_report["open_must"],
            "nice_gaps": gap_report["open_nice"],
            "already_strong": [g["skill"] for g in gap_report["gap_rows"] if g["you_have"] >= 0.7],
            "experience_status": gap_report["experience"],
            "project_gap": gap_report["project_gap"],
            "resume_fixes": gap_report["resume_fixes"],
            "github_fixes": gap_report["github_fixes"],
            "interview_topics_seed": gap_report["interview_topics"],
        }
        prompt = load_prompt("readiness_plan.txt", gaps=json.dumps(payload, indent=1))
        raw = llm.generate_json(prompt, temperature=0.3)
        plan = _validate_plan(raw, jd, candidate, gap_report) or template

    return {
        "status": gap_report["band"],
        "strengths": plan["strengths"],
        "suggestions_to_improve": plan["suggestions_to_improve"],
        "next_steps": plan["next_steps"],
        "interview_topics": plan.get("interview_topics") or [],
        "gaps": [
            {
                "skill": g["skill"],
                "requirement": g["requirement"],
                "you_have": g["you_have_label"],
                "evidence": g["evidence"],
                "gap": g["gap"],
            }
            for g in gap_report["gap_rows"][:14]
        ],
        "experience": gap_report["experience"],
        "project_gap": gap_report["project_gap"],
        "what_if": gap_report["what_if"],
        "plan_source": plan.get("source", "template"),
    }

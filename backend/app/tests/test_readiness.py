"""Offline tests for the readiness report generator (no LLM)."""

from app.services.readiness.report_generator import _validate_plan, build_report


def _jd() -> dict:
    return {
        "id": 1,
        "title": "Backend Engineer",
        "role_family": "backend",
        "seniority": "mid",
        "min_years": 1,
        "must_have": ["python", "fastapi"],
        "nice_to_have": ["postgresql", "docker"],
        "structured": {},
        "text": "Backend role",
    }


def _candidate() -> dict:
    return {
        "role": "backend",
        "years_experience": 2,
        "github_available": False,
        "skills": {"python": 0.9, "fastapi": 0.8},
        "resume_skills": {"python": 0.9},
        "evidence": {},
        "project_skills": {},
        "github_metrics": {},
        "github_stats": {},
        "consistency": {},
    }


def _gap_report() -> dict:
    return {
        "band": "Ready - apply now",
        "internal_score": 88.0,
        "gap_rows": [
            {"skill": "python", "requirement": "must", "you_have": 0.9, "you_have_label": "strong", "evidence": [], "gap": "none", "impact": 0.0},
            {"skill": "fastapi", "requirement": "must", "you_have": 0.8, "you_have_label": "strong", "evidence": [], "gap": "none", "impact": 0.0},
        ],
        "open_must": [],
        "open_nice": [],
        "experience": {"required_years": 1, "candidate_years": 2, "candidate_seniority": "mid", "jd_seniority": "mid", "status": "meets"},
        "project_gap": "",
        "project_relevance": 0.6,
        "resume_fixes": [],
        "github_fixes": [],
        "what_if": [],
        "strengths": ["python - clear evidence on your resume"],
        "interview_topics": ["fastapi design"],
    }


def test_build_report_template_no_crash(monkeypatch):
    class _OfflineLLM:
        enabled = False

    monkeypatch.setattr("app.services.readiness.report_generator.llm", _OfflineLLM())
    report = build_report(_candidate(), _jd(), _gap_report())
    assert report["plan_source"] == "template"
    assert report["strengths"]
    assert report["next_steps"]
    assert len(report["next_steps"][0]["actions"]) >= 1


def test_validate_plan_accepts_list_of_known_skills():
    """extract_known_skills returns a list; comparing with skill sets must not raise."""
    plan = {
        "strengths": ["python and fastapi experience"],
        "suggestions_to_improve": ["Build a postgresql project"],
        "interview_topics": ["fastapi", "postgresql"],
        "next_steps": [
            {"week": 1, "focus": "Skill sprint", "actions": ["Learn postgresql", "Deploy with docker"]},
            {"week": 2, "focus": "Project", "actions": ["Build a python + fastapi demo", "Add a postgresql backend"]},
            {"week": 3, "focus": "Projects", "actions": ["Containerize it with docker"]},
            {"week": 4, "focus": "Apply", "actions": ["Apply to python roles"]},
        ],
    }
    candidate = _candidate()
    candidate["skills"] = {**candidate["skills"], "postgresql": 0.4, "docker": 0.4}
    validated = _validate_plan(plan, _jd(), candidate, _gap_report())
    assert validated is not None
    assert validated["source"] == "llm"
    assert validated["strengths"] == plan["strengths"]
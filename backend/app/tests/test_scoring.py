from app.services.matching.scoring import (
    experience_fit,
    load_weights,
    overall_score,
    role_fit,
    score_jd,
    seniority_of,
    skill_match,
    skill_match_detailed,
)

JD = {
    "title": "Backend Engineer",
    "role_family": "backend",
    "seniority": "mid",
    "min_years": 2,
    "must_have": ["python", "restapi", "postgresql", "docker"],
    "nice_to_have": ["kafka", "kubernetes", "aws"],
    "structured": {"education": ""},
    "text": "backend engineer payments apis",
}

CANDIDATE = {
    "role": "backend",
    "years_experience": 2.5,
    "resume_skills": {"python": 0.95, "restapi": 0.85, "postgresql": 0.70, "docker": 0.60,
                      "kafka": 0.30, "aws": 0.40},
    "github_skills": {"python": 0.8, "docker": 0.5},
    "skills": {"python": 1.0, "restapi": 0.85, "postgresql": 0.7, "docker": 0.8,
               "kafka": 0.3, "aws": 0.4},
    "evidence": {},
    "project_skills": {"python": 0.8, "postgresql": 0.7},
    "project_text": "payment api with postgres",
    "education": ["B.Tech Computer Science"],
    "resume_quality": 0.8,
    "github_available": True,
    "github_metrics": {"project_quality": 0.7, "activity_recency": 0.8,
                       "collaboration": 0.5, "depth": 0.6},
}


def test_skill_match_guide_example():
    info = skill_match_detailed(CANDIDATE["resume_skills"], JD)
    # guide's worked example: 10.0 / 15 = 0.667 (we allow a little related-skill credit)
    assert 0.63 <= info["score"] <= 0.78
    assert {"python", "restapi", "postgresql"} <= set(info["matched"])
    assert any(p["skill"] == "docker" for p in info["partial"])
    assert "kubernetes" in info["missing_nice"] or any(
        p["skill"] == "kubernetes" for p in info["partial"]
    )


def test_experience_fit():
    assert experience_fit(2.5, 2) == 1.0
    assert experience_fit(1.5, 2) == 0.75
    assert experience_fit(3, 0) == 1.0


def test_seniority():
    assert seniority_of(0.5) == "intern"
    assert seniority_of(2) == "junior"
    assert seniority_of(4) == "mid"
    assert seniority_of(6) == "senior"


def test_overall_matches_guide_formula():
    overall, mix = overall_score(77.8, 72.0, 85.0, "backend")
    assert abs(overall - 76.5) < 0.15
    assert mix["resume"] == 0.55


def test_overall_rebalances_without_github():
    overall, mix = overall_score(77.8, None, 85.0, "backend")
    assert mix["github"] == 0.0
    assert abs(overall - (0.8 * 77.8 + 0.2 * 85)) < 0.15


def test_score_jd_shape_and_bounds():
    result = score_jd(CANDIDATE, JD, "backend")
    for key in ("resume_score", "github_score", "overall_score"):
        assert 0.0 <= result[key] <= 100.0
    breakdown = result["breakdown"]
    assert breakdown["skill_match"]["matched"]
    assert "missing_must" in breakdown["skill_match"]
    assert set(breakdown["overall_mix"]) == {"resume", "github", "role_fit"}


def test_role_fit_prefers_matching_role():
    matching = role_fit(CANDIDATE, JD, "backend")["score"]
    other = role_fit(CANDIDATE, JD, "frontend")["score"]
    assert matching > other


def test_weights_sum_to_one():
    weights = load_weights()
    assert abs(sum(weights["resume_score"].values()) - 1.0) < 1e-6
    assert abs(sum(weights["overall"].values()) - 1.0) < 1e-6

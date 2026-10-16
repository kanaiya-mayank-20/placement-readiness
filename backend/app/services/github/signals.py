"""Role-aware GitHub signal weights.

The same repository is worth a different amount depending on the role the
student picked. Stored as config (not buried in scoring code) so it can be tuned.
"""

from collections import defaultdict

# component -> weight per role. Components: skill_evidence, project_quality,
# activity_recency, collaboration, depth. Each set must sum to 1.0.
GITHUB_ROLE_WEIGHTS: dict[str, dict[str, float]] = {
    "default": {"skill_evidence": 0.45, "project_quality": 0.20, "activity_recency": 0.15,
                "collaboration": 0.10, "depth": 0.10},
    "frontend": {"skill_evidence": 0.35, "project_quality": 0.28, "activity_recency": 0.12,
                 "collaboration": 0.10, "depth": 0.15},
    "backend": {"skill_evidence": 0.48, "project_quality": 0.20, "activity_recency": 0.14,
                "collaboration": 0.08, "depth": 0.10},
    "fullstack": {"skill_evidence": 0.42, "project_quality": 0.24, "activity_recency": 0.14,
                  "collaboration": 0.10, "depth": 0.10},
    "data": {"skill_evidence": 0.46, "project_quality": 0.22, "activity_recency": 0.14,
             "collaboration": 0.08, "depth": 0.10},
    "ml": {"skill_evidence": 0.46, "project_quality": 0.24, "activity_recency": 0.14,
           "collaboration": 0.06, "depth": 0.10},
    "devops": {"skill_evidence": 0.42, "project_quality": 0.24, "activity_recency": 0.16,
               "collaboration": 0.08, "depth": 0.10},
    "mobile": {"skill_evidence": 0.40, "project_quality": 0.26, "activity_recency": 0.16,
               "collaboration": 0.08, "depth": 0.10},
}


def github_component_weights(role: str) -> dict[str, float]:
    return GITHUB_ROLE_WEIGHTS.get(role, GITHUB_ROLE_WEIGHTS["default"])


# Which GitHub evidence types matter most for a role (used to nudge skill strength).
ROLE_EVIDENCE_PRIORITY: dict[str, set[str]] = {
    "frontend": {"react", "vue", "angular", "nextjs", "typescript", "javascript", "tailwind", "css", "html"},
    "backend": {"python", "java", "go", "fastapi", "django", "spring", "postgresql", "redis", "docker", "microservices"},
    "fullstack": {"react", "nextjs", "nodejs", "typescript", "postgresql", "docker"},
    "data": {"python", "pandas", "sql", "spark", "airflow", "powerbi", "tableau"},
    "ml": {"python", "pytorch", "tensorflow", "sklearn", "nlp", "llm"},
    "devops": {"docker", "kubernetes", "terraform", "aws", "githubactions", "linux", "cicd"},
    "mobile": {"flutter", "reactnative", "kotlin", "swift", "android", "ios"},
}


def aggregate_language_shares(repo_languages: list[dict]) -> dict[str, float]:
    """[{repo, languages:{lang: bytes}}] -> {lang: 0..1 total share across repos}"""
    totals: dict[str, float] = defaultdict(float)
    for entry in repo_languages:
        langs = entry.get("languages", {}) or {}
        total = sum(langs.values()) or 1
        for lang, nbytes in langs.items():
            totals[lang.lower()] += float(nbytes) / total
    return dict(totals)

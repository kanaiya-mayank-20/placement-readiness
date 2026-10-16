from app.services.skills.normalizer import (
    extract_known_skills,
    load_taxonomy,
    normalize,
    normalize_many,
    skill_credit,
)


def test_alias_normalisation():
    assert normalize("ReactJS") == "react"
    assert normalize("React.js") == "react"
    assert normalize(" react  ") == "react"
    assert normalize("Postgres") == "postgresql"
    assert normalize("K8s") == "kubernetes"
    assert normalize("Node.js") == "nodejs"
    assert normalize("scikit learn") == "sklearn"


def test_unknown_skill_returns_none():
    assert normalize("time-travel-debugger") is None
    assert normalize("") is None


def test_normalize_many_dedupes():
    assert normalize_many(["ReactJS", "react", "next.js", "django"]) == ["react", "nextjs", "django"]


def test_extract_known_skills_from_text():
    text = "We use React, TypeScript and PostgreSQL with Docker on AWS."
    found = set(extract_known_skills(text))
    assert {"react", "typescript", "postgresql", "docker", "aws"} <= found


def test_related_credit():
    assert skill_credit({"postgresql": 0.8}, "postgresql") == 0.8
    # related (both in the postgres/mysql family) earns partial credit
    assert 0.0 < skill_credit({"postgresql": 0.8}, "mysql") <= 1.0
    # a totally different unknown skill earns nothing
    assert skill_credit({"react": 0.9}, "haskell") == 0.0


def test_taxonomy_loads_once():
    tax = load_taxonomy()
    assert len(tax.skills) > 100
    assert "react" in tax.skills
    assert tax.category("react") == "frontend"

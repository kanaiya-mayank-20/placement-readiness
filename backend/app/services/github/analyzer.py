"""GitHub profile -> skill evidence + quality signals.

Design rules (from the guide):
- dependencies and languages beat guessing from file extensions
- only user-authored activity counts toward activity/collaboration
- popular-but-empty repos must not inflate the score
- every network call is optional: failures degrade the score, never crash the pipeline
"""

import json
import re
from datetime import datetime, timezone
from typing import Optional

from app.core.config import settings
from app.core.logging import get_logger
from app.services.github.client import GitHubClient, GitHubError, GitHubRateLimited
from app.services.skills.normalizer import extract_known_skills, normalize

log = get_logger("github.analyzer")

DEP_FILES = [
    "package.json",
    "requirements.txt",
    "pyproject.toml",
    "pom.xml",
    "go.mod",
    "Cargo.toml",
    "Gemfile",
    "composer.json",
    "build.gradle",
]
TEST_PATH_RE = re.compile(r"(^|/)(tests?|specs?|__tests__)(/|$)|\.(test|spec)\.[a-z]+$", re.I)


def _utc(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def _parse_dep_file(name: str, content: str) -> list[str]:
    out: list[str] = []
    if name == "package.json":
        try:
            data = json.loads(content)
            for key in ("dependencies", "devDependencies"):
                out.extend((data.get(key) or {}).keys())
        except Exception:
            out.extend(re.findall(r'"([a-z0-9@/._\-]+)"\s*:', content))
    elif name in ("requirements.txt", "pyproject.toml", "build.gradle"):
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith(("#", ";", "//")):
                continue
            if name == "requirements.txt":
                out.append(re.split(r"[=<>!~\[;]", line)[0].strip())
            elif name == "build.gradle":
                out.extend(re.findall(r"implementation\s+['\"]([^:'\"]+)", line))
            else:
                out.extend(re.findall(r"['\"]([A-Za-z0-9_.\-]+)", line))
    elif name == "pom.xml":
        out = re.findall(r"<artifactId>([^<]+)</artifactId>", content)
    elif name == "go.mod":
        for line in content.splitlines():
            parts = line.split()
            if len(parts) >= 2 and not parts[0].startswith("//"):
                out.append(parts[0])
    elif name == "Cargo.toml":
        out = re.findall(r"^\s*([A-Za-z0-9_\-]+)\s*=", content, re.M)
    elif name == "Gemfile":
        out = re.findall(r"gem\s+['\"]([^'\"]+)['\"]", content)
    elif name == "composer.json":
        try:
            data = json.loads(content)
            out = list((data.get("require") or {}).keys()) + list((data.get("require-dev") or {}).keys())
        except Exception:
            pass
    return [p for p in out if p and not p.startswith((".", "-"))]


def _readme_is_good(readme: Optional[str]) -> bool:
    if not readme:
        return False
    words = len(readme.split())
    return words >= 120 or ("http" in readme and words >= 50)


def _is_deployed(readme: Optional[str], topics: list[str]) -> bool:
    blob = ((readme or "") + " " + " ".join(topics)).lower()
    return any(h in blob for h in ("vercel.app", "netlify.app", "herokuapp", "github.io", "live demo", "deployed"))


def analyze_github(username: str) -> dict:
    client = GitHubClient()
    warnings: list[str] = []

    user = client.get_user(username)
    try:
        repos = client.get_repos(username)
    except GitHubError as exc:
        warnings.append(f"could not list repositories: {exc}")
        repos = []

    repos = [r for r in repos if isinstance(r, dict)]
    repos.sort(key=lambda r: r.get("pushed_at") or "", reverse=True)
    top = repos[: settings.GITHUB_MAX_REPOS]
    detailed_budget = settings.GITHUB_DETAILED_REPOS if client.token else min(4, settings.GITHUB_DETAILED_REPOS)
    detailed = [r for r in top if not r.get("fork")][:detailed_budget] or top[:detailed_budget]

    lang_max: dict[str, float] = {}
    lang_total: dict[str, float] = {}
    dep_hits: dict[str, int] = {}
    topic_hits: dict[str, int] = {}
    readme_hits: dict[str, int] = {}
    repos_with: dict[str, set[str]] = {}
    quality_rows: list[dict] = []
    repo_summaries: list[dict] = []

    def _touch(skill: Optional[str], repo_name: str) -> None:
        if skill:
            repos_with.setdefault(skill, set()).add(repo_name)

    for repo in top:
        name = repo.get("name", "")
        paths: list[str] = []
        readme: Optional[str] = None
        languages: dict = {}
        dep_skills: set[str] = set()

        if repo in detailed:
            try:
                languages = client.get_languages(user["login"], name)
            except GitHubError:
                languages = {}
            try:
                paths = client.get_tree_paths(user["login"], name)
            except GitHubError:
                paths = []
            readme = client.get_readme(user["login"], name)
            for dep_name in DEP_FILES:
                if any(p.lower().endswith("/" + dep_name.lower()) or p.lower() == dep_name.lower() for p in paths):
                    content = client.get_file(user["login"], name, dep_name) or client.get_file(
                        user["login"], name, next(p for p in paths if p.lower().endswith(dep_name.lower()))
                    )
                    if content:
                        for dep in _parse_dep_file(dep_name, content[:60000]):
                            canon = normalize(dep)
                            if canon:
                                dep_skills.add(canon)
                    break

        total_bytes = sum(languages.values()) or 1
        repo_langs = {}
        for lang, nbytes in languages.items():
            share = nbytes / total_bytes
            repo_langs[lang.lower()] = share
            canon = normalize(lang)
            if not canon:
                continue
            lang_total[canon] = lang_total.get(canon, 0.0) + share
            lang_max[canon] = max(lang_max.get(canon, 0.0), share)
            _touch(canon, name)

        for dep in dep_skills:
            dep_hits[dep] = dep_hits.get(dep, 0) + 1
            _touch(dep, name)

        for topic in repo.get("topics") or []:
            canon = normalize(str(topic))
            if canon:
                topic_hits[canon] = topic_hits.get(canon, 0) + 1
                _touch(canon, name)

        if readme:
            for skill in extract_known_skills(readme)[:40]:
                readme_hits[skill] = readme_hits.get(skill, 0) + 1
                _touch(skill, name)

        has_tests = any(TEST_PATH_RE.search(p) for p in paths) or bool(re.search(r"test|spec", name, re.I))
        has_ci = any(p.startswith(".github/workflows/") for p in paths)
        has_docker = any(p.lower().endswith("dockerfile") or "docker-compose" in p.lower() for p in paths)
        structure_ok = len(paths) >= 15 or any(p.startswith(("src/", "lib/", "app/")) for p in paths)
        readme_good = _readme_is_good(readme)
        topics = [str(t) for t in (repo.get("topics") or [])]
        deployed = _is_deployed(readme, topics)

        if repo in detailed or has_tests or has_ci:
            quality_rows.append(
                {
                    "tests": 1.0 if has_tests else 0.0,
                    "ci": 1.0 if has_ci else 0.0,
                    "docs": 1.0 if readme_good else (0.5 if readme else 0.0),
                    "structure": 1.0 if structure_ok else 0.0,
                    "deployed": 1.0 if deployed else 0.0,
                    "docker": 1.0 if has_docker else 0.0,
                }
            )

        repo_summaries.append(
            {
                "name": name,
                "description": (repo.get("description") or "")[:200],
                "language": (repo.get("language") or "").lower(),
                "stars": repo.get("stargazers_count", 0),
                "forks": repo.get("forks_count", 0),
                "fork": bool(repo.get("fork")),
                "size_kb": repo.get("size", 0),
                "pushed_at": repo.get("pushed_at"),
                "topics": topics[:10],
                "has_tests": has_tests,
                "has_ci": has_ci,
                "has_docker": has_docker,
                "languages": repo_langs,
            }
        )

    # ---------------- skills strengths ----------------
    skills: dict[str, float] = {}
    all_skills = set(lang_total) | set(dep_hits) | set(topic_hits) | set(readme_hits)
    for skill in all_skills:
        score = 0.0
        max_share = lang_max.get(skill, 0.0)
        if max_share > 0:
            score += 0.25 + 0.25 * min(1.0, max_share * 2)
        if dep_hits.get(skill, 0) > 0:
            score += 0.30
        if topic_hits.get(skill, 0) > 0:
            score += 0.10
        if readme_hits.get(skill, 0) > 0:
            score += 0.10
        if len(repos_with.get(skill, set())) >= 3:
            score += 0.10
        skills[skill] = round(min(1.0, score), 3)

    # ---------------- metrics ----------------
    if quality_rows:
        n = len(quality_rows)
        project_quality = round(
            sum(
                0.24 * r["tests"] + 0.24 * r["ci"] + 0.22 * r["docs"] + 0.16 * r["structure"] + 0.14 * r["deployed"]
                for r in quality_rows
            )
            / n,
            3,
        )
    else:
        project_quality = 0.0

    now = datetime.now(timezone.utc)

    def _recency_weight(ts: Optional[str]) -> float:
        dt = _utc(ts)
        if not dt:
            return 0.0
        days = (now - dt).days
        if days <= 30:
            return 1.0
        if days <= 90:
            return 0.75
        if days <= 180:
            return 0.5
        if days <= 365:
            return 0.3
        return 0.1

    recent_weights = [_recency_weight(r.get("pushed_at")) for r in top[:10]]
    activity_recency = round(sum(recent_weights) / len(recent_weights), 3) if recent_weights else 0.0

    events: list[dict] = []
    try:
        events = client.get_public_events(username)
    except GitHubError as exc:
        warnings.append(f"could not read public events: {exc}")

    recent_events = [e for e in events if (now - (_utc(e.get("created_at")) or now)).days <= 90]
    activity_recency = min(1.0, activity_recency + min(0.2, 0.03 * len(recent_events)))

    cross_pr = 0
    collab_events = 0
    for event in recent_events:
        etype = event.get("type", "")
        repo_name = (event.get("repo") or {}).get("name", "")
        own_repo = repo_name.lower().startswith(f"{username.lower()}/")
        if etype in ("PullRequestEvent", "PullRequestReviewEvent"):
            collab_events += 1
            if not own_repo:
                cross_pr += 1
        elif etype in ("IssuesEvent", "IssueCommentEvent"):
            collab_events += 1
    followers = int(user.get("followers", 0) or 0)
    collaboration = round(
        min(1.0, 0.12 * cross_pr + 0.06 * collab_events + min(0.15, followers / 300.0)), 3
    )

    substantial = [r for r in top if int(r.get("size") or 0) >= 100 and not r.get("fork")]
    substantial_ratio = len(substantial) / len(top) if top else 0.0
    distinct_langs = {r.get("language") for r in top if r.get("language")}
    depth = round(min(1.0, 0.6 * substantial_ratio + 0.4 * min(1.0, len(distinct_langs) / 4)), 3)

    total_stars = sum(int(r.get("stargazers_count") or 0) for r in top)
    warnings_trimmed = warnings[:10]

    derived = {
        "username": user.get("login", username),
        "skills": skills,
        "metrics": {
            "project_quality": project_quality,
            "activity_recency": round(activity_recency, 3),
            "collaboration": collaboration,
            "depth": depth,
        },
        "evidence": {
            "languages": {k: round(v, 3) for k, v in sorted(lang_total.items(), key=lambda kv: -kv[1])},
            "dependencies": dep_hits,
            "topics": topic_hits,
            "readme": readme_hits,
        },
        "stats": {
            "public_repos": int(user.get("public_repos", 0) or 0),
            "followers": followers,
            "total_stars": total_stars,
            "detailed_repos": len(detailed),
            "recent_events_90d": len(recent_events),
            "cross_repo_prs": cross_pr,
        },
        "repos": repo_summaries,
        "warnings": warnings_trimmed,
        "has_tests_any": any(r["has_tests"] for r in repo_summaries),
        "has_ci_any": any(r["has_ci"] for r in repo_summaries),
        "has_docker_any": any(r["has_docker"] for r in repo_summaries),
    }

    raw = {
        "user": {
            "login": user.get("login"),
            "name": user.get("name"),
            "bio": (user.get("bio") or "")[:300],
            "followers": followers,
            "public_repos": user.get("public_repos"),
            "created_at": user.get("created_at"),
            "html_url": user.get("html_url"),
        },
        "repos": repo_summaries[:50],
        "events": [
            {"type": e.get("type"), "created_at": e.get("created_at"), "repo": (e.get("repo") or {}).get("name")}
            for e in recent_events[:40]
        ],
        "requests_made": client.requests_made,
        "rate_limit_remaining": client.rate_limit_remaining,
    }
    return {"raw": raw, "derived": derived}

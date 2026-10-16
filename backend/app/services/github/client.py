"""Minimal, resilient GitHub REST client."""

from typing import Any, Optional

import httpx

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("github.client")


class GitHubError(Exception):
    pass


class GitHubNotFound(GitHubError):
    pass


class GitHubRateLimited(GitHubError):
    pass


class GitHubClient:
    def __init__(self, token: Optional[str] = None, timeout: float = 20.0):
        self.token = (token if token is not None else settings.GITHUB_TOKEN) or ""
        self.timeout = timeout
        self.requests_made = 0
        self.rate_limit_remaining: Optional[int] = None

    def _headers(self) -> dict:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "resume-company-matcher",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def get(self, path: str, params: Optional[dict] = None) -> Any:
        if self.rate_limit_remaining is not None and self.rate_limit_remaining <= 2:
            raise GitHubRateLimited("GitHub rate limit nearly exhausted")
        url = path if path.startswith("http") else f"{settings.GITHUB_API_BASE}{path}"
        try:
            resp = httpx.get(url, params=params, headers=self._headers(), timeout=self.timeout,
                             follow_redirects=True)
        except httpx.HTTPError as exc:
            raise GitHubError(f"network error: {exc}") from exc

        self.requests_made += 1
        remaining = resp.headers.get("X-RateLimit-Remaining")
        if remaining is not None:
            self.rate_limit_remaining = int(remaining)

        if resp.status_code == 404:
            raise GitHubNotFound(f"not found: {path}")
        if resp.status_code in (403, 429):
            if remaining == "0" or "rate limit" in resp.text.lower():
                raise GitHubRateLimited("GitHub API rate limit exceeded")
            raise GitHubError(f"forbidden ({resp.status_code}): {path}")
        if resp.status_code >= 500:
            raise GitHubError(f"github {resp.status_code} on {path}")
        if resp.status_code >= 400:
            raise GitHubError(f"github {resp.status_code}: {resp.text[:200]}")
        return resp.json()

    def get_user(self, username: str) -> dict:
        return self.get(f"/users/{username}")

    def get_repos(self, username: str, per_page: int = 100, max_pages: int = 2) -> list[dict]:
        repos: list[dict] = []
        for page in range(1, max_pages + 1):
            batch = self.get(
                f"/users/{username}/repos",
                params={"per_page": per_page, "page": page, "sort": "pushed", "direction": "desc"},
            )
            if not isinstance(batch, list) or not batch:
                break
            repos.extend(batch)
            if len(batch) < per_page:
                break
        return repos

    def get_languages(self, owner: str, repo: str) -> dict:
        data = self.get(f"/repos/{owner}/{repo}/languages")
        return data if isinstance(data, dict) else {}

    def get_tree_paths(self, owner: str, repo: str, ref: str = "HEAD") -> list[str]:
        data = self.get(f"/repos/{owner}/{repo}/git/trees/{ref}", params={"recursive": "1"})
        tree = data.get("tree", []) if isinstance(data, dict) else []
        return [item.get("path", "") for item in tree if item.get("type") == "blob"]

    def get_file(self, owner: str, repo: str, path: str) -> Optional[str]:
        try:
            data = self.get(f"/repos/{owner}/{repo}/contents/{path}")
        except GitHubError:
            return None
        if isinstance(data, dict) and data.get("content") and data.get("encoding") == "base64":
            import base64

            try:
                return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
            except Exception:
                return None
        return None

    def get_readme(self, owner: str, repo: str) -> Optional[str]:
        try:
            data = self.get(f"/repos/{owner}/{repo}/readme")
        except GitHubError:
            return None
        if isinstance(data, dict) and data.get("content"):
            import base64

            try:
                return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
            except Exception:
                return None
        return None

    def get_workflow_count(self, owner: str, repo: str) -> int:
        try:
            data = self.get(f"/repos/{owner}/{repo}/actions/workflows")
            return int(data.get("total_count", 0)) if isinstance(data, dict) else 0
        except GitHubError:
            return 0

    def get_public_events(self, username: str, per_page: int = 100) -> list[dict]:
        data = self.get(f"/users/{username}/events/public", params={"per_page": per_page})
        return data if isinstance(data, list) else []

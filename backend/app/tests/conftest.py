"""Test configuration - must run before any app import.

Tests are fully offline: no Gemini key, no GitHub token, isolated SQLite DB.
"""

import os
import tempfile
from pathlib import Path

_TEST_DB = Path(tempfile.gettempdir()) / "resume_matcher_tests.db"
if _TEST_DB.exists():
    try:
        _TEST_DB.unlink()
    except OSError:
        pass

os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB}"
os.environ.setdefault("GEMINI_API_KEY", "")
os.environ.setdefault("GITHUB_TOKEN", "")
os.environ.setdefault("TOP_N_COMPANIES", "3")
os.environ.setdefault("CANDIDATE_POOL_SIZE", "50")
os.environ.setdefault("EXPLAIN_TOP_K", "2")
os.environ.setdefault("ADMIN_REGISTRATION_KEY", "test-admin-key")
os.environ.setdefault("WORKER_CONCURRENCY", "2")

import pytest  # noqa: E402


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


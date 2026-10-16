import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = BASE_DIR / "uploads"
PROMPTS_DIR = Path(__file__).resolve().parents[1] / "services" / "llm" / "prompts"

for _d in (DATA_DIR, UPLOAD_DIR):
    _d.mkdir(parents=True, exist_ok=True)

load_dotenv(BASE_DIR / ".env")


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "") or default)
    except ValueError:
        return default


class Settings:
    APP_NAME = "Resume + GitHub -> Company Match API"
    VERSION = "1.0.0"
    API_PREFIX = "/api"

    DATABASE_URL = os.getenv("DATABASE_URL", "").strip() or f"sqlite:///{DATA_DIR / 'app.db'}"

    GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest").strip()
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "gemini-embedding-001").strip()
    LLM_TIMEOUT = _int("LLM_TIMEOUT", 90)
    EMBEDDING_FALLBACK_DIM = _int("EMBEDDING_FALLBACK_DIM", 512)

    TOP_N_COMPANIES = _int("TOP_N_COMPANIES", 5)
    CANDIDATE_POOL_SIZE = _int("CANDIDATE_POOL_SIZE", 50)
    EXPLAIN_TOP_K = _int("EXPLAIN_TOP_K", 3)

    JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me-please-use-32-plus-chars")
    JWT_ALGORITHM = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES = _int("ACCESS_TOKEN_EXPIRE_MINUTES", 60 * 24)

    ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "").strip()
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "").strip()
    ADMIN_REGISTRATION_KEY = os.getenv("ADMIN_REGISTRATION_KEY", "").strip()

    CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
    MAX_UPLOAD_MB = _int("MAX_UPLOAD_MB", 5)
    WORKER_CONCURRENCY = _int("WORKER_CONCURRENCY", 2)

    GITHUB_MAX_REPOS = _int("GITHUB_MAX_REPOS", 30)
    GITHUB_DETAILED_REPOS = _int("GITHUB_DETAILED_REPOS", 10)
    GITHUB_API_BASE = "https://api.github.com"

    TAXONOMY_PATH = Path(__file__).resolve().parents[1] / "services" / "skills" / "taxonomy.yaml"
    WEIGHTS_PATH = Path(__file__).resolve().parents[1] / "services" / "matching" / "weights.yaml"

    PARSER_VERSION = "1.0"
    TAXONOMY_VERSION = "1.0"
    SCORING_VERSION = "1.0"


settings = Settings()

ROLES = ["frontend", "backend", "fullstack", "data", "ml", "devops", "mobile"]
ROLE_LABELS = {
    "frontend": "Frontend Developer",
    "backend": "Backend Developer",
    "fullstack": "Full-Stack Developer",
    "data": "Data Analyst / Data Engineer",
    "ml": "Machine Learning Engineer",
    "devops": "DevOps / Cloud Engineer",
    "mobile": "Mobile Developer",
}

SENIORITY_VALUES = ["intern", "junior", "mid", "senior", "lead"]

"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import admin, analyses, auth, companies, meta
from app.core.config import ROLES, settings
from app.core.logging import get_logger, setup_logging
from app.db.database import SessionLocal, init_db
from app.db.models import User
from app.core.security import hash_password
from app.workers.runner import runner
from app.workers.tasks import register_handlers

log = get_logger("app")


def seed_admin() -> None:
    if not (settings.ADMIN_EMAIL and settings.ADMIN_PASSWORD):
        return
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == settings.ADMIN_EMAIL.lower()).first()
        if existing is None:
            db.add(
                User(
                    email=settings.ADMIN_EMAIL.lower(),
                    name="Administrator",
                    hashed_password=hash_password(settings.ADMIN_PASSWORD),
                    role="admin",
                )
            )
            db.commit()
            log.info("seeded admin account %s", settings.ADMIN_EMAIL)
        elif existing.role != "admin":
            existing.role = "admin"
            db.commit()
            log.info("promoted %s to admin", settings.ADMIN_EMAIL)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    setup_logging()
    init_db()
    seed_admin()
    register_handlers()
    runner.start()
    log.info("%s v%s started (roles=%s)", settings.APP_NAME, settings.VERSION, ROLES)
    yield
    runner.stop()


app = FastAPI(title=settings.APP_NAME, version=settings.VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS or ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(meta.router)
app.include_router(admin.router)
app.include_router(companies.router)
app.include_router(analyses.router)


@app.get("/")
def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.VERSION,
        "docs": "/docs",
        "health": "/api/health",
    }

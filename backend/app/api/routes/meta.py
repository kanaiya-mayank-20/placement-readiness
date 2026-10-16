from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import ROLE_LABELS, ROLES, settings
from app.db.database import get_db
from app.db.models import Analysis, JobDescription, User

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(select(1))
    return {"status": "ok", "version": settings.VERSION, "llm_enabled": bool(settings.GEMINI_API_KEY)}


@router.get("/roles")
def list_roles(db: Session = Depends(get_db), _user=Depends(get_current_user)):
    counts = dict(
        db.execute(
            select(JobDescription.role_family, func.count())
            .where(JobDescription.is_active.is_(True), JobDescription.status == "ready")
            .group_by(JobDescription.role_family)
        ).all()
    )
    return {
        "roles": [
            {"id": role, "label": ROLE_LABELS[role], "openings": int(counts.get(role, 0))}
            for role in ROLES
        ],
        "top_n_companies": settings.TOP_N_COMPANIES,
    }

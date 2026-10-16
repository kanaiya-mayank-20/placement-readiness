from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import LoginIn, RegisterIn, user_out
from app.core.config import ROLES, settings
from app.core.security import create_access_token, hash_password, verify_password
from app.db.database import get_db
from app.db.models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _token_for(user: User) -> dict:
    return {
        "access_token": create_access_token(str(user.id), {"role": user.role}),
        "token_type": "bearer",
        "user": user_out(user),
    }


@router.post("/register", status_code=201)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    role = (body.role or "student").strip().lower()
    if role not in ("student", "admin"):
        raise HTTPException(status_code=400, detail="role must be 'student' or 'admin'")
    if role == "admin":
        if not settings.ADMIN_REGISTRATION_KEY:
            raise HTTPException(
                status_code=403,
                detail="Admin registration is disabled. Ask the operator to seed an admin account.",
            )
        if body.admin_key != settings.ADMIN_REGISTRATION_KEY:
            raise HTTPException(status_code=403, detail="Invalid admin registration key")

    email = body.email.strip().lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    user = User(email=email, name=(body.name or "").strip()[:255], hashed_password=hash_password(body.password), role=role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return _token_for(user)


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.strip().lower()))
    if user is None or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    return _token_for(user)


@router.get("/roles")
def roles():
    return {"roles": ROLES}

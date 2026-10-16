from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field


class RegisterIn(BaseModel):
    name: str = ""
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    role: str = "student"
    admin_key: str = ""


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class JDCreateIn(BaseModel):
    company_name: str = Field(min_length=1, max_length=255)
    title: str = ""
    raw_text: str = Field(min_length=1)
    role_family: Optional[str] = None
    website: Optional[str] = None
    location: Optional[str] = None
    industry: Optional[str] = None
    employment_type: Optional[str] = None
    compensation: Optional[str] = None
    work_mode: Optional[str] = None
    duration: Optional[str] = None
    conversion: Optional[str] = None
    eligibility: Optional[str] = None
    selection_process: Optional[List[str]] = None
    perks: Optional[List[str]] = None
    about: Optional[str] = None


JD_FIELDS = (
    "employment_type",
    "compensation",
    "work_mode",
    "duration",
    "conversion",
    "eligibility",
    "selection_process",
    "perks",
    "about",
)


class JDUpdateIn(BaseModel):
    title: Optional[str] = None
    raw_text: Optional[str] = None
    role_family: Optional[str] = None


class CompanyIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    industry: Optional[str] = None
    website: Optional[str] = None
    location: Optional[str] = None


class ScoreIn(BaseModel):
    jd_id: int


class ReadinessIn(BaseModel):
    jd_id: int


class FeedbackIn(BaseModel):
    analysis_id: int
    jd_id: int
    helpful: bool = True
    comment: str = ""


def user_out(user) -> dict:
    return {"id": user.id, "email": user.email, "name": user.name, "role": user.role}

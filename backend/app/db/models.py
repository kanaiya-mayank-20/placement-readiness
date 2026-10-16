from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), default="")
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="student")  # student | admin
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    analyses: Mapped[list["Analysis"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    industry: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    size: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    website: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    job_descriptions: Mapped[list["JobDescription"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )


class JobDescription(Base):
    __tablename__ = "job_descriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    title: Mapped[str] = mapped_column(String(255), default="")
    role_family: Mapped[Optional[str]] = mapped_column(String(30), index=True, nullable=True)
    seniority: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    min_years: Mapped[float] = mapped_column(Float, default=0.0)
    raw_text: Mapped[str] = mapped_column(Text, default="")
    structured_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    embedding_json: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    must_have: Mapped[list] = mapped_column(JSON, default=list)
    nice_to_have: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|processing|ready|failed
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    source: Mapped[str] = mapped_column(String(50), default="admin_upload")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    company: Mapped["Company"] = relationship(back_populates="job_descriptions")


class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(30), index=True)
    target_company_id: Mapped[Optional[int]] = mapped_column(ForeignKey("companies.id"), nullable=True, index=True)
    github_url: Mapped[str] = mapped_column(String(512), default="")
    github_username: Mapped[str] = mapped_column(String(255), default="")
    resume_path: Mapped[str] = mapped_column(String(512), default="")
    resume_filename: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    progress: Mapped[dict] = mapped_column(JSON, default=dict)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship(back_populates="analyses")
    target_company: Mapped[Optional["Company"]] = relationship()
    resume: Mapped[Optional["Resume"]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan", uselist=False
    )
    github_profile: Mapped[Optional["GithubProfile"]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan", uselist=False
    )
    candidate_profile: Mapped[Optional["CandidateProfile"]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan", uselist=False
    )
    match_results: Mapped[list["MatchResult"]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan"
    )


class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analyses.id"), index=True)
    raw_text: Mapped[str] = mapped_column(Text, default="")
    parsed_json: Mapped[dict] = mapped_column(JSON, default=dict)
    parser_version: Mapped[str] = mapped_column(String(20), default="")

    analysis: Mapped["Analysis"] = relationship(back_populates="resume")


class GithubProfile(Base):
    __tablename__ = "github_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analyses.id"), index=True)
    username: Mapped[str] = mapped_column(String(255), default="")
    raw_json: Mapped[dict] = mapped_column(JSON, default=dict)
    derived_json: Mapped[dict] = mapped_column(JSON, default=dict)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    analysis: Mapped["Analysis"] = relationship(back_populates="github_profile")


class CandidateProfile(Base):
    __tablename__ = "candidate_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analyses.id"), index=True)
    profile_json: Mapped[dict] = mapped_column(JSON, default=dict)
    embedding_json: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    analysis: Mapped["Analysis"] = relationship(back_populates="candidate_profile")


class MatchResult(Base):
    __tablename__ = "match_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analyses.id"), index=True)
    jd_id: Mapped[int] = mapped_column(ForeignKey("job_descriptions.id"), index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    overall_score: Mapped[float] = mapped_column(Float, default=0.0)
    resume_score: Mapped[float] = mapped_column(Float, default=0.0)
    github_score: Mapped[float] = mapped_column(Float, default=0.0)
    breakdown_json: Mapped[dict] = mapped_column(JSON, default=dict)
    explanation_json: Mapped[dict] = mapped_column(JSON, default=dict)
    rank: Mapped[int] = mapped_column(Integer, default=0)

    analysis: Mapped["Analysis"] = relationship(back_populates="match_results")


class ReadinessReport(Base):
    __tablename__ = "readiness_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analyses.id"), index=True)
    jd_id: Mapped[int] = mapped_column(ForeignKey("job_descriptions.id"), index=True)
    report_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analyses.id"), index=True)
    jd_id: Mapped[int] = mapped_column(ForeignKey("job_descriptions.id"), index=True)
    helpful: Mapped[bool] = mapped_column(Boolean, default=True)
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(50), index=True)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

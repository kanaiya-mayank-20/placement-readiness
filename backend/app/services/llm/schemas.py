"""Strict Pydantic schemas for every LLM output in the system."""

from typing import List, Optional

from pydantic import BaseModel, Field


class Experience(BaseModel):
    company: str = ""
    title: str = ""
    start: Optional[str] = None
    end: Optional[str] = None
    skills_used: List[str] = Field(default_factory=list)
    summary: str = ""


class Project(BaseModel):
    name: str = ""
    tech: List[str] = Field(default_factory=list)
    description: str = ""
    has_metrics: bool = False


class ResumeProfile(BaseModel):
    name: str = ""
    skills: List[str] = Field(default_factory=list)
    experience: List[Experience] = Field(default_factory=list)
    projects: List[Project] = Field(default_factory=list)
    education: List[str] = Field(default_factory=list)
    certifications: List[str] = Field(default_factory=list)
    links: List[str] = Field(default_factory=list)
    years_experience: Optional[float] = None


class StructuredJD(BaseModel):
    company: str = ""
    title: str = ""
    role_family: str = "backend"
    seniority: str = "mid"
    min_years: float = 0.0
    must_have: List[str] = Field(default_factory=list)
    nice_to_have: List[str] = Field(default_factory=list)
    responsibilities: List[str] = Field(default_factory=list)
    education: str = ""
    location: str = ""
    remote: str = ""
    industry: str = ""
    # --- company-facing detail fields surfaced to the admin dashboard ---
    employment_type: str = ""  # internship | full-time | contract | apprenticeship
    compensation: str = ""  # stipend / salary / CTC (e.g. "10,000 INR monthly stipend")
    work_mode: str = ""  # remote | hybrid | onsite
    duration: str = ""  # internship length / project timeline
    conversion: str = ""  # full-time conversion / absorption offer
    eligibility: str = ""  # degree / GPA / academic streams
    selection_process: List[str] = Field(default_factory=list)
    perks: List[str] = Field(default_factory=list)
    about: str = ""  # company overview / "About us"


class MatchExplanation(BaseModel):
    summary: str = ""
    strengths: List[str] = Field(default_factory=list)
    gaps: List[str] = Field(default_factory=list)
    red_flags: List[str] = Field(default_factory=list)
    score_adjustment: int = 0
    adjustment_reason: str = ""


class ReadinessPlan(BaseModel):
    strengths: List[str] = Field(default_factory=list)
    suggestions_to_improve: List[str] = Field(default_factory=list)
    next_steps: List[dict] = Field(default_factory=list)
    interview_topics: List[str] = Field(default_factory=list)

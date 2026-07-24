from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import CandidateSource


class ExperienceRecord(BaseModel):
    title: str
    company: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    summary: str | None = None


class EducationRecord(BaseModel):
    institution: str
    degree: str | None = None
    field_of_study: str | None = None
    graduation_year: str | None = None


class ProjectRecord(BaseModel):
    name: str
    summary: str | None = None
    technologies: list[str] = Field(default_factory=list)


class StructuredResume(BaseModel):
    name: str
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    current_title: str | None = None
    skills: list[str] = Field(default_factory=list)
    experience: list[ExperienceRecord] = Field(default_factory=list)
    education: list[EducationRecord] = Field(default_factory=list)
    projects: list[ProjectRecord] = Field(default_factory=list)
    total_experience_years: float = 0.0
    links: dict[str, str] = Field(default_factory=dict)
    availability: str | None = None
    source: CandidateSource
    parsing_quality_score: float = 1.0
    parsing_warnings: list[str] = Field(default_factory=list)
    summary: str


class ResumeSyncFileResult(BaseModel):
    relative_path: str
    source: CandidateSource
    candidate_id: str | None = None
    disposition: str
    status: str
    detail: str | None = None


class ResumeSyncSummary(BaseModel):
    started_at: datetime
    completed_at: datetime | None = None
    scanned_files: int = 0
    processed_files: int = 0
    embedded_files: int = 0
    skipped_files: int = 0
    failed_files: int = 0
    results: list[ResumeSyncFileResult] = Field(default_factory=list)


class ResumeSyncStatusResponse(BaseModel):
    watched_directory: str
    poll_interval_seconds: int
    running: bool
    last_summary: ResumeSyncSummary | None = None

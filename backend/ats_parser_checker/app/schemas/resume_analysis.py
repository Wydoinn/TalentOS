from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import CandidateSource


class ResumeCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str | None = Field(default=None, max_length=128)
    job_title: str | None = Field(default=None, max_length=255)
    job_description: str = Field(min_length=20)
    source: Literal["all", "internal", "external"] = "all"
    minimum_ats_score: float | None = Field(default=None, ge=0, le=100)
    retrieval_top_k: int | None = Field(default=None, ge=1, le=100)
    candidate_pool_size: int | None = Field(default=None, ge=1, le=100)
    final_top_k: int | None = Field(default=None, ge=1, le=100)


class ATSSectionStatus(BaseModel):
    skills: bool
    experience: bool
    projects: bool
    education: bool


class ResumeATSReport(BaseModel):
    candidate_id: str
    candidate_name: str
    candidate_email: str | None = None
    current_title: str | None = None
    relative_path: str
    source: CandidateSource
    summary: str
    rank: int = 0
    ats_score: float
    final_score: float
    keyword_score: float
    semantic_similarity: float
    formatting_score: float
    quality_score: float
    experience_relevance_score: float
    section_completeness_score: float
    retrieval_score: float | None = None
    graph_score: float | None = None
    reranker_score: float | None = None
    parsing_quality_score: float = 1.0
    parsing_warnings: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    missing_keywords: list[str] = Field(default_factory=list)
    matched_keywords: list[str] = Field(default_factory=list)
    sections: ATSSectionStatus
    formatting_signals: dict = Field(default_factory=dict)
    llm_summary: str | None = None
    generated_at: datetime | None = None


class ResumeCheckResponse(BaseModel):
    report_run_id: str
    job_id: str | None = None
    job_title: str | None = None
    job_description: str
    source: Literal["all", "internal", "external"]
    minimum_ats_score: float | None = None
    ranking_weights: dict[str, float] = Field(default_factory=dict)
    feedback_events_analyzed: int = 0
    total_candidates: int
    matched_candidates: int
    returned_candidates: int
    results: list[ResumeATSReport] = Field(default_factory=list)
    generated_at: datetime


class ResumeReportResponse(ResumeATSReport):
    report_run_id: str
    job_id: str | None = None
    job_title: str | None = None
    job_description: str | None = None

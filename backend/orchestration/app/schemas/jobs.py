from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import AssessmentStage, JobStatus, MatchStatus, RequirementType


class RequirementInput(BaseModel):
    requirement_type: RequirementType
    label: str = Field(min_length=1, max_length=255)
    weight: float = Field(default=1.0, ge=0.0, le=5.0)


class QuestionBlueprintItem(BaseModel):
    stage: AssessmentStage
    count: int = Field(ge=1, le=20)


def default_question_blueprint() -> list[QuestionBlueprintItem]:
    return [
        QuestionBlueprintItem(stage=AssessmentStage.INTRO, count=1),
        QuestionBlueprintItem(stage=AssessmentStage.CANDIDATE_INFO, count=1),
        QuestionBlueprintItem(stage=AssessmentStage.ROLE_SPECIFIC, count=10),
        QuestionBlueprintItem(stage=AssessmentStage.CODING, count=2),
        QuestionBlueprintItem(stage=AssessmentStage.SUMMARY, count=1),
    ]


class JobCreateRequest(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    department: str = Field(min_length=2, max_length=120)
    location: str = Field(min_length=2, max_length=160)
    employment_type: str = Field(default="full_time", min_length=2, max_length=80)
    seniority: str = Field(default="mid", min_length=2, max_length=80)
    description: str = Field(min_length=20)
    jd_text: str = Field(min_length=40)
    assessment_start_at: datetime | None = None
    assessment_end_at: datetime | None = None
    assessment_timezone: str = Field(default="UTC", min_length=2, max_length=64)
    assessment_slot_minutes: int = Field(default=30, ge=5, le=180)
    question_blueprint: list[QuestionBlueprintItem] = Field(default_factory=default_question_blueprint)
    status: JobStatus = JobStatus.ACTIVE
    requirements: list[RequirementInput] = Field(default_factory=list)


class JobUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=255)
    department: str | None = Field(default=None, min_length=2, max_length=120)
    location: str | None = Field(default=None, min_length=2, max_length=160)
    employment_type: str | None = Field(default=None, min_length=2, max_length=80)
    seniority: str | None = Field(default=None, min_length=2, max_length=80)
    description: str | None = Field(default=None, min_length=20)
    jd_text: str | None = Field(default=None, min_length=40)
    assessment_start_at: datetime | None = None
    assessment_end_at: datetime | None = None
    assessment_timezone: str | None = Field(default=None, min_length=2, max_length=64)
    assessment_slot_minutes: int | None = Field(default=None, ge=5, le=180)
    question_blueprint: list[QuestionBlueprintItem] | None = None
    status: JobStatus | None = None
    requirements: list[RequirementInput] | None = None


class JobResponse(BaseModel):
    id: str
    manager_user_id: str
    title: str
    department: str
    location: str
    employment_type: str
    seniority: str
    description: str
    jd_text: str
    assessment_start_at: datetime | None
    assessment_end_at: datetime | None
    assessment_timezone: str
    assessment_slot_minutes: int
    question_blueprint: list[QuestionBlueprintItem]
    status: JobStatus
    requirements: list[RequirementInput]
    created_at: datetime
    updated_at: datetime


class RankingRequest(BaseModel):
    source: str = Field(default="all", pattern="^(all|internal|external)$")
    minimum_ats_score: float | None = Field(default=None, ge=0, le=100)
    top_n: int | None = Field(default=None, ge=1, le=50)
    retrieval_top_k: int | None = Field(default=None, ge=1, le=100)
    candidate_pool_size: int | None = Field(default=None, ge=1, le=100)
    final_top_k: int | None = Field(default=None, ge=1, le=100)


class CandidateMatchResponse(BaseModel):
    match_id: str
    candidate_external_id: str
    candidate_name: str
    candidate_email: str | None
    source: str | None = None
    rank: int
    final_score: float
    ats_score: float
    status: MatchStatus
    explanation: str


class CandidateStatusUpdateRequest(BaseModel):
    status: MatchStatus


class RankingResponse(BaseModel):
    ranking_result_id: str
    report_run_id: str | None
    total_candidates: int
    invited_top_n: int
    matches: list[CandidateMatchResponse]


class JobCandidatesResponse(BaseModel):
    job_id: str
    ranking_result_id: str | None
    report_run_id: str | None
    candidates: list[CandidateMatchResponse]


class CandidateProfileAIResponse(BaseModel):
    candidate_external_id: str
    candidate_name: str
    candidate_email: str | None
    summary: str | None = None
    gemini_summary: str | None = None
    llm_summary: str | None = None
    reasons: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    matched_keywords: list[str] = Field(default_factory=list)
    missing_keywords: list[str] = Field(default_factory=list)
    source: str | None = None
    current_title: str | None = None
    relative_path: str | None = None
    match_explanation: str | None = None
    parsed_resume: dict = Field(default_factory=dict)
    contact: dict = Field(default_factory=dict)
    experience_timeline: list[dict] = Field(default_factory=list)
    projects: list[dict] = Field(default_factory=list)
    education: list[dict] = Field(default_factory=list)
    signals: dict = Field(default_factory=dict)
    sections: dict = Field(default_factory=dict)
    formatting_signals: dict = Field(default_factory=dict)
    generated_at: datetime | None = None


class AutoInviteResponse(BaseModel):
    ranking_result_id: str
    invited_count: int
    notification_ids: list[str] = Field(default_factory=list)


class ResumeCheckProxyRequest(BaseModel):
    job_id: str | None = None
    job_title: str | None = None
    job_description: str = Field(min_length=20)
    source: str = Field(default="all", pattern="^(all|internal|external)$")
    minimum_ats_score: float | None = Field(default=None, ge=0, le=100)
    retrieval_top_k: int | None = Field(default=None, ge=1, le=100)
    candidate_pool_size: int | None = Field(default=None, ge=1, le=100)
    final_top_k: int | None = Field(default=None, ge=1, le=100)

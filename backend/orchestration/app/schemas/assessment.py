from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import AssessmentStage, AssessmentStatus, DecisionOutcome, ProctoringSeverity


class AssessmentSessionCreateRequest(BaseModel):
    job_id: str
    candidate_email: str
    interview_schedule_id: str | None = None


class AssessmentSessionResponse(BaseModel):
    id: str
    room_id: str
    job_id: str
    candidate_profile_id: str
    status: AssessmentStatus
    anti_spoof_session_id: str | None
    heartbeat_at: datetime | None
    started_at: datetime | None
    ended_at: datetime | None
    integrity_score: float
    termination_reason: str | None = None
    question_blueprint: list[dict] = Field(default_factory=list)


class AssessmentJoinResponse(BaseModel):
    session: AssessmentSessionResponse
    websocket_url: str


class AssessmentHeartbeatRequest(BaseModel):
    status: AssessmentStatus = AssessmentStatus.IN_PROGRESS


class QuestionGenerateForSessionRequest(BaseModel):
    stage: AssessmentStage
    jd_context: str
    resume_context: str
    role_seniority: str = "mid"
    previous_answers: list[str] = Field(default_factory=list)
    count: int = Field(default=3, ge=1, le=20)


class QuestionItem(BaseModel):
    id: str | None = None
    stage: AssessmentStage
    prompt: str
    rubric: dict = Field(default_factory=dict)
    source: str | None = None
    sequence_no: int | None = None


class SessionQuestionResponse(BaseModel):
    questions: list[QuestionItem]


class AnswerSubmitRequest(BaseModel):
    question_id: str
    answer_text: str = Field(min_length=1)
    answer_transcript: str | None = None
    transcription_model: str | None = None


class AnswerEvaluationResponse(BaseModel):
    answer_id: str
    score: float
    confidence: float
    is_off_topic: bool
    classification: str
    reasons: list[str] = Field(default_factory=list)
    model: str
    fallback_used: bool


class ProctoringEventIngestRequest(BaseModel):
    event_type: str = Field(min_length=2, max_length=120)
    severity: ProctoringSeverity = ProctoringSeverity.INFO
    event_timestamp: datetime | None = None
    payload: dict = Field(default_factory=dict)


class AssessmentSpeechTranscriptionResponse(BaseModel):
    transcript: str
    model: str
    duration_seconds: float | None = None


class AssessmentVisionCheckResponse(BaseModel):
    face_count: int = 0
    gaze_status: str = "UNKNOWN"
    normalized_offset: float | None = None
    message: str | None = None


class AssessmentFinishRequest(BaseModel):
    force_decision: DecisionOutcome | None = None


class AssessmentReportResponse(BaseModel):
    assessment_session_id: str
    technical_score: float
    communication_score: float
    integrity_score: float
    coding_score: float
    overall_score: float
    decision: DecisionOutcome
    section_scores: dict = Field(default_factory=dict)
    reasons: list[str] = Field(default_factory=list)
    flagged_events_timeline: list[dict] = Field(default_factory=list)
    question_results: list[dict] = Field(default_factory=list)
    proctor_summary: str = ""
    termination_reason: str | None = None
    summary: str
    generated_by_model: str | None = None


class AssessmentReportSummaryItem(BaseModel):
    assessment_session_id: str
    candidate_profile_id: str
    candidate_name: str
    candidate_email: str
    job_id: str
    job_title: str
    session_status: AssessmentStatus
    report_available: bool = False
    decision: DecisionOutcome | None = None
    overall_score: float | None = None
    integrity_score: float | None = None
    summary: str | None = None
    termination_reason: str | None = None
    generated_by_model: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    created_at: datetime


class AssessmentReportSummaryResponse(BaseModel):
    items: list[AssessmentReportSummaryItem] = Field(default_factory=list)

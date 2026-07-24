"""Pydantic request and response schemas."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class OverallStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    FLAG = "FLAG"
    PENDING = "PENDING"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ChallengeType(str, Enum):
    PHRASE = "phrase"
    DIGIT_CODE = "digit_code"


class SessionStatus(str, Enum):
    CREATED = "created"
    CHALLENGED = "challenged"
    ANALYZING = "analyzing"
    RETRY_REQUIRED = "retry_required"
    REVIEW_READY = "review_ready"
    FINALIZED = "finalized"
    LOCKED = "locked"
    TERMINATED = "terminated"


class NextAction(str, Enum):
    NONE = "none"
    ISSUE_CHALLENGE = "issue_challenge"
    FINALIZE_SESSION = "finalize_session"
    LOCK_SESSION = "lock_session"


class ReasonCode(str, Enum):
    NO_FACE_DETECTED = "NO_FACE_DETECTED"
    MULTIPLE_FACES = "MULTIPLE_FACES"
    FACE_SPOOF_DETECTED = "FACE_SPOOF_DETECTED"
    FACE_QUALITY_LOW = "FACE_QUALITY_LOW"

    NO_AUDIO = "NO_AUDIO"
    AUDIO_SPOOF_DETECTED = "AUDIO_SPOOF_DETECTED"
    AUDIO_SILENCE = "AUDIO_SILENCE"
    STT_UNAVAILABLE = "STT_UNAVAILABLE"

    CHALLENGE_TIMEOUT = "CHALLENGE_TIMEOUT"
    KEYWORD_MISMATCH = "KEYWORD_MISMATCH"
    MOTION_NONCOMPLIANT = "MOTION_NONCOMPLIANT"
    BLINK_NOT_DETECTED = "BLINK_NOT_DETECTED"
    HEAD_TURN_NOT_DETECTED = "HEAD_TURN_NOT_DETECTED"
    CHALLENGE_NOT_ISSUED = "CHALLENGE_NOT_ISSUED"
    CHALLENGE_EXPIRED = "CHALLENGE_EXPIRED"
    CHALLENGE_SEQUENCE_INVALID = "CHALLENGE_SEQUENCE_INVALID"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"

    REPLAY_DETECTED = "REPLAY_DETECTED"
    DUPLICATE_FRAMES = "DUPLICATE_FRAMES"
    LOW_MOTION = "LOW_MOTION"
    FRAME_FREEZE = "FRAME_FREEZE"
    METADATA_ANOMALY = "METADATA_ANOMALY"

    IDENTITY_INCONSISTENT = "IDENTITY_INCONSISTENT"
    FACE_SWITCH_DETECTED = "FACE_SWITCH_DETECTED"

    PROCESSING_ERROR = "PROCESSING_ERROR"
    MEDIA_INVALID = "MEDIA_INVALID"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    TRUST_SCORE_LOW = "TRUST_SCORE_LOW"
    RETRY_ESCALATED = "RETRY_ESCALATED"


class CreateSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(..., min_length=1, max_length=128)
    job_id: str | None = Field(default=None, max_length=128)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreateSessionResponse(BaseModel):
    session_id: str
    candidate_id: str
    status: SessionStatus
    created_at: datetime
    expires_at: datetime
    access_token: str


class ChallengeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    challenge_type: ChallengeType | None = Field(
        default=None,
        description="Optional preferred challenge type. When omitted, the service alternates between phrase and digit_code prompts.",
    )


class ChallengeResponse(BaseModel):
    session_id: str
    challenge_id: str
    challenge_type: ChallengeType
    prompt: str
    instructions: list[str]
    expires_at: datetime


class AnalysisResult(BaseModel):
    overall_status: OverallStatus
    overall_score: float = Field(..., ge=0.0, le=100.0)

    face_score: float = Field(..., ge=0.0, le=100.0)
    audio_score: float = Field(..., ge=0.0, le=100.0)
    challenge_score: float = Field(..., ge=0.0, le=100.0)
    tamper_score: float = Field(..., ge=0.0, le=100.0)
    identity_consistency_score: float = Field(..., ge=0.0, le=100.0)

    reasons: list[ReasonCode] = Field(default_factory=list)
    human_readable_summary: str

    risk_level: RiskLevel
    top_issues: list[str] = Field(default_factory=list)
    confidence: str

    frame_count: int = 0
    faces_detected: int = 0
    audio_duration_sec: float = 0.0
    challenge_verified: bool = False
    trust_score: float = Field(default=50.0, ge=0.0, le=100.0)
    retry_allowed: bool = True
    processing_time_ms: float = 0.0
    analyzed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    session_status: SessionStatus | None = None
    decision_ready: bool = False
    next_action: NextAction = NextAction.NONE
    component_confidence: dict[str, float] = Field(default_factory=dict)
    component_diagnostics: dict[str, dict[str, Any]] = Field(default_factory=dict)


class SessionDetailResponse(BaseModel):
    session_id: str
    candidate_id: str
    job_id: str | None
    status: SessionStatus
    retry_count: int
    trust_score: float
    anomaly_count: int
    created_at: datetime
    expires_at: datetime
    final_decision: OverallStatus | None = None
    finalized_at: datetime | None = None
    locked_at: datetime | None = None
    challenge: ChallengeResponse | None
    latest_result: AnalysisResult | None


class FinalizeResponse(BaseModel):
    session_id: str
    final_decision: OverallStatus
    result: AnalysisResult | None
    finalized_at: datetime
    status: SessionStatus = SessionStatus.FINALIZED
    next_action: NextAction = NextAction.LOCK_SESSION


class LockResponse(BaseModel):
    session_id: str
    status: SessionStatus = SessionStatus.LOCKED
    final_decision: OverallStatus | None = None
    locked_at: datetime
    next_action: NextAction = NextAction.NONE


class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: datetime


class ReadyResponse(BaseModel):
    status: str
    models_loaded: dict[str, bool]
    session_store: bool


class DetailResponse(BaseModel):
    detail: str


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None
    session_id: str | None = None

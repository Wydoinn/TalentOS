from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import RecruiterFeedbackType


class CandidateFeedbackRequest(BaseModel):
    report_run_id: str = Field(min_length=1, max_length=64)
    candidate_id: str = Field(min_length=1, max_length=64)
    feedback_type: RecruiterFeedbackType
    note: str | None = Field(default=None, max_length=1000)
    metadata: dict = Field(default_factory=dict)


class CandidateFeedbackResponse(BaseModel):
    feedback_id: int
    report_run_id: str
    candidate_id: str
    feedback_type: RecruiterFeedbackType
    note: str | None = None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime | None = None


class FeedbackSummaryResponse(BaseModel):
    total_events: int = 0
    counts: dict[str, int] = Field(default_factory=dict)
    effective_weights: dict[str, float] = Field(default_factory=dict)
    learned_from_feedback: bool = False
    feedback_events_analyzed: int = 0

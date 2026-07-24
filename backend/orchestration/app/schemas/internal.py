from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field

from app.models.enums import ScheduleStatus


class CandidateInvitationValidationRequest(BaseModel):
    invitation_token: str = Field(min_length=16, max_length=256)
    candidate_email: EmailStr
    flow: str = Field(default="invite", pattern="^(invite|l0_session)$")
    schedule_id: str | None = Field(default=None, min_length=1, max_length=128)
    slot_id: str | None = Field(default=None, min_length=1, max_length=256)


class CandidateInvitationValidationResponse(BaseModel):
    valid: bool
    candidate_email: EmailStr | None = None
    schedule_status: ScheduleStatus | None = None
    job_id: str | None = None
    schedule_id: str | None = None
    slot_id: str | None = None

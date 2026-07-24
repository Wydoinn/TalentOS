from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import ScheduleStatus


class CreateSlotRequest(BaseModel):
    job_id: str
    start_at: datetime
    end_at: datetime
    timezone: str = Field(default="UTC", min_length=2, max_length=64)
    capacity: int = Field(default=1, ge=1, le=20)


class SlotResponse(BaseModel):
    id: str
    job_id: str
    start_at: datetime
    end_at: datetime
    timezone: str
    capacity: int
    reserved_count: int
    is_active: bool


class InviteCandidateRequest(BaseModel):
    candidate_email: str
    candidate_name: str
    candidate_user_id: str | None = None


class ScheduleBookRequest(BaseModel):
    invitation_token: str
    slot_id: str


class ScheduleRescheduleRequest(BaseModel):
    slot_id: str


class ScheduleCancelRequest(BaseModel):
    reason: str = Field(default="Cancelled by user", min_length=3, max_length=300)


class InterviewScheduleResponse(BaseModel):
    id: str
    candidate_profile_id: str
    job_id: str
    slot_id: str
    invitation_token: str
    status: ScheduleStatus
    booked_at: datetime | None
    cancelled_at: datetime | None


class CandidateScheduleView(BaseModel):
    schedule_id: str
    job_id: str
    slot_id: str
    candidate_name: str | None = None
    slot_start_at: datetime
    slot_end_at: datetime
    timezone: str
    status: ScheduleStatus

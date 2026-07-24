from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, EmailStr, Field, StringConstraints

from app.core.enums import AuthFlow, AuthNextStep, AuthStage, UserRole
from app.schemas.common import TokenResponse


SixDigitOTP = Annotated[str, StringConstraints(pattern=r"^\d{6}$")]


class OTPRequest(BaseModel):
    email: EmailStr
    role: UserRole
    invitation_token: str | None = Field(default=None, min_length=16, max_length=256)


class OTPDispatchResponse(BaseModel):
    flow: AuthFlow
    message: str
    expires_in_seconds: int


class OTPVerifyRequest(BaseModel):
    email: EmailStr
    role: UserRole
    otp_code: SixDigitOTP
    invitation_token: str | None = Field(default=None, min_length=16, max_length=256)


class AuthSessionResponse(BaseModel):
    user_id: str
    email: EmailStr
    role: UserRole
    flow: AuthFlow
    auth_stage: AuthStage
    is_authenticated: bool
    face_registered: bool
    can_register_face: bool
    requires_face_verification: bool
    next_step: AuthNextStep
    token: TokenResponse
    face_similarity_threshold: float | None = Field(default=None, ge=0.0, le=1.0)


class CandidateAccessValidationRequest(BaseModel):
    email: EmailStr
    invitation_token: str = Field(min_length=16, max_length=256)
    flow: Literal["invite", "l0_session"] = "invite"
    schedule_id: str | None = Field(default=None, min_length=1, max_length=128)
    slot_id: str | None = Field(default=None, min_length=1, max_length=256)


class CandidateAccessValidationResponse(BaseModel):
    valid: bool
    candidate_email: EmailStr | None = None
    schedule_status: str | None = None
    job_id: str | None = None
    schedule_id: str | None = None
    slot_id: str | None = None

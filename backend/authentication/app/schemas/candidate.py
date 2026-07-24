from __future__ import annotations

from pydantic import BaseModel, Field

from app.core.enums import AuthNextStep, AuthStage, FaceVerificationStatus
from app.schemas.common import TokenResponse


class FaceRegistrationResponse(BaseModel):
    user_id: str
    face_registered: bool
    auth_stage: AuthStage
    is_authenticated: bool
    next_step: AuthNextStep
    token: TokenResponse
    message: str


class FaceVerificationResponse(BaseModel):
    success: bool
    status: FaceVerificationStatus
    similarity_score: float | None = Field(default=None, ge=-1.0, le=1.0)
    threshold: float = Field(..., ge=0.0, le=1.0)
    remaining_attempts: int = Field(..., ge=0)
    auth_stage: AuthStage
    is_authenticated: bool
    next_step: AuthNextStep
    token: TokenResponse | None = None

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.schemas.auth import (
    AuthSessionResponse,
    CandidateAccessValidationRequest,
    CandidateAccessValidationResponse,
    OTPDispatchResponse,
    OTPRequest,
    OTPVerifyRequest,
)
from app.schemas.common import TokenResponse
from app.services.auth import AuthService, AuthSessionResult
from app.services.invitation_access import InvitationAccessService


settings = get_settings()
router = APIRouter(prefix="/auth", tags=["auth"])


def _build_auth_session_response(result: AuthSessionResult) -> AuthSessionResponse:
    return AuthSessionResponse(
        user_id=str(result.user.id),
        email=result.user.email,
        role=result.user.role,
        flow=result.flow,
        auth_stage=result.auth_stage,
        is_authenticated=result.is_authenticated,
        face_registered=result.face_registered,
        can_register_face=result.can_register_face,
        requires_face_verification=result.requires_face_verification,
        next_step=result.next_step,
        token=TokenResponse.from_token_bundle(result.token),
        face_similarity_threshold=result.face_similarity_threshold,
    )


@router.post(
    "/signup/send-otp",
    response_model=OTPDispatchResponse,
    summary="Send sign-up OTP",
    dependencies=[
        Depends(
            rate_limit(
                scope="signup-send-otp",
                max_requests=settings.send_otp_rate_limit,
                window_seconds=settings.send_otp_rate_window_seconds,
            )
        )
    ],
)
def send_signup_otp(
    payload: OTPRequest,
    db: Session = Depends(get_db),
) -> OTPDispatchResponse:
    service = AuthService(db=db)
    result = service.send_signup_otp(
        email=str(payload.email),
        role=payload.role,
        invitation_token=payload.invitation_token,
    )
    return OTPDispatchResponse(
        flow=result.flow,
        message="Sign-up OTP sent successfully.",
        expires_in_seconds=result.expires_in_seconds,
    )


@router.post(
    "/signup/verify-otp",
    response_model=AuthSessionResponse,
    summary="Verify sign-up OTP",
    dependencies=[
        Depends(
            rate_limit(
                scope="signup-verify-otp",
                max_requests=settings.verify_otp_rate_limit,
                window_seconds=settings.verify_otp_rate_window_seconds,
            )
        )
    ],
)
def verify_signup_otp(
    payload: OTPVerifyRequest,
    db: Session = Depends(get_db),
) -> AuthSessionResponse:
    service = AuthService(db=db)
    result = service.verify_signup_otp(
        email=str(payload.email),
        role=payload.role,
        otp_code=payload.otp_code,
        invitation_token=payload.invitation_token,
    )
    return _build_auth_session_response(result)


@router.post(
    "/login/send-otp",
    response_model=OTPDispatchResponse,
    summary="Send login OTP",
    dependencies=[
        Depends(
            rate_limit(
                scope="login-send-otp",
                max_requests=settings.send_otp_rate_limit,
                window_seconds=settings.send_otp_rate_window_seconds,
            )
        )
    ],
)
def send_login_otp(
    payload: OTPRequest,
    db: Session = Depends(get_db),
) -> OTPDispatchResponse:
    service = AuthService(db=db)
    result = service.send_login_otp(
        email=str(payload.email),
        role=payload.role,
        invitation_token=payload.invitation_token,
    )
    return OTPDispatchResponse(
        flow=result.flow,
        message="Login OTP sent successfully.",
        expires_in_seconds=result.expires_in_seconds,
    )


@router.post(
    "/login/verify-otp",
    response_model=AuthSessionResponse,
    summary="Verify login OTP",
    dependencies=[
        Depends(
            rate_limit(
                scope="login-verify-otp",
                max_requests=settings.verify_otp_rate_limit,
                window_seconds=settings.verify_otp_rate_window_seconds,
            )
        )
    ],
)
def verify_login_otp(
    payload: OTPVerifyRequest,
    db: Session = Depends(get_db),
) -> AuthSessionResponse:
    service = AuthService(db=db)
    result = service.verify_login_otp(
        email=str(payload.email),
        role=payload.role,
        otp_code=payload.otp_code,
        invitation_token=payload.invitation_token,
    )
    return _build_auth_session_response(result)


@router.post(
    "/candidate-access/validate",
    response_model=CandidateAccessValidationResponse,
    summary="Validate a candidate invite or session link before login",
)
def validate_candidate_access(
    payload: CandidateAccessValidationRequest,
) -> CandidateAccessValidationResponse:
    service = InvitationAccessService()
    result = service.validate_candidate_invitation(
        invitation_token=payload.invitation_token,
        candidate_email=str(payload.email),
        flow=payload.flow,
        schedule_id=payload.schedule_id,
        slot_id=payload.slot_id,
    )
    return CandidateAccessValidationResponse(
        valid=result.valid,
        candidate_email=result.candidate_email,
        schedule_status=result.schedule_status,
        job_id=result.job_id,
        schedule_id=result.schedule_id,
        slot_id=result.slot_id,
    )

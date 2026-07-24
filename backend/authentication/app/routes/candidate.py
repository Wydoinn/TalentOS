from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.enums import AuthNextStep, AuthStage, UserRole
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.dependencies.auth import AuthenticatedContext, require_roles
from app.schemas.candidate import FaceRegistrationResponse, FaceVerificationResponse
from app.schemas.common import TokenResponse
from app.services.face_verification import FaceVerificationService
from app.utils.images import build_device_info, read_image_upload


settings = get_settings()
router = APIRouter(prefix="/candidate", tags=["candidate"])
candidate_registration_access = require_roles(
    UserRole.CANDIDATE,
    allow_stages={AuthStage.FACE_REGISTRATION_REQUIRED},
)
candidate_verification_access = require_roles(
    UserRole.CANDIDATE,
    allow_stages={AuthStage.FACE_VERIFICATION_REQUIRED},
)


@router.post(
    "/register-face",
    response_model=FaceRegistrationResponse,
    dependencies=[
        Depends(
            rate_limit(
                scope="register-face",
                max_requests=settings.register_face_rate_limit,
                window_seconds=settings.register_face_rate_window_seconds,
            )
        )
    ],
)
async def register_face(
    image: UploadFile = File(...),
    context: AuthenticatedContext = Depends(candidate_registration_access),
    db: Session = Depends(get_db),
) -> FaceRegistrationResponse:
    image_bytes = await read_image_upload(image, field_label="face image")

    service = FaceVerificationService(db=db)
    result = await service.register_face(
        user=context.user,
        image_bytes=image_bytes,
    )
    return FaceRegistrationResponse(
        user_id=str(result.user.id),
        face_registered=result.user.face_registered,
        auth_stage=AuthStage.AUTHENTICATED,
        is_authenticated=True,
        next_step=AuthNextStep.AUTHENTICATED,
        token=TokenResponse.from_token_bundle(result.token),
        message="Face registered successfully. Candidate authentication is now complete.",
    )


@router.post(
    "/verify-face",
    response_model=FaceVerificationResponse,
    dependencies=[
        Depends(
            rate_limit(
                scope="verify-face",
                max_requests=settings.verify_face_rate_limit,
                window_seconds=settings.verify_face_rate_window_seconds,
            )
        )
    ],
)
async def verify_face(
    request: Request,
    image: UploadFile = File(...),
    device_info: Annotated[str | None, Form()] = None,
    context: AuthenticatedContext = Depends(candidate_verification_access),
    db: Session = Depends(get_db),
) -> FaceVerificationResponse:
    image_bytes = await read_image_upload(image, field_label="verification image")
    resolved_device_info = build_device_info(
        request_user_agent=request.headers.get("user-agent"),
        provided_device_info=device_info,
    )

    service = FaceVerificationService(db=db)
    result = await service.verify_face(
        user=context.user,
        image_bytes=image_bytes,
        device_info=resolved_device_info,
    )

    token_response = None
    if result.token is not None:
        token_response = TokenResponse.from_token_bundle(result.token)

    return FaceVerificationResponse(
        success=result.success,
        status=result.status,
        similarity_score=result.similarity_score,
        threshold=result.threshold,
        remaining_attempts=result.remaining_attempts,
        auth_stage=(
            AuthStage.AUTHENTICATED
            if result.success
            else AuthStage.FACE_VERIFICATION_REQUIRED
        ),
        is_authenticated=result.success,
        next_step=(
            AuthNextStep.AUTHENTICATED
            if result.success
            else AuthNextStep.VERIFY_FACE
        ),
        token=token_response,
    )

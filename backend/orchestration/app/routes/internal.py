from __future__ import annotations

from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db_session
from app.core.exceptions import ApiError
from app.schemas.internal import (
    CandidateInvitationValidationRequest,
    CandidateInvitationValidationResponse,
)
from app.services.scheduling_service import SchedulingService


router = APIRouter(prefix="/internal", tags=["internal"])


def require_internal_service_token(
    x_service_token: str | None = Header(default=None, alias="X-Service-Token"),
) -> None:
    settings = get_settings()
    expected_token = settings.internal_service_token.strip()
    if not expected_token:
        raise ApiError(
            status_code=503,
            code="internal_service_token_not_configured",
            message=(
                "Internal service token is not configured. "
                "Set ORCH_INTERNAL_SERVICE_TOKEN to enable internal endpoints."
            ),
        )

    if not x_service_token or x_service_token != expected_token:
        raise ApiError(
            status_code=401,
            code="invalid_service_token",
            message="Invalid internal service token.",
        )


@router.post(
    "/candidate-access/validate",
    response_model=CandidateInvitationValidationResponse,
    dependencies=[Depends(require_internal_service_token)],
)
async def validate_candidate_access(
    payload: CandidateInvitationValidationRequest,
    session: AsyncSession = Depends(get_db_session),
) -> CandidateInvitationValidationResponse:
    service = SchedulingService(session)
    result = await service.validate_candidate_invitation(
        invitation_token=payload.invitation_token,
        candidate_email=str(payload.candidate_email),
        flow=payload.flow,
        schedule_id=payload.schedule_id,
        slot_id=payload.slot_id,
    )
    return CandidateInvitationValidationResponse(
        valid=result.valid,
        candidate_email=result.candidate_email,
        schedule_status=result.schedule_status,
        job_id=result.job_id,
        schedule_id=result.schedule_id,
        slot_id=result.slot_id,
    )

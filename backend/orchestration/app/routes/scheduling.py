from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.security import AuthContext, get_auth_context, require_roles
from app.models.enums import UserRole
from app.schemas.scheduling import (
    CandidateScheduleView,
    CreateSlotRequest,
    InterviewScheduleResponse,
    InviteCandidateRequest,
    ScheduleBookRequest,
    ScheduleCancelRequest,
    ScheduleRescheduleRequest,
    SlotResponse,
)
from app.services.scheduling_service import SchedulingService


router = APIRouter(prefix="/schedules", tags=["scheduling"])
manager_only = require_roles(UserRole.PROJECT_MANAGER)


@router.post("/slots", response_model=SlotResponse)
async def create_slot(
    payload: CreateSlotRequest,
    request: Request,
    context: AuthContext = Depends(manager_only),
    session: AsyncSession = Depends(get_db_session),
) -> SlotResponse:
    service = SchedulingService(session)
    slot = await service.create_slot(payload=payload, context=context, request=request)
    return SlotResponse(
        id=slot.id,
        job_id=slot.job_id,
        start_at=slot.start_at,
        end_at=slot.end_at,
        timezone=slot.timezone,
        capacity=slot.capacity,
        reserved_count=slot.reserved_count,
        is_active=slot.is_active,
    )


@router.get("/slots", response_model=list[SlotResponse])
async def list_slots(
    job_id: str | None = None,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db_session),
) -> list[SlotResponse]:
    service = SchedulingService(session)
    slots = await service.list_slots(job_id=job_id, context=context)
    return [
        SlotResponse(
            id=slot.id,
            job_id=slot.job_id,
            start_at=slot.start_at,
            end_at=slot.end_at,
            timezone=slot.timezone,
            capacity=slot.capacity,
            reserved_count=slot.reserved_count,
            is_active=slot.is_active,
        )
        for slot in slots
    ]


@router.post("/{job_id}/invite", response_model=InterviewScheduleResponse)
async def invite_candidate(
    job_id: str,
    payload: InviteCandidateRequest,
    request: Request,
    context: AuthContext = Depends(manager_only),
    session: AsyncSession = Depends(get_db_session),
) -> InterviewScheduleResponse:
    service = SchedulingService(session)
    schedule = await service.invite_candidate(
        job_id=job_id,
        payload=payload,
        context=context,
        request=request,
    )
    return InterviewScheduleResponse(
        id=schedule.id,
        candidate_profile_id=schedule.candidate_profile_id,
        job_id=schedule.job_id,
        slot_id=schedule.slot_id or "",
        invitation_token=schedule.invitation_token,
        status=schedule.status,
        booked_at=schedule.booked_at,
        cancelled_at=schedule.cancelled_at,
    )


@router.post("/book", response_model=InterviewScheduleResponse)
async def book_slot(
    payload: ScheduleBookRequest,
    request: Request,
    context: AuthContext = Depends(require_roles(UserRole.CANDIDATE)),
    session: AsyncSession = Depends(get_db_session),
) -> InterviewScheduleResponse:
    service = SchedulingService(session)
    schedule = await service.book_slot(payload=payload, context=context, request=request)
    return InterviewScheduleResponse(
        id=schedule.id,
        candidate_profile_id=schedule.candidate_profile_id,
        job_id=schedule.job_id,
        slot_id=schedule.slot_id or "",
        invitation_token=schedule.invitation_token,
        status=schedule.status,
        booked_at=schedule.booked_at,
        cancelled_at=schedule.cancelled_at,
    )


@router.post("/{schedule_id}/reschedule", response_model=InterviewScheduleResponse)
async def reschedule_slot(
    schedule_id: str,
    payload: ScheduleRescheduleRequest,
    request: Request,
    context: AuthContext = Depends(require_roles(UserRole.CANDIDATE)),
    session: AsyncSession = Depends(get_db_session),
) -> InterviewScheduleResponse:
    service = SchedulingService(session)
    schedule = await service.reschedule_slot(
        schedule_id=schedule_id,
        payload=payload,
        context=context,
        request=request,
    )
    return InterviewScheduleResponse(
        id=schedule.id,
        candidate_profile_id=schedule.candidate_profile_id,
        job_id=schedule.job_id,
        slot_id=schedule.slot_id or "",
        invitation_token=schedule.invitation_token,
        status=schedule.status,
        booked_at=schedule.booked_at,
        cancelled_at=schedule.cancelled_at,
    )


@router.post("/{schedule_id}/cancel", response_model=InterviewScheduleResponse)
async def cancel_schedule(
    schedule_id: str,
    payload: ScheduleCancelRequest,
    request: Request,
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db_session),
) -> InterviewScheduleResponse:
    service = SchedulingService(session)
    schedule = await service.cancel_schedule(
        schedule_id=schedule_id,
        payload=payload,
        context=context,
        request=request,
    )
    return InterviewScheduleResponse(
        id=schedule.id,
        candidate_profile_id=schedule.candidate_profile_id,
        job_id=schedule.job_id,
        slot_id=schedule.slot_id or "",
        invitation_token=schedule.invitation_token,
        status=schedule.status,
        booked_at=schedule.booked_at,
        cancelled_at=schedule.cancelled_at,
    )


@router.get("/me", response_model=list[CandidateScheduleView])
async def my_schedules(
    context: AuthContext = Depends(require_roles(UserRole.CANDIDATE)),
    session: AsyncSession = Depends(get_db_session),
) -> list[CandidateScheduleView]:
    service = SchedulingService(session)
    return await service.list_candidate_schedules(context=context)

from __future__ import annotations

import base64
import json
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import Request
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings, get_settings
from app.core.exceptions import ApiError
from app.core.security import AuthContext
from app.models.base import utcnow
from app.models.entities import CandidateProfile, InterviewSchedule, Job, ScheduleSlot
from app.models.enums import NotificationType, ScheduleStatus, UserRole
from app.schemas.scheduling import (
    CandidateScheduleView,
    CreateSlotRequest,
    InviteCandidateRequest,
    ScheduleBookRequest,
    ScheduleCancelRequest,
    ScheduleRescheduleRequest,
)
from app.services.audit_service import AuditService
from app.services.notification_service import NotificationService


@dataclass(frozen=True, slots=True)
class SlotView:
    id: str
    job_id: str
    start_at: datetime
    end_at: datetime
    timezone: str
    capacity: int
    reserved_count: int
    is_active: bool


@dataclass(frozen=True, slots=True)
class CandidateInvitationValidation:
    valid: bool
    candidate_email: str | None
    schedule_status: ScheduleStatus | None
    job_id: str | None
    schedule_id: str | None
    slot_id: str | None


class SchedulingService:
    _window_block_re = re.compile(
        r"\[ASSESSMENT_WINDOW\](?P<body>[\s\S]*?)\[/ASSESSMENT_WINDOW\]",
        re.IGNORECASE,
    )
    _candidate_booking_lead_time = timedelta(minutes=10)

    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()

    async def create_slot(
        self,
        *,
        payload: CreateSlotRequest,
        context: AuthContext,
        request: Request | None,
    ) -> ScheduleSlot:
        if payload.end_at <= payload.start_at:
            raise ApiError(
                status_code=422,
                code="invalid_slot_window",
                message="Slot end time must be after start time.",
            )

        job = await self.session.get(Job, payload.job_id)
        if job is None:
            raise ApiError(status_code=404, code="job_not_found", message="Job was not found.")

        if context.role == UserRole.PROJECT_MANAGER and job.manager_user_id != context.user_id:
            raise ApiError(
                status_code=403,
                code="forbidden_job_access",
                message="Managers can only manage their own jobs.",
            )

        window = self._resolve_assessment_window(job)
        if window is not None:
            window_start, window_end, _, _ = window
            if payload.start_at < window_start or payload.end_at > window_end:
                raise ApiError(
                    status_code=422,
                    code="slot_outside_assessment_window",
                    message="Slot must be within the assessment window defined in the JD.",
                )

        slot = ScheduleSlot(
            job_id=payload.job_id,
            start_at=payload.start_at,
            end_at=payload.end_at,
            timezone=payload.timezone,
            capacity=payload.capacity,
            reserved_count=0,
            is_active=True,
        )
        self.session.add(slot)
        await self.session.flush()

        audit_service = AuditService(self.session)
        await audit_service.record(
            context=context,
            action="schedules.create_slot",
            resource_type="schedule_slot",
            resource_id=slot.id,
            request=request,
            metadata={"job_id": payload.job_id},
        )

        await self.session.commit()
        await self.session.refresh(slot)
        return slot

    async def list_slots(self, *, job_id: str | None = None, context: AuthContext | None = None) -> list[SlotView]:
        query = select(ScheduleSlot).where(ScheduleSlot.is_active.is_(True)).order_by(ScheduleSlot.start_at.asc())
        if job_id:
            query = query.where(ScheduleSlot.job_id == job_id)
        result = await self.session.scalars(query)

        slot_views = [self._slot_entity_to_view(slot) for slot in result]

        if job_id:
            job = await self.session.get(Job, job_id)
            if job is not None:
                slot_views.extend(self._build_virtual_slots_for_job(job=job, existing_slots=slot_views))

        if context and context.role == UserRole.CANDIDATE:
            now = utcnow()
            minimum_start_time = now + self._candidate_booking_lead_time
            slot_views = [slot for slot in slot_views if slot.start_at > minimum_start_time]

        slot_views.sort(key=lambda item: item.start_at)
        return slot_views

    async def invite_candidate(
        self,
        *,
        job_id: str,
        payload: InviteCandidateRequest,
        context: AuthContext,
        request: Request | None,
    ) -> InterviewSchedule:
        job = await self.session.get(Job, job_id)
        if job is None:
            raise ApiError(status_code=404, code="job_not_found", message="Job was not found.")

        if context.role == UserRole.PROJECT_MANAGER and job.manager_user_id != context.user_id:
            raise ApiError(status_code=403, code="forbidden_job_access", message="Job does not belong to the manager.")

        profile = await self._get_or_create_profile(
            email=payload.candidate_email,
            full_name=payload.candidate_name,
            user_id=payload.candidate_user_id,
        )

        schedule = InterviewSchedule(
            candidate_profile_id=profile.id,
            job_id=job_id,
            slot_id=None,
            invitation_token=secrets.token_urlsafe(32),
            status=ScheduleStatus.INVITED,
            booked_at=None,
            cancelled_at=None,
        )
        self.session.add(schedule)
        await self.session.flush()

        notification_service = NotificationService(self.session, self.settings)
        invitation_link = notification_service.build_invitation_link(
            invitation_token=schedule.invitation_token,
            candidate_email=profile.email,
            job_id=job_id,
        )
        candidate_name = profile.full_name.strip() or "Candidate"
        await notification_service.send_notification(
            recipient_email=profile.email,
            notification_type=NotificationType.L0_INVITE,
            subject=f"Interview Invitation: {job.title} at TalentOS",
            body=(
                f"Hi {candidate_name},\n\n"
                f"You have been invited to continue for the {job.title} role at TalentOS.\n"
                "Use your secure scheduling link below to choose an interview slot:\n"
                f"{invitation_link}\n\n"
                "Important:\n"
                "- This link is unique to your invited email and should not be shared.\n"
                "- Candidate access is invitation-only.\n\n"
                "Next steps after opening the link:\n"
                "1. Sign in with OTP\n"
                "2. Complete face registration/verification\n"
                "3. Book your interview slot"
            ),
            metadata={
                "job_id": job_id,
                "schedule_id": schedule.id,
                "invitation_token": schedule.invitation_token,
                "invitation_link": invitation_link,
                "headline": f"{job.title} interview invitation",
                "preheader": "Book your TalentOS L0 assessment slot.",
                "greeting_name": candidate_name,
                "intro": [
                    f"You have been invited to continue for the {job.title} role at TalentOS.",
                    "Use your secure scheduling link to sign in, complete identity verification, and select an assessment slot.",
                ],
                "highlights": [
                    {"label": "Role", "value": job.title},
                    {"label": "Department", "value": job.department},
                    {"label": "Location", "value": job.location},
                ],
                "steps": [
                    "Sign in with OTP using your invited email address.",
                    "Complete face registration or face verification.",
                    "Choose an available interview slot inside the assessment window.",
                ],
                "cta_label": "Book Your Slot",
                "cta_url": invitation_link,
            },
        )

        audit_service = AuditService(self.session)
        await audit_service.record(
            context=context,
            action="schedules.invite_candidate",
            resource_type="interview_schedule",
            resource_id=schedule.id,
            request=request,
            metadata={"job_id": job_id, "candidate_email": profile.email},
        )

        await self.session.commit()
        await self.session.refresh(schedule)
        return schedule

    async def book_slot(
        self,
        *,
        payload: ScheduleBookRequest,
        context: AuthContext,
        request: Request | None,
    ) -> InterviewSchedule:
        profile = await self._resolve_profile_from_context(context)

        schedule = await self.session.scalar(
            select(InterviewSchedule).where(
                InterviewSchedule.invitation_token == payload.invitation_token,
                InterviewSchedule.candidate_profile_id == profile.id,
            )
        )
        if schedule is None:
            raise ApiError(
                status_code=404,
                code="invitation_not_found",
                message="Invitation token is invalid for this candidate.",
            )

        slot = await self._resolve_slot_for_booking(slot_id=payload.slot_id, job_id=schedule.job_id)
        if slot is None or not slot.is_active:
            raise ApiError(status_code=404, code="slot_not_found", message="Slot is not available.")

        minimum_start_time = utcnow() + self._candidate_booking_lead_time
        if slot.start_at <= minimum_start_time:
            raise ApiError(
                status_code=422,
                code="slot_too_soon",
                message="Choose a slot at least 10 minutes from now.",
            )

        if slot.reserved_count >= slot.capacity:
            raise ApiError(status_code=409, code="slot_full", message="The selected slot is already full.")

        await self._assert_no_conflict(
            candidate_profile_id=profile.id,
            slot=slot,
            ignore_schedule_id=schedule.id,
        )

        if schedule.slot_id and schedule.slot_id != slot.id:
            previous_slot = await self.session.get(ScheduleSlot, schedule.slot_id)
            if previous_slot and previous_slot.reserved_count > 0:
                previous_slot.reserved_count -= 1

        schedule.slot_id = slot.id
        schedule.status = ScheduleStatus.BOOKED
        schedule.booked_at = utcnow()
        slot.reserved_count += 1

        notification_service = NotificationService(self.session, self.settings)
        job = await self.session.get(Job, schedule.job_id)
        session_link = notification_service.build_session_link(
            invitation_token=schedule.invitation_token,
            candidate_email=profile.email,
            job_id=schedule.job_id,
            schedule_id=schedule.id,
            slot_id=slot.id,
        )
        candidate_name = profile.full_name.strip() or "Candidate"
        await notification_service.send_notification(
            recipient_email=profile.email,
            notification_type=NotificationType.SLOT_BOOKED,
            subject="Interview Slot Confirmed - TalentOS",
            body=(
                f"Hi {candidate_name},\n\n"
                "Your interview slot has been confirmed.\n"
                f"Start: {slot.start_at.isoformat()}\n"
                f"End: {slot.end_at.isoformat()}\n"
                f"Timezone: {slot.timezone}\n\n"
                "A separate L0 assessment email with the secure access link and instructions will arrive next."
            ),
            metadata={
                "schedule_id": schedule.id,
                "slot_id": slot.id,
                "invitation_token": schedule.invitation_token,
                "headline": "Your interview slot is confirmed",
                "preheader": "Your TalentOS booking is complete.",
                "greeting_name": candidate_name,
                "intro": [
                    "Your interview slot has been confirmed successfully.",
                    "Watch for the next email containing the L0 assessment link, login sequence, and proctoring instructions.",
                ],
                "highlights": [
                    {"label": "Role", "value": job.title if job else schedule.job_id},
                    {"label": "Start", "value": slot.start_at.isoformat()},
                    {"label": "Timezone", "value": slot.timezone},
                ],
            },
        )

        await notification_service.send_notification(
            recipient_email=profile.email,
            notification_type=NotificationType.L0_INSTRUCTIONS,
            subject="L0 Assessment Instructions and Access Link - TalentOS",
            body=(
                f"Hi {candidate_name},\n\n"
                "Here is your assessment interview access link for the booked slot:\n"
                f"{session_link}\n\n"
                "Booked slot:\n"
                f"Start: {slot.start_at.isoformat()}\n"
                f"End: {slot.end_at.isoformat()}\n"
                f"Timezone: {slot.timezone}\n\n"
                "Flow:\n"
                "1. Log in with OTP\n"
                "2. Complete face authentication\n"
                "3. Complete anti-spoof/liveness check\n"
                "4. Join the assessment intro and proceed through all stages until submission"
            ),
            metadata={
                "schedule_id": schedule.id,
                "slot_id": slot.id,
                "session_link": session_link,
                "job_id": schedule.job_id,
                "headline": "L0 assessment access and instructions",
                "preheader": "Use this secure link to join your TalentOS assessment.",
                "greeting_name": candidate_name,
                "intro": [
                    "This is your secure L0 assessment access email.",
                    "Open the link only during your booked slot and complete every security and proctoring step in order.",
                ],
                "highlights": [
                    {"label": "Role", "value": job.title if job else schedule.job_id},
                    {"label": "Start", "value": slot.start_at.isoformat()},
                    {"label": "End", "value": slot.end_at.isoformat()},
                    {"label": "Timezone", "value": slot.timezone},
                ],
                "steps": [
                    "Log in with OTP using the invited email address.",
                    "Complete face verification and anti-spoof/liveness checks.",
                    "Stay in full-screen mode with camera access enabled throughout the session.",
                    "Finish the intro, candidate info, aptitude, verbal, technical, coding, and summary stages in one sitting.",
                ],
                "cta_label": "Open Assessment Link",
                "cta_url": session_link,
            },
        )

        audit_service = AuditService(self.session)
        await audit_service.record(
            context=context,
            action="schedules.book_slot",
            resource_type="interview_schedule",
            resource_id=schedule.id,
            request=request,
            metadata={"slot_id": slot.id},
        )

        await self.session.commit()
        await self.session.refresh(schedule)
        return schedule

    async def reschedule_slot(
        self,
        *,
        schedule_id: str,
        payload: ScheduleRescheduleRequest,
        context: AuthContext,
        request: Request | None,
    ) -> InterviewSchedule:
        profile = await self._resolve_profile_from_context(context)
        schedule = await self.session.get(InterviewSchedule, schedule_id)
        if schedule is None or schedule.candidate_profile_id != profile.id:
            raise ApiError(status_code=404, code="schedule_not_found", message="Schedule was not found.")

        slot = await self.session.get(ScheduleSlot, payload.slot_id)
        if slot is None or not slot.is_active:
            raise ApiError(status_code=404, code="slot_not_found", message="Slot was not found.")

        await self._assert_no_conflict(candidate_profile_id=profile.id, slot=slot, ignore_schedule_id=schedule.id)

        if schedule.slot_id and schedule.slot_id != slot.id:
            old_slot = await self.session.get(ScheduleSlot, schedule.slot_id)
            if old_slot and old_slot.reserved_count > 0:
                old_slot.reserved_count -= 1

        if slot.reserved_count >= slot.capacity:
            raise ApiError(status_code=409, code="slot_full", message="The selected slot is already full.")

        schedule.slot_id = slot.id
        schedule.status = ScheduleStatus.RESCHEDULED
        schedule.booked_at = utcnow()
        slot.reserved_count += 1

        notification_service = NotificationService(self.session, self.settings)
        job = await self.session.get(Job, schedule.job_id)
        session_link = notification_service.build_session_link(
            invitation_token=schedule.invitation_token,
            candidate_email=profile.email,
            job_id=schedule.job_id,
            schedule_id=schedule.id,
            slot_id=slot.id,
        )
        await notification_service.send_notification(
            recipient_email=profile.email,
            notification_type=NotificationType.SLOT_CHANGED,
            subject="Your TalentOS L0 slot was updated",
            body=(
                "Your assessment slot has been rescheduled.\n"
                f"New start: {slot.start_at.isoformat()}\n"
                f"New end: {slot.end_at.isoformat()}\n"
                f"Timezone: {slot.timezone}"
            ),
            metadata={
                "schedule_id": schedule.id,
                "slot_id": slot.id,
                "headline": "Your L0 assessment slot was updated",
                "preheader": "Review the updated assessment time and secure link.",
                "greeting_name": profile.full_name.strip() or "Candidate",
                "intro": [
                    "Your assessment slot has been rescheduled.",
                    "Please use the refreshed secure link below and join only within the updated booking window.",
                ],
                "highlights": [
                    {"label": "Role", "value": job.title if job else schedule.job_id},
                    {"label": "New start", "value": slot.start_at.isoformat()},
                    {"label": "New end", "value": slot.end_at.isoformat()},
                    {"label": "Timezone", "value": slot.timezone},
                ],
                "cta_label": "Review Updated Link",
                "cta_url": session_link,
                "session_link": session_link,
            },
        )

        audit_service = AuditService(self.session)
        await audit_service.record(
            context=context,
            action="schedules.reschedule_slot",
            resource_type="interview_schedule",
            resource_id=schedule.id,
            request=request,
            metadata={"slot_id": slot.id},
        )

        await self.session.commit()
        await self.session.refresh(schedule)
        return schedule

    async def cancel_schedule(
        self,
        *,
        schedule_id: str,
        payload: ScheduleCancelRequest,
        context: AuthContext,
        request: Request | None,
    ) -> InterviewSchedule:
        schedule = await self.session.scalar(
            select(InterviewSchedule)
            .where(InterviewSchedule.id == schedule_id)
            .options(selectinload(InterviewSchedule.candidate_profile))
        )
        if schedule is None:
            raise ApiError(status_code=404, code="schedule_not_found", message="Schedule was not found.")

        if context.role == UserRole.CANDIDATE:
            profile = await self._resolve_profile_from_context(context)
            if schedule.candidate_profile_id != profile.id:
                raise ApiError(status_code=403, code="forbidden_schedule_access", message="Schedule does not belong to this candidate.")

        if schedule.slot_id:
            slot = await self.session.get(ScheduleSlot, schedule.slot_id)
            if slot and slot.reserved_count > 0:
                slot.reserved_count -= 1

        schedule.status = ScheduleStatus.CANCELLED
        schedule.cancelled_at = utcnow()

        notification_service = NotificationService(self.session, self.settings)
        candidate_email = schedule.candidate_profile.email if schedule.candidate_profile else None
        if candidate_email:
            await notification_service.send_notification(
                recipient_email=candidate_email,
                notification_type=NotificationType.SLOT_CHANGED,
                subject="TalentOS L0 schedule cancelled",
                body=f"Your schedule has been cancelled. Reason: {payload.reason}",
                metadata={
                    "schedule_id": schedule.id,
                    "reason": payload.reason,
                    "headline": "Your TalentOS assessment was cancelled",
                    "preheader": "Your booked slot is no longer active.",
                    "greeting_name": (
                        schedule.candidate_profile.full_name.strip()
                        if schedule.candidate_profile and schedule.candidate_profile.full_name
                        else "Candidate"
                    ),
                    "intro": [
                        "Your booked TalentOS assessment has been cancelled.",
                        f"Reason: {payload.reason}",
                    ],
                },
            )

        audit_service = AuditService(self.session)
        await audit_service.record(
            context=context,
            action="schedules.cancel",
            resource_type="interview_schedule",
            resource_id=schedule.id,
            request=request,
            metadata={"reason": payload.reason},
        )

        await self.session.commit()
        await self.session.refresh(schedule)
        return schedule

    async def list_candidate_schedules(self, *, context: AuthContext) -> list[CandidateScheduleView]:
        profile = await self._resolve_profile_from_context(context)
        records = await self.session.scalars(
            select(InterviewSchedule)
            .where(InterviewSchedule.candidate_profile_id == profile.id)
            .options(selectinload(InterviewSchedule.slot))
            .order_by(InterviewSchedule.created_at.desc())
        )

        output: list[CandidateScheduleView] = []
        for schedule in records:
            slot = schedule.slot
            if slot is None:
                continue
            output.append(
                CandidateScheduleView(
                    schedule_id=schedule.id,
                    job_id=schedule.job_id,
                    slot_id=slot.id,
                    candidate_name=profile.full_name.strip() if profile.full_name else None,
                    slot_start_at=slot.start_at,
                    slot_end_at=slot.end_at,
                    timezone=slot.timezone,
                    status=schedule.status,
                )
            )
        return output

    async def validate_candidate_invitation(
        self,
        *,
        invitation_token: str,
        candidate_email: str,
        flow: str = "invite",
        schedule_id: str | None = None,
        slot_id: str | None = None,
    ) -> CandidateInvitationValidation:
        token = invitation_token.strip()
        normalized_email = candidate_email.strip().lower()
        normalized_flow = flow.strip().lower() or "invite"

        if not token or not normalized_email:
            return CandidateInvitationValidation(
                valid=False,
                candidate_email=None,
                schedule_status=None,
                job_id=None,
                schedule_id=None,
                slot_id=None,
            )

        schedule = await self.session.scalar(
            select(InterviewSchedule)
            .where(InterviewSchedule.invitation_token == token)
            .options(
                selectinload(InterviewSchedule.candidate_profile),
                selectinload(InterviewSchedule.assessment_sessions),
            )
        )
        if schedule is None or schedule.candidate_profile is None:
            return CandidateInvitationValidation(
                valid=False,
                candidate_email=None,
                schedule_status=None,
                job_id=None,
                schedule_id=None,
                slot_id=None,
            )

        matched_email = schedule.candidate_profile.email.strip().lower()
        if normalized_flow == "l0_session":
            allowed_statuses = {ScheduleStatus.BOOKED, ScheduleStatus.RESCHEDULED}
        else:
            allowed_statuses = {
                ScheduleStatus.INVITED,
                ScheduleStatus.BOOKED,
                ScheduleStatus.RESCHEDULED,
            }

        latest_assessment = None
        if schedule.assessment_sessions:
            latest_assessment = max(schedule.assessment_sessions, key=lambda item: item.created_at)
        latest_metadata = (
            latest_assessment.session_metadata
            if latest_assessment and isinstance(latest_assessment.session_metadata, dict)
            else {}
        )
        session_access_revoked = bool(latest_metadata.get("session_access_revoked"))
        latest_session_terminal = bool(
            latest_assessment
            and latest_assessment.status.value in {"FINISHED", "TERMINATED", "CANCELLED"}
        )

        schedule_id_matches = not schedule_id or schedule.id == schedule_id
        slot_id_matches = not slot_id or schedule.slot_id == slot_id
        flow_is_active = not (
            normalized_flow == "l0_session"
            and (session_access_revoked or latest_session_terminal or not schedule.slot_id)
        )
        is_valid = (
            matched_email == normalized_email
            and schedule.status in allowed_statuses
            and schedule_id_matches
            and slot_id_matches
            and flow_is_active
        )

        return CandidateInvitationValidation(
            valid=is_valid,
            candidate_email=matched_email,
            schedule_status=schedule.status,
            job_id=schedule.job_id,
            schedule_id=schedule.id,
            slot_id=schedule.slot_id,
        )

    async def _assert_no_conflict(
        self,
        *,
        candidate_profile_id: str,
        slot: ScheduleSlot,
        ignore_schedule_id: str,
    ) -> None:
        conflicting = await self.session.scalars(
            select(InterviewSchedule)
            .where(
                InterviewSchedule.candidate_profile_id == candidate_profile_id,
                InterviewSchedule.id != ignore_schedule_id,
                InterviewSchedule.status.in_([ScheduleStatus.BOOKED, ScheduleStatus.RESCHEDULED]),
                InterviewSchedule.slot_id.is_not(None),
            )
            .options(selectinload(InterviewSchedule.slot))
        )

        for schedule in conflicting:
            existing_slot = schedule.slot
            if existing_slot is None:
                continue
            overlaps = existing_slot.start_at < slot.end_at and slot.start_at < existing_slot.end_at
            if overlaps:
                raise ApiError(
                    status_code=409,
                    code="schedule_conflict",
                    message="Selected slot conflicts with another booked schedule.",
                )

    async def _resolve_slot_for_booking(self, *, slot_id: str, job_id: str) -> ScheduleSlot | None:
        slot = await self.session.get(ScheduleSlot, slot_id)
        if slot is not None:
            return slot

        if not slot_id.startswith("virtual:"):
            return None

        virtual = self._decode_virtual_slot_id(slot_id)
        if virtual is None:
            return None
        if virtual.job_id != job_id:
            raise ApiError(
                status_code=403,
                code="slot_job_mismatch",
                message="The selected slot does not belong to this job invitation.",
            )

        job = await self.session.get(Job, virtual.job_id)
        if job is None:
            return None

        window = self._resolve_assessment_window(job)
        if window is not None:
            window_start, window_end, _, _ = window
            if virtual.start_at < window_start or virtual.end_at > window_end:
                raise ApiError(
                    status_code=422,
                    code="slot_outside_assessment_window",
                    message="Selected slot is outside the JD assessment window.",
                )

        existing = await self.session.scalar(
            select(ScheduleSlot).where(
                and_(
                    ScheduleSlot.job_id == virtual.job_id,
                    ScheduleSlot.start_at == virtual.start_at,
                    ScheduleSlot.end_at == virtual.end_at,
                    ScheduleSlot.timezone == virtual.timezone,
                    ScheduleSlot.is_active.is_(True),
                )
            )
        )
        if existing is not None:
            return existing

        created = ScheduleSlot(
            job_id=virtual.job_id,
            start_at=virtual.start_at,
            end_at=virtual.end_at,
            timezone=virtual.timezone,
            capacity=virtual.capacity,
            reserved_count=0,
            is_active=True,
        )
        self.session.add(created)
        await self.session.flush()
        return created

    def _slot_entity_to_view(self, slot: ScheduleSlot) -> SlotView:
        return SlotView(
            id=slot.id,
            job_id=slot.job_id,
            start_at=slot.start_at,
            end_at=slot.end_at,
            timezone=slot.timezone,
            capacity=slot.capacity,
            reserved_count=slot.reserved_count,
            is_active=slot.is_active,
        )

    def _build_virtual_slots_for_job(self, *, job: Job, existing_slots: list[SlotView]) -> list[SlotView]:
        window = self._resolve_assessment_window(job)
        if window is None:
            return []

        start_at, end_at, timezone_name, slot_minutes = window
        if end_at <= start_at:
            return []

        existing_keys = {
            (slot.start_at.isoformat(), slot.end_at.isoformat(), slot.timezone)
            for slot in existing_slots
        }

        cursor = max(start_at, utcnow())
        step = timedelta(minutes=slot_minutes)
        virtual_slots: list[SlotView] = []

        # Prevent accidental unbounded virtual slot generation from malformed windows.
        max_slots = 1000
        while cursor < end_at and len(virtual_slots) < max_slots:
            slot_end = min(cursor + step, end_at)
            key = (cursor.isoformat(), slot_end.isoformat(), timezone_name)
            if key not in existing_keys:
                virtual_slots.append(
                    SlotView(
                        id=self._encode_virtual_slot_id(
                            job_id=job.id,
                            start_at=cursor,
                            end_at=slot_end,
                            timezone_name=timezone_name,
                            capacity=1,
                        ),
                        job_id=job.id,
                        start_at=cursor,
                        end_at=slot_end,
                        timezone=timezone_name,
                        capacity=1,
                        reserved_count=0,
                        is_active=True,
                    )
                )
            cursor += step

        return virtual_slots

    def _resolve_assessment_window(self, job: Job) -> tuple[datetime, datetime, str, int] | None:
        if job.assessment_start_at and job.assessment_end_at and job.assessment_end_at > job.assessment_start_at:
            return (
                job.assessment_start_at,
                job.assessment_end_at,
                job.assessment_timezone or "UTC",
                max(5, min(int(job.assessment_slot_minutes or 30), 180)),
            )

        return self._extract_assessment_window(job.jd_text)

    def _extract_assessment_window(self, jd_text: str) -> tuple[datetime, datetime, str, int] | None:
        if not jd_text:
            return None

        block_match = self._window_block_re.search(jd_text)
        if block_match is None:
            return None

        parsed: dict[str, str] = {}
        for raw_line in block_match.group("body").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if "=" in line:
                key, value = line.split("=", 1)
            elif ":" in line:
                key, value = line.split(":", 1)
            else:
                continue
            parsed[key.strip().lower()] = value.strip()

        start_raw = parsed.get("start") or parsed.get("assessment_start") or parsed.get("assessment_window_start")
        end_raw = parsed.get("end") or parsed.get("assessment_end") or parsed.get("assessment_window_end")
        if not start_raw or not end_raw:
            return None

        start_at = self._parse_window_datetime(start_raw)
        end_at = self._parse_window_datetime(end_raw)
        if start_at is None or end_at is None or end_at <= start_at:
            return None

        timezone_name = parsed.get("timezone") or parsed.get("assessment_timezone") or "UTC"

        slot_minutes_raw = parsed.get("slot_minutes") or parsed.get("assessment_slot_minutes")
        slot_minutes = 30
        if slot_minutes_raw:
            try:
                slot_minutes = int(slot_minutes_raw)
            except ValueError:
                slot_minutes = 30
        slot_minutes = max(5, min(slot_minutes, 180))

        return start_at, end_at, timezone_name, slot_minutes

    @staticmethod
    def _parse_window_datetime(value: str) -> datetime | None:
        normalized = value.strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None

        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed

    def _encode_virtual_slot_id(
        self,
        *,
        job_id: str,
        start_at: datetime,
        end_at: datetime,
        timezone_name: str,
        capacity: int,
    ) -> str:
        payload = {
            "job_id": job_id,
            "start_at": start_at.isoformat(),
            "end_at": end_at.isoformat(),
            "timezone": timezone_name,
            "capacity": capacity,
        }
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        encoded = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
        return f"virtual:{encoded}"

    def _decode_virtual_slot_id(self, slot_id: str) -> SlotView | None:
        encoded = slot_id.removeprefix("virtual:").strip()
        if not encoded:
            return None
        padding = (4 - (len(encoded) % 4)) % 4
        encoded = encoded + ("=" * padding)

        try:
            raw = base64.urlsafe_b64decode(encoded.encode("ascii"))
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            return None

        if not isinstance(payload, dict):
            return None

        start_at = self._parse_window_datetime(str(payload.get("start_at") or ""))
        end_at = self._parse_window_datetime(str(payload.get("end_at") or ""))
        if start_at is None or end_at is None:
            return None

        timezone_name = str(payload.get("timezone") or "UTC")
        capacity_value = payload.get("capacity")
        try:
            capacity = int(capacity_value)
        except (TypeError, ValueError):
            capacity = 1
        capacity = max(1, min(capacity, 20))

        job_id = str(payload.get("job_id") or "")
        if not job_id:
            return None

        return SlotView(
            id=slot_id,
            job_id=job_id,
            start_at=start_at,
            end_at=end_at,
            timezone=timezone_name,
            capacity=capacity,
            reserved_count=0,
            is_active=True,
        )

    async def _get_or_create_profile(
        self,
        *,
        email: str,
        full_name: str,
        user_id: str | None,
    ) -> CandidateProfile:
        normalized_email = email.strip().lower()
        existing = await self.session.scalar(
            select(CandidateProfile).where(CandidateProfile.email == normalized_email)
        )
        if existing is not None:
            if user_id and existing.user_id.startswith("pending:"):
                existing.user_id = user_id
            if full_name and existing.full_name != full_name:
                existing.full_name = full_name
            return existing

        profile = CandidateProfile(
            user_id=user_id or f"pending:{normalized_email}",
            email=normalized_email,
            full_name=full_name,
            timezone="UTC",
            profile_completeness=0.45,
            onboarding_status="invited",
        )
        self.session.add(profile)
        await self.session.flush()
        return profile

    async def _resolve_profile_from_context(self, context: AuthContext) -> CandidateProfile:
        profile = await self.session.scalar(
            select(CandidateProfile).where(CandidateProfile.user_id == context.user_id)
        )
        if profile is not None:
            return profile

        if context.email:
            profile = await self.session.scalar(
                select(CandidateProfile).where(CandidateProfile.email == context.email.lower())
            )
            if profile is not None:
                profile.user_id = context.user_id
                profile.onboarding_status = "active"
                await self.session.flush()
                return profile

        raise ApiError(
            status_code=404,
            code="candidate_profile_not_found",
            message="Candidate profile was not found for this user.",
        )

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.exceptions import ApiError
from app.models.entities import AssessmentSession, CandidateProfile, InterviewSchedule, Job, Notification, ScheduleSlot
from app.models.enums import AssessmentStatus, JobStatus, NotificationType, ScheduleStatus
from app.schemas.scheduling import ScheduleBookRequest
from app.services.scheduling_service import SchedulingService


async def test_scheduling_conflict_detection(db_session, candidate_context):
    job = Job(
        manager_user_id="manager-001",
        title="Platform Engineer",
        department="Engineering",
        location="Remote",
        employment_type="full_time",
        seniority="mid",
        status=JobStatus.ACTIVE,
        description="Platform engineering role",
        jd_text="Need cloud, CI/CD, observability.",
    )
    db_session.add(job)

    profile = CandidateProfile(
        user_id=candidate_context.user_id,
        email=candidate_context.email,
        full_name="Candidate One",
        timezone="UTC",
        profile_completeness=0.7,
        onboarding_status="active",
    )
    db_session.add(profile)
    await db_session.flush()

    slot_a = ScheduleSlot(
        job_id=job.id,
        start_at=datetime.fromisoformat("2026-04-20T10:00:00+00:00"),
        end_at=datetime.fromisoformat("2026-04-20T10:30:00+00:00"),
        timezone="UTC",
        capacity=1,
        reserved_count=0,
        is_active=True,
    )
    slot_b = ScheduleSlot(
        job_id=job.id,
        start_at=datetime.fromisoformat("2026-04-20T10:15:00+00:00"),
        end_at=datetime.fromisoformat("2026-04-20T10:45:00+00:00"),
        timezone="UTC",
        capacity=1,
        reserved_count=0,
        is_active=True,
    )
    db_session.add_all([slot_a, slot_b])
    await db_session.flush()

    invite_a = InterviewSchedule(
        candidate_profile_id=profile.id,
        job_id=job.id,
        slot_id=None,
        invitation_token="token-a",
        status=ScheduleStatus.INVITED,
        booked_at=None,
        cancelled_at=None,
    )
    invite_b = InterviewSchedule(
        candidate_profile_id=profile.id,
        job_id=job.id,
        slot_id=None,
        invitation_token="token-b",
        status=ScheduleStatus.INVITED,
        booked_at=None,
        cancelled_at=None,
    )
    db_session.add_all([invite_a, invite_b])
    await db_session.commit()

    service = SchedulingService(db_session)

    booked = await service.book_slot(
        payload=ScheduleBookRequest(invitation_token="token-a", slot_id=slot_a.id),
        context=candidate_context,
        request=None,
    )
    assert booked.status == ScheduleStatus.BOOKED

    with pytest.raises(ApiError) as exc:
        await service.book_slot(
            payload=ScheduleBookRequest(invitation_token="token-b", slot_id=slot_b.id),
            context=candidate_context,
            request=None,
        )

    assert exc.value.code == "schedule_conflict"

    slot_a_db = await db_session.scalar(select(ScheduleSlot).where(ScheduleSlot.id == slot_a.id))
    assert slot_a_db is not None
    assert slot_a_db.reserved_count == 1

    notifications = list(await db_session.scalars(select(Notification)))
    assert any(item.notification_type == NotificationType.SLOT_BOOKED for item in notifications)
    assert any(item.notification_type == NotificationType.L0_INSTRUCTIONS for item in notifications)
    instructions_notice = next(item for item in notifications if item.notification_type == NotificationType.L0_INSTRUCTIONS)
    metadata = instructions_notice.notification_metadata or {}
    assert "session_link" in metadata
    assert "/auth/candidate/access?session=" in str(metadata["session_link"])


async def test_virtual_slots_are_generated_and_bookable_from_jd_window(db_session, candidate_context):
    window_start = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    window_end = window_start + timedelta(hours=3)

    job = Job(
        manager_user_id="manager-001",
        title="Backend Engineer",
        department="Engineering",
        location="Remote",
        employment_type="full_time",
        seniority="mid",
        status=JobStatus.ACTIVE,
        description="Backend role",
        jd_text=(
            "Role details\n\n"
            "[ASSESSMENT_WINDOW]\n"
            f"start={window_start.isoformat()}\n"
            f"end={window_end.isoformat()}\n"
            "timezone=UTC\n"
            "slot_minutes=60\n"
            "[/ASSESSMENT_WINDOW]"
        ),
    )
    db_session.add(job)

    profile = CandidateProfile(
        user_id=candidate_context.user_id,
        email=candidate_context.email,
        full_name="Candidate Two",
        timezone="UTC",
        profile_completeness=0.8,
        onboarding_status="active",
    )
    db_session.add(profile)
    await db_session.flush()

    invite = InterviewSchedule(
        candidate_profile_id=profile.id,
        job_id=job.id,
        slot_id=None,
        invitation_token="token-virtual",
        status=ScheduleStatus.INVITED,
        booked_at=None,
        cancelled_at=None,
    )
    db_session.add(invite)
    await db_session.commit()

    service = SchedulingService(db_session)
    slots = await service.list_slots(job_id=job.id, context=candidate_context)
    virtual_slots = [slot for slot in slots if slot.id.startswith("virtual:")]
    assert len(virtual_slots) >= 1

    booked = await service.book_slot(
        payload=ScheduleBookRequest(invitation_token="token-virtual", slot_id=virtual_slots[0].id),
        context=candidate_context,
        request=None,
    )
    assert booked.status == ScheduleStatus.BOOKED

    persisted_slot = await db_session.get(ScheduleSlot, booked.slot_id)
    assert persisted_slot is not None
    assert persisted_slot.job_id == job.id
    assert persisted_slot.reserved_count == 1


async def test_virtual_slots_can_use_structured_assessment_window(db_session, candidate_context):
    window_start = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) + timedelta(hours=2)
    window_end = window_start + timedelta(hours=2)

    job = Job(
        manager_user_id="manager-001",
        title="Data Engineer",
        department="Engineering",
        location="Remote",
        employment_type="full_time",
        seniority="mid",
        status=JobStatus.ACTIVE,
        description="Data role",
        jd_text="Need Python, SQL, and pipelines.",
        assessment_start_at=window_start,
        assessment_end_at=window_end,
        assessment_timezone="UTC",
        assessment_slot_minutes=45,
    )
    db_session.add(job)

    profile = CandidateProfile(
        user_id=candidate_context.user_id,
        email=candidate_context.email,
        full_name="Candidate Structured",
        timezone="UTC",
        profile_completeness=0.8,
        onboarding_status="active",
    )
    db_session.add(profile)
    await db_session.flush()

    invite = InterviewSchedule(
        candidate_profile_id=profile.id,
        job_id=job.id,
        slot_id=None,
        invitation_token="token-structured",
        status=ScheduleStatus.INVITED,
        booked_at=None,
        cancelled_at=None,
    )
    db_session.add(invite)
    await db_session.commit()

    service = SchedulingService(db_session)
    slots = await service.list_slots(job_id=job.id, context=candidate_context)
    assert any(slot.id.startswith("virtual:") for slot in slots)


async def test_candidate_cannot_view_or_book_slots_too_soon(db_session, candidate_context, monkeypatch):
    from app.services import scheduling_service as scheduling_module

    now = datetime(2026, 4, 9, 10, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(scheduling_module, "utcnow", lambda: now)

    job = Job(
        manager_user_id="manager-001",
        title="QA Engineer",
        department="Engineering",
        location="Remote",
        employment_type="full_time",
        seniority="mid",
        status=JobStatus.ACTIVE,
        description="QA role",
        jd_text="Need test automation and API validation.",
    )
    db_session.add(job)

    profile = CandidateProfile(
        user_id=candidate_context.user_id,
        email=candidate_context.email,
        full_name="Candidate Three",
        timezone="UTC",
        profile_completeness=0.75,
        onboarding_status="active",
    )
    db_session.add(profile)
    await db_session.flush()

    too_soon_slot = ScheduleSlot(
        job_id=job.id,
        start_at=now + timedelta(minutes=5),
        end_at=now + timedelta(minutes=35),
        timezone="UTC",
        capacity=1,
        reserved_count=0,
        is_active=True,
    )
    valid_slot = ScheduleSlot(
        job_id=job.id,
        start_at=now + timedelta(minutes=25),
        end_at=now + timedelta(minutes=55),
        timezone="UTC",
        capacity=1,
        reserved_count=0,
        is_active=True,
    )
    db_session.add_all([too_soon_slot, valid_slot])
    await db_session.flush()

    invite_too_soon = InterviewSchedule(
        candidate_profile_id=profile.id,
        job_id=job.id,
        slot_id=None,
        invitation_token="token-too-soon",
        status=ScheduleStatus.INVITED,
        booked_at=None,
        cancelled_at=None,
    )
    invite_valid = InterviewSchedule(
        candidate_profile_id=profile.id,
        job_id=job.id,
        slot_id=None,
        invitation_token="token-valid",
        status=ScheduleStatus.INVITED,
        booked_at=None,
        cancelled_at=None,
    )
    db_session.add_all([invite_too_soon, invite_valid])
    await db_session.commit()

    service = SchedulingService(db_session)

    visible_slots = await service.list_slots(job_id=job.id, context=candidate_context)
    visible_slot_ids = {slot.id for slot in visible_slots}
    assert valid_slot.id in visible_slot_ids
    assert too_soon_slot.id not in visible_slot_ids

    with pytest.raises(ApiError) as exc:
        await service.book_slot(
            payload=ScheduleBookRequest(invitation_token="token-too-soon", slot_id=too_soon_slot.id),
            context=candidate_context,
            request=None,
        )

    assert exc.value.code == "slot_too_soon"

    booked = await service.book_slot(
        payload=ScheduleBookRequest(invitation_token="token-valid", slot_id=valid_slot.id),
        context=candidate_context,
        request=None,
    )
    assert booked.status == ScheduleStatus.BOOKED


async def test_validate_candidate_invitation_accepts_matching_active_invite(db_session):
    job = Job(
        manager_user_id="manager-001",
        title="Infra Engineer",
        department="Engineering",
        location="Remote",
        employment_type="full_time",
        seniority="mid",
        status=JobStatus.ACTIVE,
        description="Infra role",
        jd_text="Need cloud and automation.",
    )
    db_session.add(job)

    profile = CandidateProfile(
        user_id="pending:candidate@example.com",
        email="candidate@example.com",
        full_name="Candidate Validation",
        timezone="UTC",
        profile_completeness=0.5,
        onboarding_status="invited",
    )
    db_session.add(profile)
    await db_session.flush()

    schedule = InterviewSchedule(
        candidate_profile_id=profile.id,
        job_id=job.id,
        slot_id=None,
        invitation_token="invite-validation-token",
        status=ScheduleStatus.INVITED,
        booked_at=None,
        cancelled_at=None,
    )
    db_session.add(schedule)
    await db_session.commit()

    service = SchedulingService(db_session)
    result = await service.validate_candidate_invitation(
        invitation_token="invite-validation-token",
        candidate_email="candidate@example.com",
    )

    assert result.valid is True
    assert result.candidate_email == "candidate@example.com"
    assert result.schedule_status == ScheduleStatus.INVITED
    assert result.job_id == job.id
    assert result.schedule_id == schedule.id


async def test_validate_candidate_invitation_rejects_email_mismatch_and_cancelled_status(db_session):
    job = Job(
        manager_user_id="manager-001",
        title="QA Analyst",
        department="Engineering",
        location="Remote",
        employment_type="full_time",
        seniority="junior",
        status=JobStatus.ACTIVE,
        description="QA role",
        jd_text="Need testing fundamentals.",
    )
    db_session.add(job)

    profile = CandidateProfile(
        user_id="pending:another@example.com",
        email="another@example.com",
        full_name="Another Candidate",
        timezone="UTC",
        profile_completeness=0.5,
        onboarding_status="invited",
    )
    db_session.add(profile)
    await db_session.flush()

    schedule = InterviewSchedule(
        candidate_profile_id=profile.id,
        job_id=job.id,
        slot_id=None,
        invitation_token="cancelled-token",
        status=ScheduleStatus.CANCELLED,
        booked_at=None,
        cancelled_at=datetime.now(timezone.utc),
    )
    db_session.add(schedule)
    await db_session.commit()

    service = SchedulingService(db_session)

    mismatch_result = await service.validate_candidate_invitation(
        invitation_token="cancelled-token",
        candidate_email="wrong@example.com",
    )
    assert mismatch_result.valid is False
    assert mismatch_result.schedule_status == ScheduleStatus.CANCELLED

    cancelled_result = await service.validate_candidate_invitation(
        invitation_token="cancelled-token",
        candidate_email="another@example.com",
    )
    assert cancelled_result.valid is False
    assert cancelled_result.schedule_status == ScheduleStatus.CANCELLED


async def test_validate_candidate_invitation_rejects_revoked_l0_session_link(db_session):
    job = Job(
        manager_user_id="manager-001",
        title="AI Ops Engineer",
        department="Engineering",
        location="Remote",
        employment_type="full_time",
        seniority="mid",
        status=JobStatus.ACTIVE,
        description="AI ops role",
        jd_text="Need Python and observability.",
    )
    db_session.add(job)

    profile = CandidateProfile(
        user_id="pending:candidate@example.com",
        email="candidate@example.com",
        full_name="Candidate Revoked",
        timezone="UTC",
        profile_completeness=0.5,
        onboarding_status="invited",
    )
    db_session.add(profile)
    await db_session.flush()

    schedule = InterviewSchedule(
        candidate_profile_id=profile.id,
        job_id=job.id,
        slot_id="slot-revoked",
        invitation_token="revoked-session-token",
        status=ScheduleStatus.BOOKED,
        booked_at=datetime.now(timezone.utc),
        cancelled_at=None,
    )
    db_session.add(schedule)
    await db_session.flush()

    session_record = AssessmentSession(
        candidate_profile_id=profile.id,
        interview_schedule_id=schedule.id,
        job_id=job.id,
        room_id="room-revoked",
        status=AssessmentStatus.TERMINATED,
        anti_spoof_session_id=None,
        heartbeat_at=None,
        started_at=None,
        ended_at=datetime.now(timezone.utc),
        integrity_score=78.0,
        session_metadata={"session_access_revoked": True, "termination_reason": "Tab switching"},
    )
    db_session.add(session_record)
    await db_session.commit()

    service = SchedulingService(db_session)
    result = await service.validate_candidate_invitation(
        invitation_token="revoked-session-token",
        candidate_email="candidate@example.com",
        flow="l0_session",
        schedule_id=schedule.id,
        slot_id="slot-revoked",
    )

    assert result.valid is False
    assert result.schedule_status == ScheduleStatus.BOOKED
    assert result.schedule_id == schedule.id

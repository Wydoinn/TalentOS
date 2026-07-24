from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from app.models.entities import InterviewSchedule, Job, Notification
from app.models.enums import JobStatus, MatchStatus, NotificationType
from app.schemas.jobs import RankingRequest
from app.services.ranking_service import RankingService


@dataclass
class StubATSClient:
    response_payload: dict

    async def run_resume_check(self, payload: dict) -> dict:
        _ = payload
        return self.response_payload


async def test_ranking_service_auto_invites_top_candidates(db_session, manager_context):
    job = Job(
        manager_user_id=manager_context.user_id,
        title="Senior Backend Engineer",
        department="Engineering",
        location="Remote",
        employment_type="full_time",
        seniority="senior",
        status=JobStatus.ACTIVE,
        description="Build distributed backend systems",
        jd_text="Need Python, FastAPI, PostgreSQL, and system design experience.",
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    ats_response = {
        "report_run_id": "run_001",
        "results": [
            {
                "candidate_id": "cand_1",
                "candidate_name": "Alice Johnson",
                "candidate_email": "alice@example.com",
                "rank": 1,
                "final_score": 91.2,
                "ats_score": 88.0,
                "reasons": ["Strong Python", "Solid backend architecture"],
            },
            {
                "candidate_id": "cand_2",
                "candidate_name": "Bob Smith",
                "candidate_email": "bob@example.com",
                "rank": 2,
                "final_score": 86.5,
                "ats_score": 82.0,
                "reasons": ["Good API design"],
            },
            {
                "candidate_id": "cand_3",
                "candidate_name": "No Email",
                "candidate_email": None,
                "rank": 3,
                "final_score": 80.0,
                "ats_score": 77.0,
                "reasons": ["Missing contact email"],
            },
        ],
    }

    service = RankingService(
        db_session,
        ats_client=StubATSClient(ats_response),
    )

    outcome = await service.run_ranking(
        job=job,
        payload=RankingRequest(top_n=2),
        context=manager_context,
        request=None,
    )

    assert outcome.ranking_result.report_run_id == "run_001"
    assert outcome.ranking_result.total_candidates == 3
    assert outcome.ranking_result.invited_top_n == 2

    invited = [match for match in outcome.matches if match.status == MatchStatus.INVITED]
    assert len(invited) == 2
    assert invited[0].candidate_email == "alice@example.com"
    assert invited[1].candidate_email == "bob@example.com"

    schedules = list(await db_session.scalars(select(InterviewSchedule)))
    assert len(schedules) == 2

    notifications = list(await db_session.scalars(select(Notification)))
    assert len(notifications) == 2
    assert all(item.notification_type == NotificationType.L0_INVITE for item in notifications)
    assert all("invitation_link" in (item.notification_metadata or {}) for item in notifications)
    expected_invite_prefix = (
        f"{service.settings.candidate_portal_base_url.rstrip('/')}/auth/candidate/access?invite="
    )
    assert all(
        str((item.notification_metadata or {}).get("invitation_link", "")).startswith(
            expected_invite_prefix
        )
        for item in notifications
    )

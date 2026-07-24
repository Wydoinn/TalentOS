from __future__ import annotations

from app.models.entities import CandidateMatch, Job, RankingResult
from app.models.enums import JobStatus, MatchStatus
from app.routes.jobs import list_job_candidates, update_candidate_status
from app.schemas.jobs import CandidateStatusUpdateRequest


async def test_update_candidate_status_route_persists_match_status(db_session, manager_context):
    job = Job(
        manager_user_id=manager_context.user_id,
        title="Frontend Engineer",
        department="Engineering",
        location="Remote",
        employment_type="full_time",
        seniority="mid",
        status=JobStatus.ACTIVE,
        description="Build candidate-facing web experiences.",
        jd_text="Need Angular, TypeScript, accessibility, and API integration experience.",
    )
    db_session.add(job)
    await db_session.flush()

    ranking = RankingResult(
        job_id=job.id,
        report_run_id="report-run-1",
        total_candidates=1,
        invited_top_n=0,
        ranking_payload={},
    )
    db_session.add(ranking)
    await db_session.flush()

    match = CandidateMatch(
        ranking_result_id=ranking.id,
        candidate_profile_id=None,
        candidate_external_id="cand-001",
        candidate_name="Taylor Candidate",
        candidate_email="taylor@example.com",
        rank=1,
        final_score=89.0,
        ats_score=85.5,
        status=MatchStatus.MATCHED,
        explanation="Strong Angular and UI architecture depth.",
    )
    db_session.add(match)
    await db_session.commit()

    response = await update_candidate_status(
        job_id=job.id,
        match_id=match.id,
        payload=CandidateStatusUpdateRequest(status=MatchStatus.SHORTLISTED),
        request=None,
        context=manager_context,
        session=db_session,
    )

    assert response.status == MatchStatus.SHORTLISTED

    refreshed = await db_session.get(CandidateMatch, match.id)
    assert refreshed is not None
    assert refreshed.status == MatchStatus.SHORTLISTED


async def test_list_job_candidates_uses_ranking_payload_when_matches_are_missing(db_session, manager_context):
    job = Job(
        manager_user_id=manager_context.user_id,
        title="React Developer",
        department="Engineering",
        location="Remote",
        employment_type="full_time",
        seniority="mid",
        status=JobStatus.ACTIVE,
        description="Build modern UI experiences.",
        jd_text="Need React, TypeScript, state management, and component architecture experience.",
    )
    db_session.add(job)
    await db_session.flush()

    ranking = RankingResult(
        job_id=job.id,
        report_run_id="report-run-2",
        total_candidates=1,
        invited_top_n=0,
        ranking_payload={
            "results": [
                {
                    "candidate_id": "cand-react-1",
                    "candidate_name": "Priya React",
                    "candidate_email": "priya@example.com",
                    "source": "external",
                    "final_score": 91.0,
                    "ats_score": 88.0,
                    "explanation": "Strong React fundamentals and component design depth.",
                }
            ]
        },
    )
    db_session.add(ranking)
    await db_session.commit()

    response = await list_job_candidates(
        job_id=job.id,
        context=manager_context,
        session=db_session,
    )

    assert len(response.candidates) == 1
    assert response.candidates[0].candidate_external_id == "cand-react-1"
    assert response.candidates[0].candidate_name == "Priya React"
    assert response.candidates[0].source == "external"
    assert response.candidates[0].status == MatchStatus.MATCHED

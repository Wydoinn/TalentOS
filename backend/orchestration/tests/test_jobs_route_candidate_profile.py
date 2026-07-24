from __future__ import annotations

from app.models.entities import CandidateMatch, Job, RankingResult, ResumeAnalysis
from app.models.enums import JobStatus, MatchStatus
from app.routes.jobs import get_candidate_profile_ai


async def test_get_candidate_profile_ai_returns_resume_analysis_details(db_session, manager_context):
    job = Job(
        manager_user_id=manager_context.user_id,
        title="Backend Engineer",
        department="Engineering",
        location="Remote",
        employment_type="full_time",
        seniority="mid",
        status=JobStatus.ACTIVE,
        description="Build backend systems.",
        jd_text="Need Python, FastAPI, SQL, and distributed systems experience.",
    )
    db_session.add(job)
    await db_session.flush()

    ranking = RankingResult(
        job_id=job.id,
        report_run_id="run-777",
        total_candidates=1,
        invited_top_n=0,
        ranking_payload={},
    )
    db_session.add(ranking)
    await db_session.flush()

    match = CandidateMatch(
        ranking_result_id=ranking.id,
        candidate_profile_id=None,
        candidate_external_id="cand-777",
        candidate_name="Jordan Candidate",
        candidate_email="jordan@example.com",
        rank=1,
        final_score=90.0,
        ats_score=86.0,
        status=MatchStatus.MATCHED,
        explanation="Strong backend API design | Solid SQL fundamentals",
    )
    db_session.add(match)

    analysis = ResumeAnalysis(
        job_id=job.id,
        candidate_external_id="cand-777",
        candidate_email="jordan@example.com",
        report_run_id="run-777",
        final_score=90.0,
        ats_score=86.0,
        reasons=["Strong backend API design", "Solid SQL fundamentals"],
        raw_payload={
            "summary": "Strong fit for backend API and systems work.",
            "llm_summary": "Candidate demonstrates strong backend engineering depth with production API experience.",
            "reasons": ["Strong backend API design", "Solid SQL fundamentals"],
            "suggestions": ["Probe distributed tracing knowledge in interview."],
            "issues": ["No public cloud certification listed."],
            "matched_keywords": ["Python", "FastAPI", "SQL"],
            "missing_keywords": ["Kubernetes"],
            "source": "internal",
            "current_title": "Software Engineer",
            "relative_path": "internal/jordan-candidate.pdf",
            "sections": {"skills": True, "experience": True, "projects": True, "education": True},
            "formatting_signals": {"two_column_layout": False},
            "projects": [{"name": "API Platform", "impact": "Scaled backend APIs"}],
            "education": [{"degree": "B.Tech", "institution": "ABC University"}],
            "experience": [{"role": "Software Engineer", "company": "Example Co"}],
            "generated_at": "2026-04-10T09:00:00+00:00",
        },
    )
    db_session.add(analysis)
    await db_session.commit()

    response = await get_candidate_profile_ai(
        job_id=job.id,
        match_id=match.id,
        context=manager_context,
        session=db_session,
    )

    assert response.candidate_external_id == "cand-777"
    assert response.candidate_name == "Jordan Candidate"
    assert response.summary == "Strong fit for backend API and systems work."
    assert response.llm_summary == "Candidate demonstrates strong backend engineering depth with production API experience."
    assert response.reasons == ["Strong backend API design", "Solid SQL fundamentals"]
    assert response.suggestions == ["Probe distributed tracing knowledge in interview."]
    assert response.issues == ["No public cloud certification listed."]
    assert response.matched_keywords == ["Python", "FastAPI", "SQL"]
    assert response.missing_keywords == ["Kubernetes"]
    assert response.source == "internal"
    assert response.current_title == "Software Engineer"
    assert response.relative_path == "internal/jordan-candidate.pdf"
    assert response.gemini_summary is not None
    assert response.projects == [{"name": "API Platform", "impact": "Scaled backend APIs"}]
    assert response.education == [{"degree": "B.Tech", "institution": "ABC University"}]
    assert response.experience_timeline == [{"role": "Software Engineer", "company": "Example Co"}]
    assert response.sections == {"skills": True, "experience": True, "projects": True, "education": True}
    assert response.formatting_signals == {"two_column_layout": False}
    assert response.signals["final_score"] == 90.0
    assert response.signals["ats_score"] == 86.0
    assert response.generated_at is not None


async def test_get_candidate_profile_ai_falls_back_to_candidate_external_id(db_session, manager_context):
    job = Job(
        manager_user_id=manager_context.user_id,
        title="Platform Engineer",
        department="Engineering",
        location="Remote",
        employment_type="full_time",
        seniority="mid",
        status=JobStatus.ACTIVE,
        description="Build platform tooling.",
        jd_text="Need Python, CI/CD, Kubernetes, and cloud fundamentals.",
    )
    db_session.add(job)
    await db_session.flush()

    ranking = RankingResult(
        job_id=job.id,
        report_run_id="run-888",
        total_candidates=1,
        invited_top_n=0,
        ranking_payload={},
    )
    db_session.add(ranking)
    await db_session.flush()

    match = CandidateMatch(
        ranking_result_id=ranking.id,
        candidate_profile_id=None,
        candidate_external_id="cand-888",
        candidate_name="Alex Engineer",
        candidate_email="alex@example.com",
        rank=1,
        final_score=87.0,
        ats_score=84.0,
        status=MatchStatus.MATCHED,
        explanation="Strong CI/CD background | Solid cloud understanding",
    )
    db_session.add(match)

    analysis = ResumeAnalysis(
        job_id=job.id,
        candidate_external_id="cand-888",
        candidate_email="alex@example.com",
        report_run_id="run-888",
        final_score=87.0,
        ats_score=84.0,
        reasons=["Strong CI/CD background"],
        raw_payload={
            "summary": "Candidate has strong platform engineering potential.",
            "reasons": ["Strong CI/CD background"],
        },
    )
    db_session.add(analysis)
    await db_session.commit()

    response = await get_candidate_profile_ai(
        job_id=job.id,
        match_id="missing-match-id",
        candidate_external_id="cand-888",
        context=manager_context,
        session=db_session,
    )

    assert response.candidate_external_id == "cand-888"
    assert response.summary == "Candidate has strong platform engineering potential."
    assert response.reasons == ["Strong CI/CD background"]
    assert response.gemini_summary is not None

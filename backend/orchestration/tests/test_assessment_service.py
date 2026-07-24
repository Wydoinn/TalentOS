from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.core.exceptions import ApiError
from app.models.entities import AssessmentSession, CandidateProfile, Job
from app.models.enums import AssessmentStage, AssessmentStatus, DecisionOutcome, JobStatus
from app.schemas.assessment import (
    AnswerSubmitRequest,
    AssessmentFinishRequest,
    AssessmentSessionCreateRequest,
    ProctoringEventIngestRequest,
    QuestionGenerateForSessionRequest,
)
from app.services.assessment_service import AssessmentService


@dataclass
class StubGeminiService:
    captured_resume: str | None = None

    async def generate_questions(
        self,
        *,
        jd: str,
        resume: str,
        stage: AssessmentStage,
        role_seniority: str,
        previous_answers: list[str],
        count: int,
    ):
        _ = jd, stage, role_seniority, previous_answers
        self.captured_resume = resume
        return type(
            "StubQuestionResult",
            (),
            {
                "questions": [
                    {
                        "prompt": f"Question {index}",
                        "rubric": {"key_points": ["clarity", "depth"], "weight": 1.0},
                    }
                    for index in range(1, count + 1)
                ],
                "model": "stub-gemini",
                "fallback_used": False,
            },
        )()

    async def evaluate_answer(self, *, question: str, answer: str, rubric: dict):
        _ = question, answer, rubric
        return type(
            "StubEvaluationResult",
            (),
            {
                "score": 82.0,
                "confidence": 0.88,
                "classification": "pass",
                "reasons": ["Strong answer quality."],
                "model": "stub-gemini",
                "fallback_used": False,
            },
        )()


@dataclass
class StubAntiSpoofClient:
    async def create_session(self, *, candidate_id: str, job_id: str | None):
        _ = candidate_id, job_id
        return {"session_id": "anti-session-1", "access_token": "anti-token-1"}

    async def get_session(self, *, session_id: str, access_token: str):
        _ = session_id, access_token
        return {
            "status": "review_ready",
            "final_decision": "PASS",
            "latest_result": {"overall_status": "PASS"},
        }


@dataclass
class StubAntiSpoofUnavailable:
    async def create_session(self, *, candidate_id: str, job_id: str | None):
        _ = candidate_id, job_id
        return None


@dataclass
class StubAntiSpoofStateful:
    payload: dict

    async def create_session(self, *, candidate_id: str, job_id: str | None):
        _ = candidate_id, job_id
        return {"session_id": "anti-session-1", "access_token": "anti-token-1"}

    async def get_session(self, *, session_id: str, access_token: str):
        _ = session_id, access_token
        return self.payload


async def test_assessment_session_report_generation(db_session, manager_context):
    job = Job(
        manager_user_id=manager_context.user_id,
        title="AI Engineer",
        department="Engineering",
        location="Remote",
        employment_type="full_time",
        seniority="senior",
        status=JobStatus.ACTIVE,
        description="Build AI interview systems",
        jd_text="Need Python, LLM evaluation, APIs, and system design.",
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    service = AssessmentService(db_session)
    service.anti_spoof = StubAntiSpoofClient()
    service.gemini = StubGeminiService()

    created = await service.create_session(
        payload=AssessmentSessionCreateRequest(
            job_id=job.id,
            candidate_email="candidate@example.com",
            interview_schedule_id=None,
        ),
        context=manager_context,
        request=None,
    )

    assert created.status == AssessmentStatus.CREATED

    joined = await service.join_session(session_id=created.id, context=manager_context, request=None)
    assert joined.status == AssessmentStatus.JOINED

    questions = await service.generate_questions(
        session_id=created.id,
        payload=QuestionGenerateForSessionRequest(
            stage=AssessmentStage.TECHNICAL,
            jd_context=job.jd_text,
            resume_context="Candidate built scalable APIs and model serving systems.",
            role_seniority="senior",
            previous_answers=[],
            count=2,
        ),
        context=manager_context,
    )
    assert len(questions) == 2

    answer = await service.submit_answer(
        session_id=created.id,
        payload=AnswerSubmitRequest(
            question_id=questions[0].id,
            answer_text="I used FastAPI and async workers to scale to 10k RPM with observability.",
            answer_transcript=None,
        ),
        context=manager_context,
    )
    assert answer.score is not None

    event = await service.ingest_proctor_event(
        session_id=created.id,
        payload=ProctoringEventIngestRequest(
            event_type="TAB_SWITCH",
            severity="WARNING",
            payload={"duration_ms": 1200},
        ),
        context=manager_context,
    )
    assert event.event_type == "TAB_SWITCH"

    report = await service.finish_session(
        session_id=created.id,
        payload=AssessmentFinishRequest(),
        context=manager_context,
        request=None,
    )

    assert report.overall_score >= 0
    assert report.summary

    session_record = await db_session.get(AssessmentSession, created.id)
    assert session_record is not None
    assert session_record.status == AssessmentStatus.FINISHED


async def test_candidate_assessment_requires_anti_spoof(db_session, candidate_context):
    job = Job(
        manager_user_id="manager-001",
        title="ML Engineer",
        department="Engineering",
        location="Remote",
        employment_type="full_time",
        seniority="mid",
        status=JobStatus.ACTIVE,
        description="Build ML services",
        jd_text="Need Python and APIs.",
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    service = AssessmentService(db_session)
    service.anti_spoof = StubAntiSpoofUnavailable()
    service.gemini = StubGeminiService()

    with pytest.raises(ApiError) as exc:
        await service.create_session(
            payload=AssessmentSessionCreateRequest(
                job_id=job.id,
                candidate_email=candidate_context.email or "candidate@example.com",
                interview_schedule_id=None,
            ),
            context=candidate_context,
            request=None,
        )

    assert exc.value.code == "anti_spoof_unavailable"


async def test_candidate_questions_blocked_until_anti_spoof_passed(db_session, candidate_context):
    job = Job(
        manager_user_id="manager-001",
        title="Backend Engineer",
        department="Engineering",
        location="Remote",
        employment_type="full_time",
        seniority="mid",
        status=JobStatus.ACTIVE,
        description="Build backend services",
        jd_text="Need Python and distributed systems experience.",
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    anti_spoof = StubAntiSpoofStateful(
        payload={
            "status": "challenged",
            "final_decision": None,
            "latest_result": {"overall_status": "PENDING"},
        }
    )

    service = AssessmentService(db_session)
    service.anti_spoof = anti_spoof
    service.gemini = StubGeminiService()

    created = await service.create_session(
        payload=AssessmentSessionCreateRequest(
            job_id=job.id,
            candidate_email=candidate_context.email or "candidate@example.com",
            interview_schedule_id=None,
        ),
        context=candidate_context,
        request=None,
    )

    with pytest.raises(ApiError) as blocked:
        await service.generate_questions(
            session_id=created.id,
            payload=QuestionGenerateForSessionRequest(
                stage=AssessmentStage.APTITUDE,
                jd_context=job.jd_text,
                resume_context="Candidate has Python and backend experience.",
                role_seniority="mid",
                previous_answers=[],
                count=1,
            ),
            context=candidate_context,
        )

    assert blocked.value.code == "anti_spoof_required"

    anti_spoof.payload = {
        "status": "review_ready",
        "final_decision": "PASS",
        "latest_result": {"overall_status": "PASS"},
    }

    generated = await service.generate_questions(
        session_id=created.id,
        payload=QuestionGenerateForSessionRequest(
            stage=AssessmentStage.TECHNICAL,
            jd_context=job.jd_text,
            resume_context="Candidate has Python and backend experience.",
            role_seniority="mid",
            previous_answers=[],
            count=1,
        ),
        context=candidate_context,
    )

    assert len(generated) == 1


async def test_generate_questions_uses_candidate_name_instead_of_email(db_session, manager_context):
    job = Job(
        manager_user_id=manager_context.user_id,
        title="Frontend Engineer",
        department="Engineering",
        location="Remote",
        employment_type="full_time",
        seniority="mid",
        status=JobStatus.ACTIVE,
        description="Build candidate-facing interview experiences",
        jd_text="Need Angular, TypeScript, and product thinking.",
    )
    profile = CandidateProfile(
        user_id="candidate-123",
        email="priya.narayan@example.com",
        full_name="Priya Krishnan",
        timezone="UTC",
        profile_completeness=0.8,
        onboarding_status="active",
    )
    db_session.add(job)
    db_session.add(profile)
    await db_session.commit()
    await db_session.refresh(job)

    gemini = StubGeminiService()
    service = AssessmentService(db_session)
    service.anti_spoof = StubAntiSpoofClient()
    service.gemini = gemini

    created = await service.create_session(
        payload=AssessmentSessionCreateRequest(
            job_id=job.id,
            candidate_email="priya.narayan@example.com",
            interview_schedule_id=None,
        ),
        context=manager_context,
        request=None,
    )

    questions = await service.generate_questions(
        session_id=created.id,
        payload=QuestionGenerateForSessionRequest(
            stage=AssessmentStage.INTRO,
            jd_context=job.jd_text,
            resume_context="Candidate email: priya.narayan@example.com. Assessment context generated from scheduled interview.",
            role_seniority="mid",
            previous_answers=[],
            count=1,
        ),
        context=manager_context,
    )

    assert len(questions) == 1
    assert gemini.captured_resume is not None
    assert "Candidate name: Priya Krishnan." in gemini.captured_resume
    assert "Candidate email: priya.narayan@example.com" not in gemini.captured_resume
    assert "[redacted-email]" in gemini.captured_resume


async def test_proctoring_terminates_after_three_warnings(db_session, manager_context):
    job = Job(
        manager_user_id=manager_context.user_id,
        title="Security Engineer",
        department="Engineering",
        location="Remote",
        employment_type="full_time",
        seniority="mid",
        status=JobStatus.ACTIVE,
        description="Run secure assessment workflows",
        jd_text="Need security fundamentals, Python, and incident analysis.",
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    service = AssessmentService(db_session)
    service.anti_spoof = StubAntiSpoofClient()

    created = await service.create_session(
        payload=AssessmentSessionCreateRequest(
            job_id=job.id,
            candidate_email="candidate@example.com",
            interview_schedule_id=None,
        ),
        context=manager_context,
        request=None,
    )

    for _ in range(3):
        await service.ingest_proctor_event(
            session_id=created.id,
            payload=ProctoringEventIngestRequest(
                event_type="TAB_SWITCH",
                severity="WARNING",
                payload={"duration_ms": 1500},
            ),
            context=manager_context,
        )

    session_record = await db_session.get(AssessmentSession, created.id)
    assert session_record is not None
    assert session_record.status == AssessmentStatus.TERMINATED

    report = await service.get_report(session_id=created.id)
    assert report.decision == DecisionOutcome.FAIL
    assert report.termination_reason is not None
    assert report.proctor_summary
    assert report.question_results == []


async def test_gaze_warnings_do_not_terminate_session(db_session, manager_context):
    job = Job(
        manager_user_id=manager_context.user_id,
        title="QA Engineer",
        department="Engineering",
        location="Remote",
        employment_type="full_time",
        seniority="mid",
        status=JobStatus.ACTIVE,
        description="Review assessments",
        jd_text="Need attention to detail and communication.",
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    service = AssessmentService(db_session)
    service.anti_spoof = StubAntiSpoofClient()
    service.gemini = StubGeminiService()

    created = await service.create_session(
        payload=AssessmentSessionCreateRequest(
            job_id=job.id,
            candidate_email="candidate@example.com",
            interview_schedule_id=None,
        ),
        context=manager_context,
        request=None,
    )

    for _ in range(5):
        await service.ingest_proctor_event(
            session_id=created.id,
            payload=ProctoringEventIngestRequest(
                event_type="gaze_away",
                severity="WARNING",
                payload={"normalized_offset": 0.31},
            ),
            context=manager_context,
        )

    session_record = await db_session.get(AssessmentSession, created.id)
    assert session_record is not None
    assert session_record.status != AssessmentStatus.TERMINATED


async def test_multiple_faces_terminates_immediately(db_session, manager_context):
    job = Job(
        manager_user_id=manager_context.user_id,
        title="Support Engineer",
        department="Operations",
        location="Remote",
        employment_type="full_time",
        seniority="mid",
        status=JobStatus.ACTIVE,
        description="Support candidate operations",
        jd_text="Need communication and process discipline.",
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    service = AssessmentService(db_session)
    service.anti_spoof = StubAntiSpoofClient()
    service.gemini = StubGeminiService()

    created = await service.create_session(
        payload=AssessmentSessionCreateRequest(
            job_id=job.id,
            candidate_email="candidate@example.com",
            interview_schedule_id=None,
        ),
        context=manager_context,
        request=None,
    )

    await service.ingest_proctor_event(
        session_id=created.id,
        payload=ProctoringEventIngestRequest(
            event_type="multiple_faces",
            severity="CRITICAL",
            payload={"face_count": 2},
        ),
        context=manager_context,
    )

    session_record = await db_session.get(AssessmentSession, created.id)
    assert session_record is not None
    assert session_record.status == AssessmentStatus.TERMINATED

from __future__ import annotations

from collections import Counter
import re
from typing import Any
from statistics import mean
from uuid import uuid4

from fastapi import Request
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings, get_settings
from app.core.exceptions import ApiError
from app.core.security import AuthContext
from app.models.base import utcnow
from app.models.entities import (
    AssessmentAnswer,
    AssessmentQuestion,
    AssessmentReport,
    AssessmentSession,
    CandidateMatch,
    CandidateProfile,
    InterviewSchedule,
    Job,
    ProctoringEvent,
    RankingResult,
)
from app.models.enums import (
    AssessmentStage,
    AssessmentStatus,
    DecisionOutcome,
    MatchStatus,
    NotificationType,
    ProctoringSeverity,
    QuestionSource,
    ScheduleStatus,
    UserRole,
)
from app.schemas.assessment import (
    AnswerSubmitRequest,
    AssessmentFinishRequest,
    AssessmentSessionCreateRequest,
    ProctoringEventIngestRequest,
    QuestionGenerateForSessionRequest,
)
from app.services.anti_spoofing_client import AntiSpoofingClient
from app.services.anti_spoofing_client import AntiSpoofingClientError
from app.services.audit_service import AuditService
from app.services.gemini_service import GeminiService
from app.services.notification_service import NotificationService
from app.services.speech_transcription_service import SpeechTranscriptionService
from app.services.vision_analysis_service import VisionAnalysisService


class AssessmentService:
    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.gemini = GeminiService(self.settings)
        self.anti_spoof = AntiSpoofingClient(self.settings)
        self.speech = SpeechTranscriptionService(self.settings)
        self.vision = VisionAnalysisService()

    async def create_session(
        self,
        *,
        payload: AssessmentSessionCreateRequest,
        context: AuthContext,
        request: Request | None,
    ) -> AssessmentSession:
        job = await self.session.get(Job, payload.job_id)
        if job is None:
            raise ApiError(status_code=404, code="job_not_found", message="Job was not found.")

        if context.role == UserRole.PROJECT_MANAGER and job.manager_user_id != context.user_id:
            raise ApiError(status_code=403, code="forbidden_job_access", message="Managers can only manage their jobs.")

        profile = await self._resolve_or_create_candidate_profile(
            email=payload.candidate_email,
            user_id=context.user_id if context.role == UserRole.CANDIDATE else None,
            default_name="Candidate",
        )

        interview_schedule = None
        if payload.interview_schedule_id:
            interview_schedule = await self.session.get(InterviewSchedule, payload.interview_schedule_id)
            if interview_schedule is None:
                raise ApiError(status_code=404, code="schedule_not_found", message="Schedule was not found.")
            if interview_schedule.candidate_profile_id != profile.id:
                raise ApiError(status_code=403, code="schedule_profile_mismatch", message="Schedule does not belong to candidate profile.")
            if interview_schedule.status not in {ScheduleStatus.BOOKED, ScheduleStatus.RESCHEDULED}:
                raise ApiError(status_code=409, code="schedule_not_booked", message="Schedule must be booked before assessment starts.")

        try:
            anti_spoof_data = await self.anti_spoof.create_session(candidate_id=profile.id, job_id=payload.job_id)
        except AntiSpoofingClientError as exc:
            raise ApiError(
                status_code=exc.status_code,
                code="anti_spoof_unavailable",
                message=exc.message,
            ) from exc
        anti_spoof_session_id = None
        if anti_spoof_data and isinstance(anti_spoof_data, dict):
            anti_spoof_session_id = str(anti_spoof_data.get("session_id") or "") or None

        if context.role == UserRole.CANDIDATE and not anti_spoof_session_id:
            raise ApiError(
                status_code=503,
                code="anti_spoof_unavailable",
                message="Anti-spoof verification is unavailable. Please try again in a few minutes.",
            )

        assessment_session = AssessmentSession(
            candidate_profile_id=profile.id,
            interview_schedule_id=interview_schedule.id if interview_schedule else None,
            job_id=payload.job_id,
            room_id=f"room-{uuid4().hex[:12]}",
            status=AssessmentStatus.CREATED,
            anti_spoof_session_id=anti_spoof_session_id,
            heartbeat_at=None,
            started_at=None,
            ended_at=None,
            integrity_score=100.0,
            session_metadata={
                "anti_spoof": anti_spoof_data or {},
                "job_title": job.title,
                "question_blueprint": list(job.question_blueprint or []),
                "session_access_revoked": False,
            },
        )
        self.session.add(assessment_session)
        await self.session.flush()

        audit_service = AuditService(self.session)
        await audit_service.record(
            context=context,
            action="assessment.create_session",
            resource_type="assessment_session",
            resource_id=assessment_session.id,
            request=request,
            metadata={"job_id": payload.job_id},
        )

        await self.session.commit()
        await self.session.refresh(assessment_session)
        return assessment_session

    async def join_session(
        self,
        *,
        session_id: str,
        context: AuthContext,
        request: Request | None,
    ) -> AssessmentSession:
        assessment_session = await self._get_assessment_session(session_id)
        self._assert_session_allows_activity(assessment_session)
        if context.role == UserRole.CANDIDATE:
            await self._validate_candidate_access(context, assessment_session)

        assessment_session.status = AssessmentStatus.JOINED
        assessment_session.started_at = assessment_session.started_at or utcnow()
        assessment_session.heartbeat_at = utcnow()

        audit_service = AuditService(self.session)
        await audit_service.record(
            context=context,
            action="assessment.join_session",
            resource_type="assessment_session",
            resource_id=session_id,
            request=request,
        )

        await self.session.commit()
        await self.session.refresh(assessment_session)
        return assessment_session

    async def heartbeat(
        self,
        *,
        session_id: str,
        status: AssessmentStatus,
        context: AuthContext,
    ) -> AssessmentSession:
        assessment_session = await self._get_assessment_session(session_id)
        self._assert_session_allows_activity(assessment_session)
        if context.role == UserRole.CANDIDATE:
            await self._validate_candidate_access(context, assessment_session)

        assessment_session.status = status
        assessment_session.heartbeat_at = utcnow()
        await self.session.commit()
        await self.session.refresh(assessment_session)
        return assessment_session

    async def get_anti_spoof_status(
        self,
        *,
        session_id: str,
        context: AuthContext,
    ) -> dict[str, Any]:
        assessment_session = await self._get_assessment_session(session_id)
        self._assert_session_allows_activity(assessment_session)
        if context.role == UserRole.CANDIDATE:
            await self._validate_candidate_access(context, assessment_session)

        anti_spoof_session_id, anti_spoof_token = self._anti_spoof_credentials(assessment_session)
        if not anti_spoof_session_id or not anti_spoof_token:
            raise ApiError(
                status_code=409,
                code="anti_spoof_missing",
                message="Anti-spoof session is not initialized for this assessment.",
            )

        try:
            payload = await self.anti_spoof.get_session(
                session_id=anti_spoof_session_id,
                access_token=anti_spoof_token,
            )
        except AntiSpoofingClientError as exc:
            raise ApiError(
                status_code=exc.status_code,
                code="anti_spoof_unavailable",
                message=exc.message,
            ) from exc

        self._persist_anti_spoof_snapshot(assessment_session, payload)
        await self.session.commit()
        return payload

    async def issue_anti_spoof_challenge(
        self,
        *,
        session_id: str,
        context: AuthContext,
        challenge_type: str | None = None,
    ) -> dict[str, Any]:
        assessment_session = await self._get_assessment_session(session_id)
        self._assert_session_allows_activity(assessment_session)
        if context.role == UserRole.CANDIDATE:
            await self._validate_candidate_access(context, assessment_session)

        anti_spoof_session_id, anti_spoof_token = self._anti_spoof_credentials(assessment_session)
        if not anti_spoof_session_id or not anti_spoof_token:
            raise ApiError(
                status_code=409,
                code="anti_spoof_missing",
                message="Anti-spoof session is not initialized for this assessment.",
            )

        try:
            payload = await self.anti_spoof.issue_challenge(
                session_id=anti_spoof_session_id,
                access_token=anti_spoof_token,
                challenge_type=challenge_type,
            )
        except AntiSpoofingClientError as exc:
            raise ApiError(
                status_code=exc.status_code,
                code="anti_spoof_unavailable",
                message=exc.message,
            ) from exc

        return payload

    async def analyze_anti_spoof(
        self,
        *,
        session_id: str,
        context: AuthContext,
        video_bytes: bytes,
        filename: str,
        content_type: str,
    ) -> dict[str, Any]:
        assessment_session = await self._get_assessment_session(session_id)
        self._assert_session_allows_activity(assessment_session)
        if context.role == UserRole.CANDIDATE:
            await self._validate_candidate_access(context, assessment_session)

        anti_spoof_session_id, anti_spoof_token = self._anti_spoof_credentials(assessment_session)
        if not anti_spoof_session_id or not anti_spoof_token:
            raise ApiError(
                status_code=409,
                code="anti_spoof_missing",
                message="Anti-spoof session is not initialized for this assessment.",
            )

        try:
            payload = await self.anti_spoof.analyze(
                session_id=anti_spoof_session_id,
                access_token=anti_spoof_token,
                video_bytes=video_bytes,
                filename=filename,
                content_type=content_type,
            )
        except AntiSpoofingClientError as exc:
            raise ApiError(
                status_code=exc.status_code,
                code="anti_spoof_unavailable",
                message=exc.message,
            ) from exc

        return payload

    async def finalize_anti_spoof(
        self,
        *,
        session_id: str,
        context: AuthContext,
    ) -> dict[str, Any]:
        assessment_session = await self._get_assessment_session(session_id)
        self._assert_session_allows_activity(assessment_session)
        if context.role == UserRole.CANDIDATE:
            await self._validate_candidate_access(context, assessment_session)

        anti_spoof_session_id, anti_spoof_token = self._anti_spoof_credentials(assessment_session)
        if not anti_spoof_session_id or not anti_spoof_token:
            raise ApiError(
                status_code=409,
                code="anti_spoof_missing",
                message="Anti-spoof session is not initialized for this assessment.",
            )

        try:
            payload = await self.anti_spoof.finalize(
                session_id=anti_spoof_session_id,
                access_token=anti_spoof_token,
            )
        except AntiSpoofingClientError as exc:
            raise ApiError(
                status_code=exc.status_code,
                code="anti_spoof_unavailable",
                message=exc.message,
            ) from exc

        self._persist_anti_spoof_snapshot(assessment_session, payload)
        await self.session.commit()
        return payload

    async def generate_questions(
        self,
        *,
        session_id: str,
        payload: QuestionGenerateForSessionRequest,
        context: AuthContext,
    ) -> list[AssessmentQuestion]:
        assessment_session = await self._get_assessment_session(session_id)
        self._assert_session_allows_activity(assessment_session)
        if context.role == UserRole.CANDIDATE:
            await self._validate_candidate_access(context, assessment_session)
            await self._ensure_anti_spoof_passed(assessment_session=assessment_session)

        resume_context = await self._build_assessment_resume_context(
            assessment_session=assessment_session,
            raw_resume_context=payload.resume_context,
        )
        result = await self.gemini.generate_questions(
            jd=payload.jd_context,
            resume=resume_context,
            stage=payload.stage,
            role_seniority=payload.role_seniority,
            previous_answers=payload.previous_answers,
            count=payload.count,
        )

        saved_questions: list[AssessmentQuestion] = []
        for index, item in enumerate(result.questions, start=1):
            question = AssessmentQuestion(
                assessment_session_id=assessment_session.id,
                stage=payload.stage,
                prompt=str(item.get("prompt") or "Question"),
                rubric=item.get("rubric") if isinstance(item.get("rubric"), dict) else {},
                source=QuestionSource.GEMINI,
                sequence_no=index,
            )
            self.session.add(question)
            saved_questions.append(question)

        await self.session.commit()
        for question in saved_questions:
            await self.session.refresh(question)
        return saved_questions

    async def submit_answer(
        self,
        *,
        session_id: str,
        payload: AnswerSubmitRequest,
        context: AuthContext,
    ) -> AssessmentAnswer:
        assessment_session = await self._get_assessment_session(session_id)
        self._assert_session_allows_activity(assessment_session)
        if context.role == UserRole.CANDIDATE:
            await self._validate_candidate_access(context, assessment_session)
            await self._ensure_anti_spoof_passed(assessment_session=assessment_session)

        question = await self.session.get(AssessmentQuestion, payload.question_id)
        if question is None or question.assessment_session_id != session_id:
            raise ApiError(status_code=404, code="question_not_found", message="Question was not found for this session.")

        evaluation = await self.gemini.evaluate_answer(
            question=question.prompt,
            answer=payload.answer_text,
            rubric=question.rubric,
        )

        answer = AssessmentAnswer(
            assessment_session_id=session_id,
            question_id=question.id,
            answer_text=payload.answer_text,
            answer_transcript=payload.answer_transcript,
            score=evaluation.score,
            confidence=evaluation.confidence,
            is_off_topic=evaluation.classification == "fail" and evaluation.score < 40,
            evaluation={
                "classification": evaluation.classification,
                "reasons": evaluation.reasons,
                "model": evaluation.model,
                "fallback_used": False,
                "transcription_model": payload.transcription_model,
            },
        )
        self.session.add(answer)
        await self.session.commit()
        await self.session.refresh(answer)
        return answer

    async def transcribe_answer_audio(
        self,
        *,
        session_id: str,
        context: AuthContext,
        audio_bytes: bytes,
    ) -> dict[str, Any]:
        assessment_session = await self._get_assessment_session(session_id)
        self._assert_session_allows_activity(assessment_session)
        if context.role == UserRole.CANDIDATE:
            await self._validate_candidate_access(context, assessment_session)
            await self._ensure_anti_spoof_passed(assessment_session=assessment_session)

        return await self.speech.transcribe_audio_bytes(audio_bytes)

    async def analyze_vision_frame(
        self,
        *,
        session_id: str,
        context: AuthContext,
        image_bytes: bytes,
    ) -> dict[str, Any]:
        assessment_session = await self._get_assessment_session(session_id)
        self._assert_session_allows_activity(assessment_session)
        if context.role == UserRole.CANDIDATE:
            await self._validate_candidate_access(context, assessment_session)
            await self._ensure_anti_spoof_passed(assessment_session=assessment_session)

        return await self.vision.analyze_frame(image_bytes)

    async def ingest_proctor_event(
        self,
        *,
        session_id: str,
        payload: ProctoringEventIngestRequest,
        context: AuthContext,
    ) -> ProctoringEvent:
        assessment_session = await self._get_assessment_session(session_id)
        self._assert_session_allows_activity(assessment_session)
        if context.role == UserRole.CANDIDATE:
            await self._validate_candidate_access(context, assessment_session)

        event = ProctoringEvent(
            assessment_session_id=session_id,
            event_type=payload.event_type,
            severity=payload.severity,
            event_timestamp=payload.event_timestamp or utcnow(),
            payload=payload.payload,
        )
        self.session.add(event)

        penalty_map = {
            ProctoringSeverity.INFO: 0.5,
            ProctoringSeverity.WARNING: 2.5,
            ProctoringSeverity.CRITICAL: 8.0,
        }
        assessment_session.integrity_score = max(
            0.0,
            assessment_session.integrity_score - penalty_map[payload.severity],
        )

        metadata = self._session_metadata(assessment_session)
        proctor_counts = metadata.get("proctor_counts")
        if not isinstance(proctor_counts, dict):
            proctor_counts = {"info": 0, "warning": 0, "critical": 0}

        event_counts = metadata.get("proctor_event_counts")
        if not isinstance(event_counts, dict):
            event_counts = {}

        normalized_event_type = self._normalize_proctor_event(payload.event_type)
        severity_key = payload.severity.value.lower()
        proctor_counts[severity_key] = int(proctor_counts.get(severity_key) or 0) + 1
        event_counts[normalized_event_type] = int(event_counts.get(normalized_event_type) or 0) + 1
        metadata["proctor_counts"] = proctor_counts
        metadata["proctor_event_counts"] = event_counts
        metadata["last_proctor_event"] = {
            "event_type": payload.event_type,
            "severity": payload.severity.value,
            "timestamp": (payload.event_timestamp or utcnow()).isoformat(),
            "payload": payload.payload,
        }

        policy = self._resolve_proctor_policy(
            event_type=normalized_event_type,
            severity=payload.severity,
            event_count=int(event_counts.get(normalized_event_type) or 0),
            warning_count=int(proctor_counts.get("warning") or 0),
            critical_count=int(proctor_counts.get("critical") or 0),
        )
        metadata["last_proctor_policy"] = policy

        should_terminate = bool(policy.get("should_terminate"))
        if should_terminate:
            termination_reason = str(policy.get("termination_reason") or self._build_termination_reason(event_type=normalized_event_type))
            metadata["termination_reason"] = termination_reason
            metadata["session_access_revoked"] = True
            metadata["link_invalidated_at"] = utcnow().isoformat()
            assessment_session.status = AssessmentStatus.TERMINATED
            assessment_session.ended_at = assessment_session.ended_at or utcnow()
            assessment_session.session_metadata = metadata
            report = await self._upsert_report(
                assessment_session=assessment_session,
                force_decision=DecisionOutcome.FAIL,
                termination_reason=termination_reason,
            )
            await self._sync_candidate_match_status_from_report(
                assessment_session=assessment_session,
                report=report,
            )
            await self._send_result_notification(
                assessment_session=assessment_session,
                report=report,
            )
        else:
            assessment_session.session_metadata = metadata

        await self.session.commit()
        await self.session.refresh(event)
        return event

    async def finish_session(
        self,
        *,
        session_id: str,
        payload: AssessmentFinishRequest,
        context: AuthContext,
        request: Request | None,
    ) -> AssessmentReport:
        assessment_session = await self._get_assessment_session(session_id)
        if context.role == UserRole.CANDIDATE:
            await self._validate_candidate_access(context, assessment_session)
            if assessment_session.status != AssessmentStatus.TERMINATED:
                await self._ensure_anti_spoof_passed(assessment_session=assessment_session)

        report = await self._upsert_report(
            assessment_session=assessment_session,
            force_decision=payload.force_decision,
            termination_reason=self._read_termination_reason(assessment_session),
        )
        await self._sync_candidate_match_status_from_report(
            assessment_session=assessment_session,
            report=report,
        )

        metadata = self._session_metadata(assessment_session)
        metadata["session_access_revoked"] = True
        metadata["completed_at"] = utcnow().isoformat()
        assessment_session.session_metadata = metadata

        if assessment_session.status != AssessmentStatus.TERMINATED:
            assessment_session.status = AssessmentStatus.FINISHED
            assessment_session.ended_at = utcnow()

        await self._send_result_notification(
            assessment_session=assessment_session,
            report=report,
        )

        audit_service = AuditService(self.session)
        await audit_service.record(
            context=context,
            action="assessment.finish_session",
            resource_type="assessment_session",
            resource_id=session_id,
            request=request,
            metadata={"decision": report.decision.value, "overall_score": report.overall_score},
        )

        await self.session.commit()
        await self.session.refresh(report)
        return report

    async def get_report(self, *, session_id: str, context: AuthContext | None = None) -> AssessmentReport:
        assessment_session = await self._get_assessment_session(session_id)
        if context is not None:
            if context.role == UserRole.CANDIDATE:
                await self._validate_candidate_access(context, assessment_session)
            elif context.role == UserRole.PROJECT_MANAGER:
                job = await self.session.get(Job, assessment_session.job_id)
                if job is None or job.manager_user_id != context.user_id:
                    raise ApiError(status_code=403, code="forbidden_report_access", message="Managers can only view reports for their own jobs.")

        report = await self.session.scalar(
            select(AssessmentReport).where(AssessmentReport.assessment_session_id == session_id)
        )
        if report is None:
            if assessment_session.status == AssessmentStatus.TERMINATED:
                report = await self._upsert_report(
                    assessment_session=assessment_session,
                    force_decision=DecisionOutcome.FAIL,
                    termination_reason=self._read_termination_reason(assessment_session),
                )
                await self.session.commit()
        if report is None:
            raise ApiError(status_code=404, code="report_not_found", message="Assessment report was not found.")
        return report

    async def list_manager_report_summaries(
        self,
        *,
        context: AuthContext,
        job_id: str | None = None,
        candidate_email: str | None = None,
    ) -> list[dict[str, Any]]:
        if context.role != UserRole.PROJECT_MANAGER:
            raise ApiError(status_code=403, code="forbidden_report_access", message="Only managers can view assessment reports.")

        query = (
            select(AssessmentSession, CandidateProfile, Job, AssessmentReport)
            .join(CandidateProfile, CandidateProfile.id == AssessmentSession.candidate_profile_id)
            .join(Job, Job.id == AssessmentSession.job_id)
            .outerjoin(AssessmentReport, AssessmentReport.assessment_session_id == AssessmentSession.id)
            .where(Job.manager_user_id == context.user_id)
            .order_by(AssessmentSession.created_at.desc())
        )

        if job_id:
            query = query.where(AssessmentSession.job_id == job_id)

        normalized_email = candidate_email.strip().lower() if candidate_email else None
        if normalized_email:
            query = query.where(CandidateProfile.email == normalized_email)

        rows = await self.session.execute(query)
        latest_by_candidate_job: dict[tuple[str, str], dict[str, Any]] = {}
        for assessment_session, profile, job, report in rows.all():
            key = (profile.id, job.id)
            if key in latest_by_candidate_job:
                continue

            latest_by_candidate_job[key] = {
                "assessment_session_id": assessment_session.id,
                "candidate_profile_id": profile.id,
                "candidate_name": profile.full_name,
                "candidate_email": profile.email,
                "job_id": job.id,
                "job_title": job.title,
                "session_status": assessment_session.status,
                "report_available": report is not None,
                "decision": report.decision if report is not None else None,
                "overall_score": report.overall_score if report is not None else None,
                "integrity_score": report.integrity_score if report is not None else None,
                "summary": report.summary if report is not None else None,
                "termination_reason": report.termination_reason if report is not None else None,
                "generated_by_model": report.generated_by_model if report is not None else None,
                "started_at": assessment_session.started_at,
                "ended_at": assessment_session.ended_at,
                "created_at": assessment_session.created_at,
            }

        return list(latest_by_candidate_job.values())

    async def _get_assessment_session(self, session_id: str) -> AssessmentSession:
        assessment_session = await self.session.scalar(
            select(AssessmentSession)
            .where(AssessmentSession.id == session_id)
            .options(selectinload(AssessmentSession.interview_schedule))
        )
        if assessment_session is None:
            raise ApiError(status_code=404, code="assessment_session_not_found", message="Assessment session not found.")
        return assessment_session

    async def _resolve_or_create_candidate_profile(
        self,
        *,
        email: str,
        user_id: str | None,
        default_name: str,
    ) -> CandidateProfile:
        normalized_email = email.strip().lower()
        profile = await self.session.scalar(
            select(CandidateProfile).where(CandidateProfile.email == normalized_email)
        )
        if profile is not None:
            if user_id and profile.user_id.startswith("pending:"):
                profile.user_id = user_id
                profile.onboarding_status = "active"
            return profile

        profile = CandidateProfile(
            user_id=user_id or f"pending:{normalized_email}",
            email=normalized_email,
            full_name=default_name,
            timezone="UTC",
            profile_completeness=0.5,
            onboarding_status="active" if user_id else "invited",
        )
        self.session.add(profile)
        await self.session.flush()
        return profile

    async def _validate_candidate_access(
        self,
        context: AuthContext,
        assessment_session: AssessmentSession,
    ) -> None:
        profile = await self.session.get(CandidateProfile, assessment_session.candidate_profile_id)
        if profile is None:
            raise ApiError(status_code=404, code="candidate_profile_not_found", message="Candidate profile not found.")

        if profile.user_id == context.user_id:
            return

        if context.email and context.email.lower() == profile.email:
            profile.user_id = context.user_id
            profile.onboarding_status = "active"
            await self.session.flush()
            return

        raise ApiError(
            status_code=403,
            code="forbidden_assessment_access",
            message="Assessment session does not belong to this candidate.",
        )

    def _session_metadata(self, assessment_session: AssessmentSession) -> dict[str, Any]:
        metadata = assessment_session.session_metadata
        if isinstance(metadata, dict):
            return dict(metadata)
        return {}

    async def _build_assessment_resume_context(
        self,
        *,
        assessment_session: AssessmentSession,
        raw_resume_context: str,
    ) -> str:
        profile = await self.session.get(CandidateProfile, assessment_session.candidate_profile_id)
        candidate_name = await self._resolve_assessment_candidate_name(
            assessment_session=assessment_session,
            profile=profile,
        )
        redacted_context = self._redact_email_addresses(raw_resume_context)

        parts = [
            f"Candidate name: {candidate_name}.",
            "Use this exact candidate name if you address the candidate during the assessment.",
            "Do not infer or rewrite the candidate name from any email address or identifier.",
        ]
        if redacted_context:
            parts.append(redacted_context)
        return " ".join(parts)

    async def _resolve_assessment_candidate_name(
        self,
        *,
        assessment_session: AssessmentSession,
        profile: CandidateProfile | None,
    ) -> str:
        profile_name = self._normalize_candidate_name(profile.full_name if profile else None)
        if profile_name:
            return profile_name

        email = (profile.email if profile else "").strip().lower()
        if email:
            match = await self.session.scalar(
                select(CandidateMatch)
                .join(RankingResult, CandidateMatch.ranking_result_id == RankingResult.id)
                .where(
                    RankingResult.job_id == assessment_session.job_id,
                    or_(
                        CandidateMatch.candidate_profile_id == assessment_session.candidate_profile_id,
                        CandidateMatch.candidate_email == email,
                    ),
                )
                .order_by(CandidateMatch.created_at.desc())
            )
            match_name = self._normalize_candidate_name(match.candidate_name if match else None)
            if match_name:
                if profile is not None and profile.full_name != match_name:
                    profile.full_name = match_name
                return match_name

        if email:
            email_prefix = email.split("@")[0]
            return email_prefix.replace(".", " ").replace("_", " ").replace("-", " ").strip().title() or "Candidate"
        return "Candidate"

    def _normalize_candidate_name(self, value: str | None) -> str | None:
        text = str(value or "").strip()
        if not text or "@" in text:
            return None

        lowered = text.lower()
        if lowered in {"candidate", "unknown candidate", "user"}:
            return None
        return text

    def _redact_email_addresses(self, text: str | None) -> str:
        raw = str(text or "").strip()
        if not raw:
            return ""
        return re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[redacted-email]", raw)

    def _read_termination_reason(self, assessment_session: AssessmentSession) -> str | None:
        metadata = self._session_metadata(assessment_session)
        reason = metadata.get("termination_reason")
        if reason is None:
            return None
        text = str(reason).strip()
        return text or None

    def _normalize_proctor_event(self, event_type: str) -> str:
        return event_type.strip().lower()

    def _assert_session_allows_activity(self, assessment_session: AssessmentSession) -> None:
        if assessment_session.status == AssessmentStatus.TERMINATED:
            raise ApiError(
                status_code=409,
                code="assessment_terminated",
                message=(
                    self._read_termination_reason(assessment_session)
                    or "This assessment session has been terminated."
                ),
            )
        if assessment_session.status == AssessmentStatus.CANCELLED:
            raise ApiError(
                status_code=409,
                code="assessment_cancelled",
                message="This assessment session is no longer active.",
            )

    def _build_termination_reason(
        self,
        *,
        event_type: str,
    ) -> str:
        labels = {
            "tab_switch": "Assessment terminated after the third tab switch warning.",
            "multiple_faces": "Assessment terminated because multiple faces were detected on camera.",
            "camera_lost": "Assessment terminated because the camera feed was lost.",
            "fullscreen_exit": "Assessment terminated because fullscreen mode was exited.",
            "face_missing": "Assessment terminated because the face was no longer visible.",
        }
        return labels.get(event_type, "Assessment terminated by proctoring policy.")

    def _resolve_proctor_policy(
        self,
        *,
        event_type: str,
        severity: ProctoringSeverity,
        event_count: int,
        warning_count: int,
        critical_count: int,
    ) -> dict[str, Any]:
        _ = warning_count, critical_count

        if event_type == "tab_switch":
            if event_count >= 3:
                return {
                    "event_type": event_type,
                    "event_count": event_count,
                    "should_acknowledge": False,
                    "warning_message": None,
                    "should_terminate": True,
                    "termination_reason": self._build_termination_reason(event_type=event_type),
                }

            ordinal = "First" if event_count == 1 else "Second"
            return {
                "event_type": event_type,
                "event_count": event_count,
                "should_acknowledge": True,
                "warning_message": (
                    f"{ordinal} tab switching warning. Stay on the assessment tab. "
                    "One more tab switch will terminate the session."
                ),
                "should_terminate": False,
                "termination_reason": None,
            }

        if event_type == "multiple_faces":
            return {
                "event_type": event_type,
                "event_count": event_count,
                "should_acknowledge": False,
                "warning_message": None,
                "should_terminate": True,
                "termination_reason": self._build_termination_reason(event_type=event_type),
            }

        if event_type == "gaze_away":
            return {
                "event_type": event_type,
                "event_count": event_count,
                "should_acknowledge": True,
                "warning_message": "Please keep your eyes on the screen. This is a warning only, but it will be recorded in your report.",
                "should_terminate": False,
                "termination_reason": None,
            }

        if event_type == "face_missing":
            if event_count >= 3:
                return {
                    "event_type": event_type,
                    "event_count": event_count,
                    "should_acknowledge": False,
                    "warning_message": None,
                    "should_terminate": True,
                    "termination_reason": self._build_termination_reason(event_type=event_type),
                }

            ordinal = "First" if event_count == 1 else "Second"
            return {
                "event_type": event_type,
                "event_count": event_count,
                "should_acknowledge": True,
                "warning_message": (
                    f"{ordinal} face visibility warning. Center yourself in the camera now. "
                    "A third face-missing warning will terminate the session."
                ),
                "should_terminate": False,
                "termination_reason": None,
            }

        if severity == ProctoringSeverity.CRITICAL:
            return {
                "event_type": event_type,
                "event_count": event_count,
                "should_acknowledge": False,
                "warning_message": None,
                "should_terminate": True,
                "termination_reason": self._build_termination_reason(event_type=event_type),
            }

        return {
            "event_type": event_type,
            "event_count": event_count,
            "should_acknowledge": severity == ProctoringSeverity.WARNING,
            "warning_message": "A proctoring warning was recorded for this session." if severity == ProctoringSeverity.WARNING else None,
            "should_terminate": False,
            "termination_reason": None,
        }

    async def _upsert_report(
        self,
        *,
        assessment_session: AssessmentSession,
        force_decision: DecisionOutcome | None,
        termination_reason: str | None,
    ) -> AssessmentReport:
        session_id = assessment_session.id
        questions = list(
            await self.session.scalars(
                select(AssessmentQuestion)
                .where(AssessmentQuestion.assessment_session_id == session_id)
                .order_by(AssessmentQuestion.sequence_no.asc(), AssessmentQuestion.created_at.asc())
            )
        )
        question_map = {question.id: question for question in questions}

        answers_list = list(
            await self.session.scalars(
                select(AssessmentAnswer)
                .where(AssessmentAnswer.assessment_session_id == session_id)
                .order_by(AssessmentAnswer.created_at.asc())
            )
        )

        stage_scores: dict[str, list[float]] = {}
        technical_scores: list[float] = []
        coding_scores: list[float] = []
        communication_scores: list[float] = []
        question_results: list[dict[str, Any]] = []

        for answer in answers_list:
            question = question_map.get(answer.question_id)
            stage = question.stage if question is not None else AssessmentStage.TECHNICAL
            score = float(answer.score or 0.0)
            stage_scores.setdefault(stage.value, []).append(score)

            if stage == AssessmentStage.CODING:
                coding_scores.append(score)
            elif stage in {AssessmentStage.INTRO, AssessmentStage.CANDIDATE_INFO, AssessmentStage.VERBAL}:
                communication_scores.append(40.0 if answer.is_off_topic else min(100.0, score + 10.0))
            else:
                technical_scores.append(score)

            evaluation = answer.evaluation if isinstance(answer.evaluation, dict) else {}
            question_results.append(
                {
                    "question_id": answer.question_id,
                    "stage": stage.value,
                    "prompt": question.prompt if question is not None else "",
                    "sequence_no": question.sequence_no if question is not None else None,
                    "answer_text": answer.answer_text,
                    "answer_transcript": answer.answer_transcript,
                    "score": score,
                    "confidence": float(answer.confidence or 0.0),
                    "is_off_topic": bool(answer.is_off_topic),
                    "classification": str(evaluation.get("classification") or "needs_review"),
                    "transcription_model": (
                        str(evaluation.get("transcription_model"))
                        if evaluation.get("transcription_model")
                        else None
                    ),
                    "reasons": (
                        [str(item) for item in evaluation.get("reasons", [])]
                        if isinstance(evaluation.get("reasons"), list)
                        else []
                    ),
                }
            )

        section_scores = {
            stage: round(mean(values), 2)
            for stage, values in stage_scores.items()
            if values
        }

        technical = round(mean(technical_scores), 2) if technical_scores else 0.0
        coding = round(mean(coding_scores), 2) if coding_scores else round(technical * 0.85, 2)
        communication = round(mean(communication_scores), 2) if communication_scores else 50.0
        integrity = round(max(0.0, min(100.0, float(assessment_session.integrity_score))), 2)
        overall = round(
            (technical * 0.35)
            + (communication * 0.20)
            + (coding * 0.25)
            + (integrity * 0.20),
            2,
        )

        events = list(
            await self.session.scalars(
                select(ProctoringEvent)
                .where(ProctoringEvent.assessment_session_id == session_id)
                .order_by(ProctoringEvent.event_timestamp.asc())
            )
        )
        timeline = [
            {
                "event_type": event.event_type,
                "severity": event.severity.value,
                "timestamp": event.event_timestamp.isoformat(),
                "payload": event.payload,
            }
            for event in events
        ]
        proctor_summary = self._build_proctor_summary(events)

        if force_decision is not None:
            decision = force_decision
        elif termination_reason or assessment_session.status == AssessmentStatus.TERMINATED:
            decision = DecisionOutcome.FAIL
        elif overall >= 75 and integrity >= 60:
            decision = DecisionOutcome.PASS
        elif overall <= 45 or integrity <= 35:
            decision = DecisionOutcome.FAIL
        else:
            decision = DecisionOutcome.NEEDS_REVIEW

        reasons = [
            f"Technical score: {technical:.1f}",
            f"Communication score: {communication:.1f}",
            f"Coding score: {coding:.1f}",
            f"Integrity score: {integrity:.1f}",
        ]
        if termination_reason:
            reasons.append(f"Termination reason: {termination_reason}")

        if termination_reason:
            summary = (
                "The assessment ended early because of a proctoring event. "
                "Thank you for completing the steps so far. The session has been marked as "
                f"{decision.value} and shared with the hiring team for review."
            )
        elif decision == DecisionOutcome.PASS:
            summary = (
                f"The L0 assessment concluded strongly with an overall score of {overall:.1f}. "
                "Thank you for your time, and the hiring team will contact you about the next step."
            )
        elif decision == DecisionOutcome.FAIL:
            summary = (
                f"The L0 assessment is complete with an overall score of {overall:.1f}. "
                "Thank you for your effort. The hiring team will review the session outcome and update you soon."
            )
        else:
            summary = (
                f"The L0 assessment is complete with an overall score of {overall:.1f}. "
                "Thank you for completing the session. The hiring team will review the details before the next update."
            )

        report = await self.session.scalar(
            select(AssessmentReport).where(AssessmentReport.assessment_session_id == session_id)
        )
        if report is None:
            report = AssessmentReport(
                assessment_session_id=session_id,
                technical_score=technical,
                communication_score=communication,
                integrity_score=integrity,
                coding_score=coding,
                overall_score=overall,
                decision=decision,
                section_scores=section_scores,
                reasons=reasons,
                flagged_events_timeline=timeline,
                question_results=question_results,
                proctor_summary=proctor_summary,
                termination_reason=termination_reason,
                summary=summary,
                generated_by_model=self.settings.gemini_model if self.settings.gemini_api_key else None,
            )
            self.session.add(report)
            return report

        report.technical_score = technical
        report.communication_score = communication
        report.integrity_score = integrity
        report.coding_score = coding
        report.overall_score = overall
        report.decision = decision
        report.section_scores = section_scores
        report.reasons = reasons
        report.flagged_events_timeline = timeline
        report.question_results = question_results
        report.proctor_summary = proctor_summary
        report.termination_reason = termination_reason
        report.summary = summary
        report.generated_by_model = self.settings.gemini_model if self.settings.gemini_api_key else None
        return report

    async def _sync_candidate_match_status_from_report(
        self,
        *,
        assessment_session: AssessmentSession,
        report: AssessmentReport,
    ) -> None:
        if report.decision != DecisionOutcome.FAIL:
            return

        profile = await self.session.get(CandidateProfile, assessment_session.candidate_profile_id)
        if profile is None:
            return

        matches = list(
            await self.session.scalars(
                select(CandidateMatch)
                .join(RankingResult, CandidateMatch.ranking_result_id == RankingResult.id)
                .where(
                    RankingResult.job_id == assessment_session.job_id,
                    or_(
                        CandidateMatch.candidate_profile_id == profile.id,
                        CandidateMatch.candidate_email == profile.email,
                    ),
                )
            )
        )

        for match in matches:
            if match.status != MatchStatus.HIRED:
                match.status = MatchStatus.REJECTED

    async def _send_result_notification(
        self,
        *,
        assessment_session: AssessmentSession,
        report: AssessmentReport,
    ) -> None:
        metadata = self._session_metadata(assessment_session)
        if metadata.get("result_notification_sent_at"):
            assessment_session.session_metadata = metadata
            return

        profile = await self.session.get(CandidateProfile, assessment_session.candidate_profile_id)
        if profile is None or not profile.email:
            assessment_session.session_metadata = metadata
            return

        job = await self.session.get(Job, assessment_session.job_id)
        job_title = job.title if job is not None else "your role"
        notification_service = NotificationService(self.session, self.settings)
        candidate_name = await self._resolve_assessment_candidate_name(
            assessment_session=assessment_session,
            profile=profile,
        )

        if report.termination_reason:
            subject = f"TalentOS update for {job_title}"
            headline = "Your assessment session was closed"
            intro = [
                f"Thank you for attending the TalentOS L0 assessment for {job_title}.",
                "The session ended early because of a proctoring or integrity event, so the result has been marked as FAIL.",
                report.termination_reason,
            ]
        elif report.decision == DecisionOutcome.PASS:
            subject = f"Great news on your TalentOS assessment for {job_title}"
            headline = "You cleared the L0 assessment"
            intro = [
                f"Thank you for completing the TalentOS L0 assessment for {job_title}.",
                "You have cleared this stage and the hiring team will review the next steps with you soon.",
                report.summary,
            ]
        elif report.decision == DecisionOutcome.FAIL:
            subject = f"Your TalentOS assessment update for {job_title}"
            headline = "Your L0 assessment review is complete"
            intro = [
                f"Thank you for completing the TalentOS L0 assessment for {job_title}.",
                "This time the session did not meet the required bar, but we appreciate the effort you put into the process.",
                report.summary,
            ]
        else:
            subject = f"Your TalentOS assessment is under review for {job_title}"
            headline = "Your assessment is being reviewed"
            intro = [
                f"Thank you for completing the TalentOS L0 assessment for {job_title}.",
                "Your responses have been saved successfully and the hiring team is reviewing the final outcome.",
                report.summary,
            ]

        body_lines = [
            f"Assessment update for {job_title}",
            f"Decision: {report.decision.value}",
            f"Integrity score: {report.integrity_score:.1f}",
            f"{report.termination_reason or report.summary}",
        ]
        highlight_rows = [
            {"label": "Role", "value": job_title},
            {"label": "Decision", "value": report.decision.value},
            {"label": "Integrity", "value": f"{report.integrity_score:.1f}"},
        ]
        if not report.termination_reason:
            body_lines.insert(2, f"Overall score: {report.overall_score:.1f}")
            highlight_rows.insert(2, {"label": "Overall score", "value": f"{report.overall_score:.1f}"})

        await notification_service.send_notification(
            recipient_email=profile.email,
            notification_type=NotificationType.RESULT_AVAILABLE,
            subject=subject,
            body="\n".join(body_lines),
            metadata={
                "assessment_session_id": assessment_session.id,
                "decision": report.decision.value,
                "headline": headline,
                "preheader": f"Your TalentOS assessment update for {job_title} is ready.",
                "greeting_name": candidate_name,
                "intro": intro,
                "highlights": highlight_rows,
                "footer_note": "This TalentOS update was generated automatically for your assessment journey.",
            },
        )

        metadata["result_notification_sent_at"] = utcnow().isoformat()
        assessment_session.session_metadata = metadata

    def _build_proctor_summary(self, events: list[ProctoringEvent]) -> str:
        info_count = sum(1 for event in events if event.severity == ProctoringSeverity.INFO)
        warning_count = sum(1 for event in events if event.severity == ProctoringSeverity.WARNING)
        critical_count = sum(1 for event in events if event.severity == ProctoringSeverity.CRITICAL)
        if not events:
            return "No proctoring events were recorded during the assessment."

        event_counts = Counter(event.event_type.replace("_", " ").strip().lower() for event in events)
        event_summary = ", ".join(
            f"{label}: {count}"
            for label, count in event_counts.most_common()
        )
        latest_event = events[-1].event_type.replace("_", " ").strip().lower()
        return (
            f"{len(events)} proctoring events captured: "
            f"{warning_count} warning(s), {critical_count} critical event(s), {info_count} info event(s). "
            f"Events by type: {event_summary}. Latest event: {latest_event}."
        )

    def _anti_spoof_credentials(self, assessment_session: AssessmentSession) -> tuple[str | None, str | None]:
        metadata = assessment_session.session_metadata if isinstance(assessment_session.session_metadata, dict) else {}
        anti_spoof_metadata = metadata.get("anti_spoof")
        if not isinstance(anti_spoof_metadata, dict):
            anti_spoof_metadata = {}

        anti_spoof_session_id = str(
            anti_spoof_metadata.get("session_id")
            or assessment_session.anti_spoof_session_id
            or ""
        ).strip() or None
        anti_spoof_token = str(anti_spoof_metadata.get("access_token") or "").strip() or None
        return anti_spoof_session_id, anti_spoof_token

    async def _ensure_anti_spoof_passed(self, *, assessment_session: AssessmentSession) -> None:
        anti_spoof_session_id, anti_spoof_token = self._anti_spoof_credentials(assessment_session)
        if not anti_spoof_session_id or not anti_spoof_token:
            raise ApiError(
                status_code=409,
                code="anti_spoof_required",
                message="Complete anti-spoof/liveness verification before starting the L0 assessment.",
            )

        metadata = assessment_session.session_metadata if isinstance(assessment_session.session_metadata, dict) else {}
        anti_spoof_snapshot = metadata.get("anti_spoof_snapshot")
        if isinstance(anti_spoof_snapshot, dict) and self._anti_spoof_snapshot_passed(anti_spoof_snapshot):
            return

        try:
            payload = await self.anti_spoof.get_session(
                session_id=anti_spoof_session_id,
                access_token=anti_spoof_token,
            )
        except AntiSpoofingClientError as exc:
            raise ApiError(
                status_code=exc.status_code,
                code="anti_spoof_unavailable",
                message=exc.message,
            ) from exc

        self._persist_anti_spoof_snapshot(assessment_session, payload)
        await self.session.flush()
        if self._anti_spoof_snapshot_passed(payload):
            return

        raise ApiError(
            status_code=409,
            code="anti_spoof_required",
            message="Complete anti-spoof/liveness verification before starting the L0 assessment.",
        )

    def _persist_anti_spoof_snapshot(self, assessment_session: AssessmentSession, payload: dict[str, Any]) -> None:
        metadata = dict(assessment_session.session_metadata or {})
        metadata["anti_spoof_snapshot"] = payload

        anti_spoof_metadata = metadata.get("anti_spoof")
        if not isinstance(anti_spoof_metadata, dict):
            anti_spoof_metadata = {}
        anti_spoof_metadata["status"] = payload.get("status")
        anti_spoof_metadata["final_decision"] = payload.get("final_decision")
        metadata["anti_spoof"] = anti_spoof_metadata

        assessment_session.session_metadata = metadata

    def _anti_spoof_snapshot_passed(self, snapshot: dict[str, Any]) -> bool:
        status = str(snapshot.get("status") or "").strip().lower()
        final_decision = str(snapshot.get("final_decision") or "").strip().upper()

        latest_result = snapshot.get("latest_result")
        latest_overall = ""
        if isinstance(latest_result, dict):
            latest_overall = str(latest_result.get("overall_status") or "").strip().upper()

        if final_decision == "PASS":
            return True

        if latest_overall == "PASS" and status in {"review_ready", "finalized", "locked"}:
            return True

        return False

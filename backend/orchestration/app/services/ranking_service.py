from __future__ import annotations

import secrets
from dataclasses import dataclass

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings, get_settings
from app.core.exceptions import ApiError
from app.core.security import AuthContext
from app.models.base import utcnow
from app.models.entities import (
    CandidateMatch,
    CandidateProfile,
    InterviewSchedule,
    Job,
    RankingResult,
    ResumeAnalysis,
)
from app.models.enums import MatchStatus, NotificationType, ScheduleStatus
from app.schemas.jobs import RankingRequest
from app.services.ats_client import ATSClient
from app.services.audit_service import AuditService
from app.services.notification_service import NotificationService


@dataclass(frozen=True, slots=True)
class RankingOutcome:
    ranking_result: RankingResult
    matches: list[CandidateMatch]
    notification_ids: list[str]


class RankingService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings | None = None,
        ats_client: ATSClient | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.ats_client = ats_client or ATSClient(self.settings)

    async def run_ranking(
        self,
        *,
        job: Job,
        payload: RankingRequest,
        context: AuthContext,
        request: Request | None,
    ) -> RankingOutcome:
        ats_payload = {
            "job_id": job.id,
            "job_title": job.title,
            "job_description": job.jd_text,
            "source": payload.source,
            "minimum_ats_score": payload.minimum_ats_score,
            "retrieval_top_k": payload.retrieval_top_k,
            "candidate_pool_size": payload.candidate_pool_size,
            "final_top_k": payload.final_top_k,
        }
        ats_response = await self.ats_client.run_resume_check(ats_payload)
        results = ats_response.get("results")
        if not isinstance(results, list):
            raise ApiError(
                status_code=502,
                code="ats_invalid_response",
                message="ATS returned an invalid ranking payload.",
            )

        ranking_result = RankingResult(
            job_id=job.id,
            report_run_id=ats_response.get("report_run_id"),
            total_candidates=len(results),
            invited_top_n=0,
            ranking_payload=ats_response,
        )
        self.session.add(ranking_result)
        await self.session.flush()

        matches: list[CandidateMatch] = []
        for index, candidate in enumerate(results, start=1):
            candidate_external_id = str(candidate.get("candidate_id") or f"unknown-{index}")
            candidate_name = str(candidate.get("candidate_name") or "Unknown Candidate")
            candidate_email = self._clean_email(candidate.get("candidate_email"))
            final_score = float(candidate.get("final_score", 0.0))
            ats_score = float(candidate.get("ats_score", 0.0))
            reasons = candidate.get("reasons")
            explanation = " | ".join([str(item) for item in reasons]) if isinstance(reasons, list) else ""

            candidate_profile = None
            if candidate_email:
                candidate_profile = await self._get_or_create_candidate_profile(
                    email=candidate_email,
                    full_name=candidate_name,
                )

            match = CandidateMatch(
                ranking_result_id=ranking_result.id,
                candidate_profile_id=candidate_profile.id if candidate_profile else None,
                candidate_external_id=candidate_external_id,
                candidate_name=candidate_name,
                candidate_email=candidate_email,
                rank=int(candidate.get("rank") or index),
                final_score=final_score,
                ats_score=ats_score,
                status=MatchStatus.MATCHED,
                explanation=explanation,
            )
            self.session.add(match)

            resume_analysis = ResumeAnalysis(
                job_id=job.id,
                candidate_external_id=candidate_external_id,
                candidate_email=candidate_email,
                report_run_id=str(ats_response.get("report_run_id") or ""),
                final_score=final_score,
                ats_score=ats_score,
                reasons=[str(item) for item in reasons] if isinstance(reasons, list) else [],
                raw_payload=candidate,
            )
            self.session.add(resume_analysis)
            matches.append(match)

        await self.session.flush()

        invite_limit = payload.top_n or self.settings.default_invite_top_n
        notification_service = NotificationService(self.session, self.settings)
        notification_ids: list[str] = []

        ranked_matches = sorted(matches, key=lambda item: item.rank)
        for match in ranked_matches[:invite_limit]:
            if not match.candidate_email or not match.candidate_profile_id:
                continue

            invitation_token = secrets.token_urlsafe(32)
            invite = InterviewSchedule(
                candidate_profile_id=match.candidate_profile_id,
                job_id=job.id,
                slot_id=None,
                invitation_token=invitation_token,
                status=ScheduleStatus.INVITED,
                booked_at=None,
                cancelled_at=None,
            )
            self.session.add(invite)
            match.status = MatchStatus.INVITED

            invitation_link = notification_service.build_invitation_link(
                invitation_token=invitation_token,
                candidate_email=match.candidate_email,
                job_id=job.id,
            )
            candidate_name = (match.candidate_name or "Candidate").strip() or "Candidate"

            notification = await notification_service.send_notification(
                recipient_email=match.candidate_email,
                notification_type=NotificationType.L0_INVITE,
                subject=f"Interview Invitation: {job.title} at TalentOS",
                body=(
                    f"Hi {candidate_name},\n\n"
                    f"You have been shortlisted for the TalentOS L0 assessment interview for '{job.title}'.\n"
                    "Please use the secure scheduling link below to continue:\n"
                    f"{invitation_link}\n\n"
                    "Next steps:\n"
                    "1. Open the link\n"
                    "2. Sign in with your invited email\n"
                    "3. Complete face registration/verification\n"
                    "4. Pick your interview slot"
                ),
                metadata={
                    "job_id": job.id,
                    "candidate_match_id": match.id,
                    "invitation_token": invitation_token,
                    "invitation_link": invitation_link,
                    "headline": f"{job.title} interview invitation",
                    "preheader": "You have been shortlisted for the next TalentOS stage.",
                    "greeting_name": candidate_name,
                    "intro": [
                        f"You have been shortlisted for the TalentOS L0 assessment interview for {job.title}.",
                        "Use the secure link below to sign in, complete identity verification, and select a slot.",
                    ],
                    "highlights": [
                        {"label": "Role", "value": job.title},
                        {"label": "Department", "value": job.department},
                        {"label": "Location", "value": job.location},
                    ],
                    "steps": [
                        "Open the secure link from your invited email address.",
                        "Sign in with OTP and complete face verification.",
                        "Pick an available slot to unlock the L0 assessment flow.",
                    ],
                    "cta_label": "Continue to Booking",
                    "cta_url": invitation_link,
                },
            )
            notification_ids.append(notification.id)

        ranking_result.invited_top_n = len(notification_ids)

        audit_service = AuditService(self.session)
        await audit_service.record(
            context=context,
            action="jobs.rank_candidates",
            resource_type="job",
            resource_id=job.id,
            request=request,
            metadata={
                "report_run_id": ranking_result.report_run_id,
                "invited_top_n": ranking_result.invited_top_n,
                "total_candidates": ranking_result.total_candidates,
            },
        )

        await self.session.commit()
        return RankingOutcome(
            ranking_result=ranking_result,
            matches=ranked_matches,
            notification_ids=notification_ids,
        )

    async def get_latest_ranking(self, *, job_id: str) -> RankingResult | None:
        records = list(
            await self.session.scalars(
                select(RankingResult)
                .where(RankingResult.job_id == job_id)
                .options(selectinload(RankingResult.matches))
                .order_by(RankingResult.created_at.desc())
            )
        )
        if not records:
            return None

        for record in records:
            if record.matches:
                return record

            payload = record.ranking_payload if isinstance(record.ranking_payload, dict) else {}
            results = payload.get("results")
            if isinstance(results, list) and any(isinstance(item, dict) for item in results):
                return record

        return records[0]

    async def _get_or_create_candidate_profile(
        self,
        *,
        email: str,
        full_name: str,
    ) -> CandidateProfile:
        existing = await self.session.scalar(
            select(CandidateProfile).where(CandidateProfile.email == email)
        )
        if existing is not None:
            if not existing.full_name and full_name:
                existing.full_name = full_name
            return existing

        candidate = CandidateProfile(
            user_id=f"pending:{email}",
            email=email,
            full_name=full_name,
            timezone="UTC",
            profile_completeness=0.4,
            onboarding_status="invited",
        )
        self.session.add(candidate)
        await self.session.flush()
        return candidate

    @staticmethod
    def _clean_email(raw: object) -> str | None:
        if raw is None:
            return None
        value = str(raw).strip().lower()
        if "@" not in value:
            return None
        return value

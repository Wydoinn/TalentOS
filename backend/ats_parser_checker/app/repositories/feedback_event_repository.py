from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import RecruiterFeedbackType
from app.models.feedback_event import CandidateFeedbackEvent
from app.models.resume_report import ResumeReport


@dataclass(slots=True)
class FeedbackLearningRow:
    report_run_id: str
    candidate_id: str
    feedback_type: RecruiterFeedbackType
    retrieval_score: float | None
    graph_score: float | None
    reranker_score: float | None
    ats_score: float
    final_score: float


class FeedbackEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, event: CandidateFeedbackEvent) -> CandidateFeedbackEvent:
        self.session.add(event)
        await self.session.flush()
        return event

    async def list_by_run_id(self, report_run_id: str) -> list[CandidateFeedbackEvent]:
        result = await self.session.execute(
            select(CandidateFeedbackEvent)
            .where(CandidateFeedbackEvent.report_run_id == report_run_id)
            .order_by(CandidateFeedbackEvent.created_at.asc(), CandidateFeedbackEvent.id.asc())
        )
        return list(result.scalars().all())

    async def count_by_type(self) -> dict[str, int]:
        result = await self.session.execute(
            select(
                CandidateFeedbackEvent.feedback_type,
                func.count(CandidateFeedbackEvent.id),
            ).group_by(CandidateFeedbackEvent.feedback_type)
        )
        return {
            feedback_type.value if hasattr(feedback_type, "value") else str(feedback_type): count
            for feedback_type, count in result.all()
        }

    async def list_learning_rows(self) -> list[FeedbackLearningRow]:
        result = await self.session.execute(
            select(
                CandidateFeedbackEvent.report_run_id,
                CandidateFeedbackEvent.candidate_id,
                CandidateFeedbackEvent.feedback_type,
                ResumeReport.retrieval_score,
                ResumeReport.graph_score,
                ResumeReport.reranker_score,
                ResumeReport.ats_score,
                ResumeReport.final_score,
            )
            .join(
                ResumeReport,
                and_(
                    ResumeReport.report_run_id == CandidateFeedbackEvent.report_run_id,
                    ResumeReport.candidate_id == CandidateFeedbackEvent.candidate_id,
                ),
            )
            .order_by(CandidateFeedbackEvent.created_at.asc(), CandidateFeedbackEvent.id.asc())
        )
        return [
            FeedbackLearningRow(
                report_run_id=report_run_id,
                candidate_id=candidate_id,
                feedback_type=feedback_type,
                retrieval_score=retrieval_score,
                graph_score=graph_score,
                reranker_score=reranker_score,
                ats_score=ats_score,
                final_score=final_score,
            )
            for (
                report_run_id,
                candidate_id,
                feedback_type,
                retrieval_score,
                graph_score,
                reranker_score,
                ats_score,
                final_score,
            ) in result.all()
        ]

    async def commit(self) -> None:
        await self.session.commit()

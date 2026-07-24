from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.resume_report import ResumeReport


class ResumeReportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_run_and_candidate(
        self,
        report_run_id: str,
        candidate_id: str,
    ) -> ResumeReport | None:
        return await self.session.get(
            ResumeReport,
            {"report_run_id": report_run_id, "candidate_id": candidate_id},
        )

    async def list_by_run_id(self, report_run_id: str) -> list[ResumeReport]:
        result = await self.session.execute(
            select(ResumeReport)
            .where(ResumeReport.report_run_id == report_run_id)
            .order_by(ResumeReport.rank.asc(), ResumeReport.final_score.desc())
        )
        return list(result.scalars().all())

    async def save(self, report: ResumeReport) -> ResumeReport:
        self.session.add(report)
        await self.session.flush()
        return report

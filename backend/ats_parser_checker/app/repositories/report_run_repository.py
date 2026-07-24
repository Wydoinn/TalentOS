from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_run import ATSReportRun


class ATSReportRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, report_run_id: str) -> ATSReportRun | None:
        return await self.session.get(ATSReportRun, report_run_id)

    async def save(self, report_run: ATSReportRun) -> ATSReportRun:
        self.session.add(report_run)
        await self.session.flush()
        return report_run

    async def commit(self) -> None:
        await self.session.commit()

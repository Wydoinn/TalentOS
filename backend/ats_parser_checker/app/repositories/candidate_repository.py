from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.candidate import Candidate
from app.models.enums import CandidateSource, IngestionStatus


class CandidateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, candidate: Candidate) -> Candidate:
        self.session.add(candidate)
        await self.session.flush()
        return candidate

    async def get_by_id(self, candidate_id: str) -> Candidate | None:
        return await self.session.get(Candidate, candidate_id)

    async def get_by_checksum_and_source(
        self,
        checksum: str,
        source: CandidateSource,
    ) -> Candidate | None:
        result = await self.session.execute(
            select(Candidate).where(
                Candidate.resume_checksum == checksum,
                Candidate.source == source,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_ats(
        self,
        *,
        source: CandidateSource | None = None,
    ) -> list[Candidate]:
        query = select(Candidate).where(Candidate.ingestion_status == IngestionStatus.completed)
        if source is not None:
            query = query.where(Candidate.source == source)
        query = query.order_by(Candidate.updated_at.desc())
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def list_by_ids(self, candidate_ids: list[str]) -> list[Candidate]:
        if not candidate_ids:
            return []

        result = await self.session.execute(
            select(Candidate).where(
                Candidate.id.in_(candidate_ids),
                Candidate.ingestion_status == IngestionStatus.completed,
            )
        )
        found = {candidate.id: candidate for candidate in result.scalars().all()}
        return [found[candidate_id] for candidate_id in candidate_ids if candidate_id in found]

    async def delete_all(self) -> None:
        await self.session.execute(delete(Candidate))

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()

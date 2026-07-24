from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.agents.embedding_model import LocalEmbeddingModel
from app.models.candidate import Candidate
from app.models.enums import CandidateSource, IngestionStatus
from app.pipelines.resume_pipeline import ResumeIngestionPipeline
from app.repositories.candidate_repository import CandidateRepository
from app.services.parsing_service import ResumeParsingService
from app.utils.candidate_profile import build_graph_payload, build_pinecone_metadata
from app.utils.ids import generate_candidate_id


@dataclass(slots=True)
class ResumeIngestionOutcome:
    candidate_id: str
    status: str
    source: CandidateSource
    disposition: str


class ResumeIngestionService:
    def __init__(
        self,
        *,
        candidate_repository: CandidateRepository,
        parsing_service: ResumeParsingService,
        embedding_model: LocalEmbeddingModel,
        vector_store,
        graph_store,
    ) -> None:
        self.candidate_repository = candidate_repository
        self.parsing_service = parsing_service
        self.pipeline = ResumeIngestionPipeline(
            embedding_model=embedding_model,
            vector_store=vector_store,
            graph_store=graph_store,
        )

    async def ingest_saved_resume(
        self,
        *,
        file_path: Path,
        checksum: str,
        source: CandidateSource,
        force_reingest: bool = False,
        availability: str | None = None,
        location: str | None = None,
        candidate_id: str | None = None,
    ) -> ResumeIngestionOutcome:
        existing = await self.candidate_repository.get_by_checksum_and_source(checksum, source)
        if (
            not force_reingest
            and
            existing is not None
            and existing.ingestion_status == IngestionStatus.completed
        ):
            return self._build_outcome(existing, disposition="existing")

        raw_text = await self.parsing_service.extract_text(file_path)
        structured_resume = await self.parsing_service.parse(
            raw_text=raw_text,
            source=source,
            availability=availability,
            location=location,
        )
        if existing is None:
            disposition = "ingested"
            resolved_candidate_id = candidate_id or generate_candidate_id()
            candidate = Candidate(
                id=resolved_candidate_id,
                full_name=structured_resume.name,
                email=structured_resume.email,
                phone=structured_resume.phone,
                location=structured_resume.location,
                source=source,
                availability=structured_resume.availability,
                current_title=structured_resume.current_title,
                total_experience_years=structured_resume.total_experience_years,
                skills=structured_resume.skills,
                structured_resume=structured_resume.model_dump(mode="json"),
                summary=structured_resume.summary,
                raw_text=raw_text,
                file_path=str(file_path),
                resume_checksum=checksum,
                ingestion_status=IngestionStatus.processing,
            )
            await self.candidate_repository.add(candidate)
        else:
            disposition = "reprocessed"
            candidate = existing
            candidate.full_name = structured_resume.name
            candidate.email = structured_resume.email
            candidate.phone = structured_resume.phone
            candidate.location = structured_resume.location
            candidate.availability = structured_resume.availability
            candidate.current_title = structured_resume.current_title
            candidate.total_experience_years = structured_resume.total_experience_years
            candidate.skills = structured_resume.skills
            candidate.structured_resume = structured_resume.model_dump(mode="json")
            candidate.summary = structured_resume.summary
            candidate.raw_text = raw_text
            candidate.file_path = str(file_path)
            candidate.resume_checksum = checksum
            candidate.ingestion_status = IngestionStatus.processing
        await self.candidate_repository.commit()

        try:
            await self.pipeline.run(
                candidate_id=candidate.id,
                search_document=structured_resume.summary,
                metadata=build_pinecone_metadata(
                    candidate_id=candidate.id,
                    source=candidate.source.value,
                    structured_resume=structured_resume,
                ),
                graph_payload=build_graph_payload(
                    candidate_id=candidate.id,
                    full_name=candidate.full_name,
                    source=candidate.source.value,
                    structured_resume=structured_resume,
                ),
            )
            candidate.ingestion_status = IngestionStatus.completed
            await self.candidate_repository.commit()
        except Exception as exc:
            await self.candidate_repository.rollback()
            persisted_candidate = await self.candidate_repository.get_by_id(candidate.id)
            if persisted_candidate is not None:
                persisted_candidate.ingestion_status = IngestionStatus.failed
                await self.candidate_repository.commit()
            raise

        return self._build_outcome(candidate, disposition=disposition)

    @staticmethod
    def _build_outcome(candidate: Candidate, *, disposition: str) -> ResumeIngestionOutcome:
        return ResumeIngestionOutcome(
            candidate_id=candidate.id,
            status=candidate.ingestion_status.value,
            source=candidate.source,
            disposition=disposition,
        )

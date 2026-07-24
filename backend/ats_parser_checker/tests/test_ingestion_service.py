from __future__ import annotations

from pathlib import Path

from app.models.enums import CandidateSource, IngestionStatus
from app.schemas.ingestion import StructuredResume
from app.services.ingestion_service import ResumeIngestionService
from conftest import build_candidate


class StubCandidateRepository:
    def __init__(self, candidate):
        self.candidate = candidate
        self.commit_calls = 0

    async def get_by_checksum_and_source(self, _checksum, _source):
        _ = (_checksum, _source)
        return self.candidate

    async def add(self, _candidate):
        _ = _candidate
        raise AssertionError("add should not be called for existing candidate")

    async def commit(self):
        self.commit_calls += 1

    async def rollback(self):
        return None

    async def get_by_id(self, candidate_id):
        return self.candidate if self.candidate.id == candidate_id else None


class StubParsingService:
    def __init__(self, structured_resume: StructuredResume):
        self.structured_resume = structured_resume
        self.extract_calls = 0
        self.parse_calls = 0

    async def extract_text(self, _file_path: Path) -> str:
        _ = _file_path
        self.extract_calls += 1
        return "raw text"

    async def parse(
        self,
        *,
        raw_text,
        source,
        availability=None,
        location=None,
    ) -> StructuredResume:
        _ = (raw_text, source, availability, location)
        self.parse_calls += 1
        return self.structured_resume


class StubPipeline:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def run(self, **kwargs) -> None:
        self.calls.append(kwargs)
        return None


async def test_ingest_saved_resume_keeps_existing_completed_candidate_when_graph_not_synced(tmp_path: Path) -> None:
    existing = build_candidate(
        candidate_id="cand_retry",
        name="Old Name",
        source=CandidateSource.external,
        summary="old summary",
        skills=["python"],
        experience_years=1,
        raw_text="old raw text",
        file_path=str(tmp_path / "resumes" / "external" / "resume.docx"),
    )
    existing.resume_checksum = "same-checksum"
    existing.ingestion_status = IngestionStatus.completed

    structured_resume = StructuredResume(
        name="Arun Kumar R",
        email="arun@example.com",
        phone="+91-9999999999",
        location="Tamil Nadu, India",
        current_title="Backend Developer",
        skills=["python", "fastapi"],
        experience=[],
        education=[],
        projects=[],
        total_experience_years=0.0,
        links={},
        availability="unspecified",
        source=CandidateSource.external,
        summary="Candidate Arun Kumar R. Current title Backend Developer.",
    )

    repository = StubCandidateRepository(existing)
    parsing_service = StubParsingService(structured_resume)
    service = ResumeIngestionService(
        candidate_repository=repository,
        parsing_service=parsing_service,
        embedding_model=object(),
        vector_store=object(),
        graph_store=object(),
    )
    service.pipeline = StubPipeline()

    outcome = await service.ingest_saved_resume(
        file_path=tmp_path / "resume.docx",
        checksum="same-checksum",
        source=CandidateSource.external,
    )

    assert outcome.disposition == "existing"
    assert parsing_service.extract_calls == 0
    assert parsing_service.parse_calls == 0
    assert existing.full_name == "Old Name"
    assert repository.commit_calls == 0


async def test_ingest_saved_resume_force_reingest_rebuilds_completed_candidate(tmp_path: Path) -> None:
    existing = build_candidate(
        candidate_id="cand_force",
        name="Existing Name",
        source=CandidateSource.internal,
        summary="existing summary",
        skills=["sql"],
        experience_years=2,
        raw_text="existing raw text",
        file_path=str(tmp_path / "resumes" / "internal" / "resume.pdf"),
    )
    existing.resume_checksum = "checksum-force"
    existing.ingestion_status = IngestionStatus.completed

    structured_resume = StructuredResume(
        name="Vignesh S",
        email="vignesh@example.com",
        phone=None,
        location="Tamil Nadu, India",
        current_title="Data Analyst",
        skills=["python", "sql"],
        experience=[],
        education=[],
        projects=[],
        total_experience_years=2.0,
        links={},
        availability="unspecified",
        source=CandidateSource.internal,
        summary="Candidate Vignesh S. Current title Data Analyst.",
    )

    repository = StubCandidateRepository(existing)
    parsing_service = StubParsingService(structured_resume)
    service = ResumeIngestionService(
        candidate_repository=repository,
        parsing_service=parsing_service,
        embedding_model=object(),
        vector_store=object(),
        graph_store=object(),
    )
    pipeline = StubPipeline()
    service.pipeline = pipeline

    outcome = await service.ingest_saved_resume(
        file_path=tmp_path / "resume.pdf",
        checksum="checksum-force",
        source=CandidateSource.internal,
        force_reingest=True,
    )

    assert outcome.disposition == "reprocessed"
    assert parsing_service.extract_calls == 1
    assert parsing_service.parse_calls == 1
    assert existing.full_name == "Vignesh S"
    assert pipeline.calls[0]["metadata"]["candidate_id"] == "cand_force"
    assert pipeline.calls[0]["metadata"]["source"] == "internal"
    assert pipeline.calls[0]["metadata"]["skills"] == ["python", "sql"]
    assert pipeline.calls[0]["metadata"]["experience_years"] == 2.0
    assert pipeline.calls[0]["metadata"]["current_role"] == "Data Analyst"
    assert pipeline.calls[0]["metadata"]["location"] == "Tamil Nadu, India"
    assert pipeline.calls[0]["metadata"]["education"] == ""
    assert "python" in pipeline.calls[0]["metadata"]["top_keywords"]
    assert pipeline.calls[0]["graph_payload"]["full_name"] == "Vignesh S"
    assert pipeline.calls[0]["graph_payload"]["source"] == "internal"
    assert pipeline.calls[0]["graph_payload"]["current_title"] == "Data Analyst"
    assert pipeline.calls[0]["graph_payload"]["total_experience_years"] == 2.0
    assert pipeline.calls[0]["graph_payload"]["skills"] == ["python", "sql"]
    assert pipeline.calls[0]["graph_payload"]["projects"] == []
    assert pipeline.calls[0]["graph_payload"]["experiences"] == []
    assert pipeline.calls[0]["graph_payload"]["experience_level"] == "junior"
    assert pipeline.calls[0]["graph_payload"]["experience_min_years"] == 1.0
    assert pipeline.calls[0]["graph_payload"]["experience_max_years"] == 3.0

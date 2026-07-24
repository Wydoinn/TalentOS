from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.models.enums import IngestionStatus
from app.models.enums import CandidateSource
from app.services.ingestion_service import ResumeIngestionOutcome
from app.services.resume_sync_service import ResumeDirectorySyncManager


class DummySessionManager:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, _exc_type, _exc, _tb):
        _ = (_exc_type, _exc, _tb)
        return False


class StubIngestionService:
    def __init__(self, **kwargs):
        pass

    async def ingest_saved_resume(self, *, file_path, checksum, source, **kwargs):
        _ = checksum
        return ResumeIngestionOutcome(
            candidate_id=f"cand_{file_path.stem}",
            status="completed",
            source=source,
            disposition="ingested",
        )


class StubCandidateRepository:
    def __init__(self, session):
        self.session = session

    async def delete_all(self):
        return None

    async def commit(self):
        return None

    async def get_by_checksum_and_source(self, _checksum, _source):
        _ = (_checksum, _source)
        return SimpleNamespace(
            ingestion_status=IngestionStatus.completed,
        )


async def test_resume_sync_scans_internal_and_external_folders(monkeypatch, tmp_path: Path) -> None:
    resumes_root = tmp_path / "resumes"
    (resumes_root / "internal").mkdir(parents=True)
    (resumes_root / "external").mkdir(parents=True)
    (resumes_root / "internal" / "alice.pdf").write_bytes(b"alice")
    (resumes_root / "external" / "bob.docx").write_bytes(b"bob")
    (resumes_root / "external" / "charlie.txt").write_text("charlie", encoding="utf-8")

    monkeypatch.setattr("app.services.resume_sync_service.AsyncSessionLocal", lambda: DummySessionManager())
    monkeypatch.setattr("app.services.resume_sync_service.ResumeIngestionService", StubIngestionService)
    monkeypatch.setattr("app.services.resume_sync_service.CandidateRepository", StubCandidateRepository)

    settings = type(
        "Settings",
        (),
        {
            "resume_source_dir": resumes_root,
            "allowed_resume_extensions": (".pdf", ".docx"),
            "resume_sync_interval_seconds": 15,
        },
    )()
    manager = ResumeDirectorySyncManager(
        settings=settings,
        embedding_model=object(),
        vector_store=object(),
        graph_store=object(),
    )

    summary = await manager.sync(force=True)

    assert summary.scanned_files == 2
    assert summary.processed_files == 2
    assert summary.embedded_files == 2
    assert summary.failed_files == 0
    assert {item.source for item in summary.results} == {
        CandidateSource.internal,
        CandidateSource.external,
    }

    next_summary = await manager.sync(force=False)

    assert next_summary.scanned_files == 2
    assert next_summary.processed_files == 0
    assert next_summary.skipped_files == 2

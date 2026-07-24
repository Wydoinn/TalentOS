from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path

from app.agents.embedding_model import LocalEmbeddingModel
from app.core.config import Settings
from app.core.database import AsyncSessionLocal
from app.models.candidate import Candidate
from app.models.enums import CandidateSource, IngestionStatus
from app.repositories.candidate_repository import CandidateRepository
from app.schemas.ingestion import (
    ResumeSyncFileResult,
    ResumeSyncStatusResponse,
    ResumeSyncSummary,
)
from app.services.ingestion_service import ResumeIngestionService
from app.services.parsing_service import ResumeParsingService
from app.utils.documents import compute_file_checksum, is_supported_resume_path

logger = logging.getLogger(__name__)

SOURCE_DIRECTORY_MAP = {
    "internal": CandidateSource.internal,
    "external": CandidateSource.external,
}


class ResumeDirectorySyncManager:
    def __init__(
        self,
        *,
        settings: Settings,
        embedding_model: LocalEmbeddingModel,
        vector_store,
        graph_store,
    ) -> None:
        self.settings = settings
        self.embedding_model = embedding_model
        self.vector_store = vector_store
        self.graph_store = graph_store
        self._lock = asyncio.Lock()
        self._last_summary: ResumeSyncSummary | None = None
        self._file_fingerprints: dict[str, tuple[int, int]] = {}
        self._running = False

    async def sync(self, *, force: bool = False) -> ResumeSyncSummary:
        async with self._lock:
            self._running = True
            summary = ResumeSyncSummary(started_at=datetime.now(timezone.utc))
            try:
                if force:
                    await self._reset_ingestion_state()
                for file_path, source in self._discover_resume_files():
                    summary.scanned_files += 1
                    fingerprint = self._fingerprint(file_path)
                    cache_key = str(file_path.resolve())
                    try:
                        async with AsyncSessionLocal() as session:
                            checksum = compute_file_checksum(file_path)
                            repository = CandidateRepository(session)
                            if not force and self._file_fingerprints.get(cache_key) == fingerprint:
                                existing = await repository.get_by_checksum_and_source(checksum, source)
                                if self._is_healthy_candidate(existing):
                                    summary.skipped_files += 1
                                    continue
                                logger.info(
                                    "Retrying unchanged resume '%s' because previous sync is incomplete",
                                    self._relative_path(file_path),
                                )

                            logger.info(
                                "Syncing resume '%s' from %s",
                                self._relative_path(file_path),
                                source.value,
                            )
                            service = ResumeIngestionService(
                                candidate_repository=repository,
                                parsing_service=ResumeParsingService(),
                                embedding_model=self.embedding_model,
                                vector_store=self.vector_store,
                                graph_store=self.graph_store,
                            )
                            outcome = await service.ingest_saved_resume(
                                file_path=file_path,
                                checksum=checksum,
                                source=source,
                                force_reingest=force,
                            )
                        self._file_fingerprints[cache_key] = fingerprint
                        summary.processed_files += 1
                        if outcome.disposition in {"ingested", "reprocessed"}:
                            summary.embedded_files += 1
                        else:
                            summary.skipped_files += 1
                        logger.info(
                            "Resume sync completed for '%s' with disposition=%s status=%s",
                            self._relative_path(file_path),
                            outcome.disposition,
                            outcome.status,
                        )
                        summary.results.append(
                            ResumeSyncFileResult(
                                relative_path=self._relative_path(file_path),
                                source=source,
                                candidate_id=outcome.candidate_id,
                                disposition=outcome.disposition,
                                status=outcome.status,
                                detail=None,
                            )
                        )
                    except Exception as exc:
                        logger.warning("Failed to sync resume '%s': %s", file_path, exc)
                        summary.processed_files += 1
                        summary.failed_files += 1
                        summary.results.append(
                            ResumeSyncFileResult(
                                relative_path=self._relative_path(file_path),
                                source=source,
                                candidate_id=None,
                                disposition="failed",
                                status="failed",
                                detail=str(exc),
                            )
                        )
                summary.completed_at = datetime.now(timezone.utc)
                self._last_summary = summary
                return summary
            finally:
                self._running = False

    async def watch(self) -> None:
        while True:
            try:
                await self.sync(force=False)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Resume directory sync cycle failed")
            try:
                await asyncio.sleep(self.settings.resume_sync_interval_seconds)
            except asyncio.CancelledError:
                raise

    def build_status(self) -> ResumeSyncStatusResponse:
        return ResumeSyncStatusResponse(
            watched_directory=str(self.settings.resume_source_dir),
            poll_interval_seconds=self.settings.resume_sync_interval_seconds,
            running=self._running,
            last_summary=self._last_summary,
        )

    def _discover_resume_files(self) -> list[tuple[Path, CandidateSource]]:
        root = self.settings.resume_source_dir
        if not root.exists():
            return []

        discovered: list[tuple[Path, CandidateSource]] = []
        for file_path in sorted(root.rglob("*")):
            if not file_path.is_file():
                continue
            if not is_supported_resume_path(
                file_path,
                allowed_extensions=self.settings.allowed_resume_extensions,
            ):
                continue
            source = self._resolve_source(file_path)
            if source is None:
                logger.warning(
                    "Skipping resume outside supported source folders: %s",
                    file_path,
                )
                continue
            discovered.append((file_path, source))
        return discovered

    def _resolve_source(self, file_path: Path) -> CandidateSource | None:
        relative = file_path.relative_to(self.settings.resume_source_dir)
        if not relative.parts:
            return None
        return SOURCE_DIRECTORY_MAP.get(relative.parts[0].lower())

    def _relative_path(self, file_path: Path) -> str:
        with suppress(ValueError):
            return str(file_path.relative_to(self.settings.resume_source_dir))
        return str(file_path)

    async def _reset_ingestion_state(self) -> None:
        self._file_fingerprints.clear()

        async with AsyncSessionLocal() as session:
            repository = CandidateRepository(session)
            await repository.delete_all()
            await repository.commit()

        clear_namespace = getattr(self.vector_store, "clear_namespace", None)
        if callable(clear_namespace):
            await clear_namespace()

        clear_candidate_graph = getattr(self.graph_store, "clear_candidate_graph", None)
        if callable(clear_candidate_graph):
            await clear_candidate_graph()

    @staticmethod
    def _fingerprint(file_path: Path) -> tuple[int, int]:
        stat_result = file_path.stat()
        return (stat_result.st_size, stat_result.st_mtime_ns)

    @staticmethod
    def _is_healthy_candidate(candidate: Candidate | None) -> bool:
        return bool(
            candidate is not None
            and candidate.ingestion_status == IngestionStatus.completed
        )

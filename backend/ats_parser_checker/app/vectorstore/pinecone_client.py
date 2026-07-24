from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

from pinecone import Pinecone, ServerlessSpec

from app.core.config import Settings
from app.core.exceptions import ExternalServiceException


@dataclass(slots=True)
class RetrievedCandidateMatch:
    candidate_id: str
    score: float
    metadata: dict[str, Any]


class PineconeVectorStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: Pinecone | None = None
        self._index = None
        self._last_error: str | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.settings.pinecone_api_key)

    def _service_unavailable_detail(self) -> str:
        if not self.enabled:
            return "Pinecone credentials not configured"
        if self._last_error:
            return self._last_error
        return "Pinecone index is not initialized"

    def _get_client(self) -> Pinecone:
        if not self.enabled:
            raise ExternalServiceException("Pinecone is not configured")
        if self._client is None:
            self._client = Pinecone(api_key=self.settings.pinecone_api_key)
        return self._client

    @property
    def _request_timeout(self) -> tuple[int, int]:
        return self._build_request_timeout()

    def _build_request_timeout(
        self,
        *,
        connect_timeout_seconds: int | None = None,
        read_timeout_seconds: int | None = None,
    ) -> tuple[int, int]:
        return (
            connect_timeout_seconds or self.settings.pinecone_connect_timeout_seconds,
            read_timeout_seconds or self.settings.pinecone_read_timeout_seconds,
        )

    def _list_index_names(self) -> list[str]:
        client = self._get_client()
        raw_indexes = client.list_indexes()
        if hasattr(raw_indexes, "indexes"):
            return [item.name for item in raw_indexes.indexes]
        names: list[str] = []
        for item in raw_indexes:
            if isinstance(item, dict):
                names.append(item["name"])
            else:
                names.append(item.name)
        return names

    def _get_index(self):
        if self._index is None:
            self._index = self._get_client().Index(self.settings.pinecone_index_name)
        return self._index

    async def ensure_index(self) -> None:
        if not self.enabled:
            return

        def _ensure() -> None:
            client = self._get_client()
            if self.settings.pinecone_index_name not in self._list_index_names():
                client.create_index(
                    name=self.settings.pinecone_index_name,
                    dimension=self.settings.vector_dimension,
                    metric=self.settings.pinecone_metric,
                    spec=ServerlessSpec(
                        cloud=self.settings.pinecone_cloud,
                        region=self.settings.pinecone_region,
                    ),
                )
            self._index = client.Index(self.settings.pinecone_index_name)

        try:
            await self._execute_operation(
                _ensure,
                error_detail=f"Unable to initialize Pinecone index '{self.settings.pinecone_index_name}'",
            )
            self._last_error = None
        except ExternalServiceException:
            raise

    async def upsert_candidate(
        self,
        *,
        candidate_id: str,
        embedding: list[float],
        metadata: dict[str, Any],
    ) -> None:
        if not self.enabled or self._index is None:
            raise ExternalServiceException(self._service_unavailable_detail())

        def _upsert() -> None:
            self._get_index().upsert(
                vectors=[
                    {
                        "id": candidate_id,
                        "values": embedding,
                        "metadata": metadata,
                    }
                ],
                namespace=self.settings.pinecone_namespace,
                _request_timeout=self._request_timeout,
            )

        await self._execute_operation(
            _upsert,
            error_detail="Failed to upsert candidate embedding into Pinecone",
        )

    async def query_candidates(
        self,
        *,
        query_embedding: list[float],
        top_k: int,
        source: str | None = None,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[RetrievedCandidateMatch]:
        if not self.enabled or self._index is None:
            raise ExternalServiceException(self._service_unavailable_detail())

        def _query():
            query_kwargs = {
                "vector": query_embedding,
                "top_k": top_k,
                "namespace": self.settings.pinecone_namespace,
                "include_metadata": True,
                "_request_timeout": self._request_timeout,
            }
            merged_filter = self._merge_filters(
                {"source": {"$eq": source}} if source else None,
                metadata_filter,
            )
            if merged_filter:
                query_kwargs["filter"] = merged_filter
            return self._get_index().query(
                **query_kwargs,
            )

        raw_result = await self._execute_operation(
            _query,
            error_detail="Failed to query candidate embeddings from Pinecone",
        )
        matches = getattr(raw_result, "matches", None)
        if matches is None and isinstance(raw_result, dict):
            matches = raw_result.get("matches", [])
        if matches is None:
            return []
        return [self._coerce_match(match) for match in matches if self._resolve_candidate_id(match)]

    async def healthcheck(self, *, fast: bool = False) -> dict[str, str]:
        if not self.enabled:
            return {"status": "disabled", "detail": "Pinecone credentials not configured"}
        if self._index is None and self._last_error:
            return {"status": "error", "detail": self._last_error}
        if self._index is None:
            return {"status": "error", "detail": "Pinecone index is not initialized"}

        request_timeout = (
            self._build_request_timeout(
                connect_timeout_seconds=self.settings.healthcheck_timeout_seconds,
                read_timeout_seconds=self.settings.healthcheck_timeout_seconds,
            )
            if fast
            else self._request_timeout
        )

        def _stats():
            return self._get_index().describe_index_stats(_request_timeout=request_timeout)

        try:
            await self._execute_operation(
                _stats,
                error_detail="Failed to reach Pinecone index",
                retry=not fast,
                timeout_seconds=(
                    self.settings.healthcheck_timeout_seconds + 1 if fast else None
                ),
                reset_state_on_failure=not fast,
            )
            self._last_error = None
        except ExternalServiceException as exc:
            return {"status": "error", "detail": exc.detail}
        return {"status": "ok", "detail": self.settings.pinecone_index_name}

    async def clear_namespace(self) -> None:
        if not self.enabled or self._index is None:
            return

        def _delete_all() -> None:
            self._get_index().delete(
                delete_all=True,
                namespace=self.settings.pinecone_namespace,
                _request_timeout=self._request_timeout,
            )

        await self._execute_operation(
            _delete_all,
            error_detail="Failed to clear Pinecone namespace",
        )

    async def _execute_operation(
        self,
        operation,
        *,
        error_detail: str,
        retry: bool = True,
        timeout_seconds: int | None = None,
        reset_state_on_failure: bool = True,
    ):
        timeout_seconds = timeout_seconds or (
            self.settings.pinecone_connect_timeout_seconds
            + self.settings.pinecone_read_timeout_seconds
            + 5
        )
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(operation),
                timeout=timeout_seconds,
            )
            self._last_error = None
            return result
        except Exception as exc:
            if not retry:
                self._last_error = str(exc) or exc.__class__.__name__
                if reset_state_on_failure:
                    self._reset_client_state()
                raise ExternalServiceException(error_detail) from exc
            self._reset_client_state()
            try:
                result = await asyncio.wait_for(
                    asyncio.to_thread(operation),
                    timeout=timeout_seconds,
                )
                self._last_error = None
                return result
            except Exception as retry_exc:
                self._last_error = str(retry_exc) or retry_exc.__class__.__name__
                raise ExternalServiceException(error_detail) from retry_exc

    def _reset_client_state(self) -> None:
        with suppress(Exception):
            api_client = getattr(getattr(self._index, "_vector_api", None), "api_client", None)
            if api_client is not None:
                api_client.close()
        self._index = None
        self._client = None

    @classmethod
    def _coerce_match(cls, match: Any) -> RetrievedCandidateMatch:
        metadata = cls._resolve_match_metadata(match)
        candidate_id = cls._resolve_candidate_id(match)
        raw_score = getattr(match, "score", None)
        if raw_score is None and isinstance(match, dict):
            raw_score = match.get("score", 0.0)
        return RetrievedCandidateMatch(
            candidate_id=candidate_id,
            score=round(float(raw_score or 0.0), 4),
            metadata=metadata,
        )

    @staticmethod
    def _resolve_match_metadata(match: Any) -> dict[str, Any]:
        metadata = getattr(match, "metadata", None)
        if metadata is None and isinstance(match, dict):
            metadata = match.get("metadata")
        return dict(metadata or {})

    @staticmethod
    def _merge_filters(
        left_filter: dict[str, Any] | None,
        right_filter: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if left_filter and right_filter:
            return {"$and": [left_filter, right_filter]}
        return left_filter or right_filter

    @classmethod
    def _resolve_candidate_id(cls, match: Any) -> str | None:
        metadata = cls._resolve_match_metadata(match)
        candidate_id = metadata.get("candidate_id")
        if candidate_id:
            return str(candidate_id)
        raw_id = getattr(match, "id", None)
        if raw_id is None and isinstance(match, dict):
            raw_id = match.get("id")
        return str(raw_id) if raw_id else None

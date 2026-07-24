from __future__ import annotations

from app.core.config import Settings
from app.vectorstore.pinecone_client import PineconeVectorStore


class _FakeIndex:
    def __init__(self, *, fail_upsert: bool = False) -> None:
        self.fail_upsert = fail_upsert
        self.upsert_calls: list[dict] = []
        self.stats_calls: list[dict] = []
        self.query_calls: list[dict] = []

    def upsert(self, **kwargs):
        self.upsert_calls.append(kwargs)
        if self.fail_upsert:
            raise TimeoutError("timed out")
        return None

    def describe_index_stats(self, **kwargs):
        self.stats_calls.append(kwargs)
        return {"namespaces": {}}

    def query(self, **kwargs):
        self.query_calls.append(kwargs)
        return {
            "matches": [
                {
                    "id": "cand_1",
                    "score": 0.91,
                    "metadata": {
                        "candidate_id": "cand_1",
                        "name": "Jane",
                    },
                }
            ]
        }


async def test_pinecone_upsert_passes_request_timeout() -> None:
    settings = Settings(
        _env_file=None,
        pinecone_api_key="test-key",
        pinecone_connect_timeout_seconds=7,
        pinecone_read_timeout_seconds=11,
    )
    store = PineconeVectorStore(settings)
    fake_index = _FakeIndex()
    store._index = fake_index

    await store.upsert_candidate(
        candidate_id="cand_1",
        embedding=[0.1, 0.2],
        metadata={"name": "Jane"},
    )

    assert fake_index.upsert_calls[0]["_request_timeout"] == (7, 11)


async def test_pinecone_upsert_retries_after_timeout(monkeypatch) -> None:
    settings = Settings(
        _env_file=None,
        pinecone_api_key="test-key",
        pinecone_connect_timeout_seconds=3,
        pinecone_read_timeout_seconds=4,
    )
    store = PineconeVectorStore(settings)
    failing_index = _FakeIndex(fail_upsert=True)
    healthy_index = _FakeIndex()
    indexes = iter([healthy_index])

    def fake_get_index():
        if store._index is None:
            store._index = next(indexes)
        return store._index

    monkeypatch.setattr(store, "_get_index", fake_get_index)
    store._index = failing_index

    await store.upsert_candidate(
        candidate_id="cand_retry",
        embedding=[0.3, 0.4],
        metadata={"name": "Retry"},
    )

    assert len(failing_index.upsert_calls) == 1
    assert len(healthy_index.upsert_calls) == 1


async def test_pinecone_fast_healthcheck_uses_short_timeout() -> None:
    settings = Settings(
        _env_file=None,
        pinecone_api_key="test-key",
        pinecone_connect_timeout_seconds=10,
        pinecone_read_timeout_seconds=15,
        healthcheck_timeout_seconds=4,
    )
    store = PineconeVectorStore(settings)
    fake_index = _FakeIndex()
    store._index = fake_index

    result = await store.healthcheck(fast=True)

    assert result == {"status": "ok", "detail": settings.pinecone_index_name}
    assert fake_index.stats_calls[0]["_request_timeout"] == (4, 4)


async def test_pinecone_query_candidates_includes_metadata_and_filter() -> None:
    settings = Settings(
        _env_file=None,
        pinecone_api_key="test-key",
        pinecone_connect_timeout_seconds=5,
        pinecone_read_timeout_seconds=9,
    )
    store = PineconeVectorStore(settings)
    fake_index = _FakeIndex()
    store._index = fake_index

    matches = await store.query_candidates(
        query_embedding=[0.1, 0.2],
        top_k=3,
        source="internal",
        metadata_filter={"experience_years": {"$gte": 4}},
    )

    assert [match.candidate_id for match in matches] == ["cand_1"]
    assert fake_index.query_calls[0]["include_metadata"] is True
    assert fake_index.query_calls[0]["filter"] == {
        "$and": [
            {"source": {"$eq": "internal"}},
            {"experience_years": {"$gte": 4}},
        ]
    }
    assert fake_index.query_calls[0]["_request_timeout"] == (5, 9)

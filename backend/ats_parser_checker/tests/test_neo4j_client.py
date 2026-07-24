from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from app.core.config import Settings
from app.graph.neo4j_client import Neo4jGraphStore


async def test_neo4j_healthcheck_reports_disabled_when_not_configured() -> None:
    settings = Settings(_env_file=None, neo4j_uri=None, neo4j_username=None, neo4j_password=None)
    store = Neo4jGraphStore(settings)

    result = await store.healthcheck()

    assert result["status"] == "disabled"


async def test_neo4j_healthcheck_surfaces_cached_error() -> None:
    settings = Settings(
        _env_file=None,
        neo4j_uri="bolt://localhost:7687",
        neo4j_username="neo4j",
        neo4j_password="secret",
    )
    store = Neo4jGraphStore(settings)
    store._last_error = "connection refused"

    result = await store.healthcheck()

    assert result == {"status": "error", "detail": "connection refused"}


async def test_neo4j_fast_healthcheck_uses_connected_driver() -> None:
    settings = Settings(
        _env_file=None,
        neo4j_uri="bolt://localhost:7687",
        neo4j_username="neo4j",
        neo4j_password="secret",
        healthcheck_timeout_seconds=4,
    )
    store = Neo4jGraphStore(settings)
    fake_session = _FakeSession()
    store._driver = _FakeDriver(fake_session)

    result = await store.healthcheck(fast=True)

    assert result == {"status": "ok", "detail": "neo4j"}
    assert fake_session.calls == [("RETURN 1 AS health", {})]


class _FakeResult:
    def __init__(self, records: list[dict[str, object]] | None = None) -> None:
        self._records = records or []

    async def consume(self) -> None:
        return None

    async def single(self):
        return {"health": 1}

    async def data(self):
        return list(self._records)


class _FakeSession:
    def __init__(self, *, records: list[dict[str, object]] | None = None) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.records = records or []

    async def run(self, query: str, **parameters: object) -> _FakeResult:
        self.calls.append((query, parameters))
        return _FakeResult(records=self.records)


class _FakeDriver:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session
        self.closed = False

    @asynccontextmanager
    async def session(self) -> AsyncIterator[_FakeSession]:
        yield self._session

    async def verify_connectivity(self) -> None:
        return None

    async def close(self) -> None:
        self.closed = True


class _SlowClosingDriver(_FakeDriver):
    async def close(self) -> None:
        await asyncio.sleep(0.1)


async def test_upsert_candidate_profile_splits_graph_work_into_small_queries() -> None:
    settings = Settings(
        _env_file=None,
        neo4j_uri="bolt://localhost:7687",
        neo4j_username="neo4j",
        neo4j_password="secret",
        neo4j_query_timeout_seconds=15,
    )
    store = Neo4jGraphStore(settings)
    fake_session = _FakeSession()
    store._driver = _FakeDriver(fake_session)

    await store.upsert_candidate_profile(
        candidate_id="cand_1",
        full_name="Jane Doe",
        source="internal",
        current_title="Backend Engineer",
        total_experience_years=6.0,
        skills=["python", "python", "fastapi", ""],
        projects=[
            {
                "key": "cand_1:ats",
                "name": "ATS",
                "summary": "ATS platform",
                "skills": ["python", "fastapi"],
            }
        ],
        experiences=[
            {
                "key": "cand_1:experience:1",
                "role": "Backend Engineer",
                "company": "Acme",
                "description": "Built APIs",
                "start_date": "2021",
                "end_date": "2024",
                "skills": ["python", "fastapi"],
            }
        ],
        experience_level="senior",
        experience_min_years=6.0,
        experience_max_years=9.0,
    )

    assert len(fake_session.calls) == 8
    assert "MERGE (candidate:Candidate" in fake_session.calls[0][0]
    assert "DETACH DELETE project" in fake_session.calls[1][0]
    assert "DETACH DELETE experience" in fake_session.calls[2][0]
    assert "DELETE relationship" in fake_session.calls[3][0]
    assert fake_session.calls[4][1]["skills"] == ["fastapi", "python"]
    assert fake_session.calls[5][1]["experience_level"] == "senior"
    assert fake_session.calls[6][1]["experiences"][0]["company"] == "Acme"
    assert fake_session.calls[7][1]["projects"][0]["skills"] == ["fastapi", "python"]


async def test_ensure_schema_creates_constraints_once() -> None:
    settings = Settings(
        _env_file=None,
        neo4j_uri="bolt://localhost:7687",
        neo4j_username="neo4j",
        neo4j_password="secret",
    )
    store = Neo4jGraphStore(settings)
    fake_session = _FakeSession()
    store._driver = _FakeDriver(fake_session)

    await store._ensure_schema()
    await store._ensure_schema()

    assert len(fake_session.calls) == len(store._schema_queries())
    assert any("CREATE INDEX" in query for query, _ in fake_session.calls)
    assert any("CREATE CONSTRAINT" in query for query, _ in fake_session.calls)


async def test_close_uses_bounded_timeout(monkeypatch) -> None:
    settings = Settings(
        _env_file=None,
        neo4j_uri="bolt://localhost:7687",
        neo4j_username="neo4j",
        neo4j_password="secret",
    )
    store = Neo4jGraphStore(settings)
    store._driver = _SlowClosingDriver(_FakeSession())

    monkeypatch.setattr(store, "_close_timeout_seconds", lambda: 0.01)

    await asyncio.wait_for(store.close(), timeout=0.05)

    assert store._driver is None


async def test_score_candidates_returns_normalized_graph_match_scores() -> None:
    settings = Settings(
        _env_file=None,
        neo4j_uri="bolt://localhost:7687",
        neo4j_username="neo4j",
        neo4j_password="secret",
        neo4j_query_timeout_seconds=15,
    )
    fake_session = _FakeSession(
        records=[
                {
                    "candidate_id": "cand_1",
                    "total_experience_years": 6.0,
                    "matched_skills": ["python", "fastapi"],
                    "project_validated_skills": ["python", "fastapi"],
                    "experience_validated_skills": ["python", "fastapi"],
                    "cooccurring_skills": ["python", "fastapi"],
                    "cooccurrence_project_count": 1,
                    "project_count": 1,
                },
                {
                    "candidate_id": "cand_2",
                    "total_experience_years": 2.0,
                    "matched_skills": ["python"],
                    "project_validated_skills": ["python"],
                    "experience_validated_skills": ["python"],
                    "cooccurring_skills": [],
                    "cooccurrence_project_count": 0,
                    "project_count": 1,
                },
        ]
    )
    store = Neo4jGraphStore(settings)
    store._driver = _FakeDriver(fake_session)

    scores = await store.score_candidates(
        candidate_ids=["cand_1", "cand_2"],
        required_skills=["python", "fastapi", "neo4j"],
        required_years=5.0,
    )

    assert scores["cand_1"].score == 0.75
    assert scores["cand_1"].matched_skills == ["fastapi", "python"]
    assert scores["cand_1"].project_validated_skills == ["fastapi", "python"]
    assert scores["cand_1"].cooccurring_skills == ["fastapi", "python"]
    assert scores["cand_1"].experience_score == 1.0
    assert scores["cand_2"].score == 0.31
    assert fake_session.calls[0][1]["candidate_ids"] == ["cand_1", "cand_2"]

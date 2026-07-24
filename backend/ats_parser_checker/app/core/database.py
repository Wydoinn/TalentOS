from collections.abc import AsyncGenerator
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.models.base import Base

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    future=True,
    pool_pre_ping=True,
)
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autoflush=False,
    expire_on_commit=False,
)


def _ensure_sqlite_directory(database_url: URL) -> None:
    database_path = database_url.database
    if not database_path or database_path == ":memory:":
        return
    Path(database_path).expanduser().resolve(strict=False).parent.mkdir(
        parents=True,
        exist_ok=True,
    )


def _build_admin_database_url(database_url: URL) -> URL | None:
    database_name = database_url.database
    if not database_name:
        return None
    return database_url.set(database="postgres")


def _quote_identifier(identifier: str) -> str:
    escaped = identifier.replace('"', '""')
    return '"' + escaped + '"'


async def _ensure_database_exists() -> None:
    database_url = make_url(settings.database_url)
    backend_name = database_url.get_backend_name()

    if backend_name == "sqlite":
        _ensure_sqlite_directory(database_url)
        return

    if backend_name != "postgresql" or not database_url.database:
        return

    admin_database_url = _build_admin_database_url(database_url)
    if admin_database_url is None:
        return

    admin_engine = create_async_engine(
        admin_database_url,
        pool_pre_ping=True,
        isolation_level="AUTOCOMMIT",
    )

    try:
        async with admin_engine.connect() as connection:
            database_exists = (
                await connection.execute(
                    text("SELECT 1 FROM pg_database WHERE datname = :database_name"),
                    {"database_name": database_url.database},
                )
            ).scalar()
            if database_exists:
                return
            await connection.execute(
                text(f"CREATE DATABASE {_quote_identifier(database_url.database)}")
            )
    finally:
        await admin_engine.dispose()


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def init_database() -> None:
    from app.models import candidate, feedback_event, report_run, resume_report  # noqa: F401

    await _ensure_database_exists()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        if connection.dialect.name == "postgresql":
            await _promote_json_columns_to_jsonb(connection)
            await _ensure_resume_report_score_columns(connection)
            await _ensure_report_run_ranking_columns(connection)
            await _drop_unused_candidate_columns(connection)


async def dispose_database() -> None:
    await engine.dispose()


async def _ensure_resume_report_score_columns(connection) -> None:
    for statement in (
        """
        ALTER TABLE resume_report_results
        ADD COLUMN IF NOT EXISTS final_score DOUBLE PRECISION NOT NULL DEFAULT 0.0
        """,
        """
        ALTER TABLE resume_report_results
        ADD COLUMN IF NOT EXISTS retrieval_score DOUBLE PRECISION
        """,
        """
        ALTER TABLE resume_report_results
        ADD COLUMN IF NOT EXISTS graph_score DOUBLE PRECISION
        """,
        """
        ALTER TABLE resume_report_results
        ADD COLUMN IF NOT EXISTS reranker_score DOUBLE PRECISION
        """,
        """
        ALTER TABLE resume_report_results
        ADD COLUMN IF NOT EXISTS parsing_quality_score DOUBLE PRECISION NOT NULL DEFAULT 1.0
        """,
        """
        ALTER TABLE resume_report_results
        ADD COLUMN IF NOT EXISTS parsing_warnings JSONB NOT NULL DEFAULT '[]'::jsonb
        """,
        """
        ALTER TABLE resume_report_results
        ADD COLUMN IF NOT EXISTS reasons JSONB NOT NULL DEFAULT '[]'::jsonb
        """,
    ):
        await connection.execute(text(statement))


async def _ensure_report_run_ranking_columns(connection) -> None:
    for statement in (
        """
        ALTER TABLE ats_report_runs
        ADD COLUMN IF NOT EXISTS ranking_weights JSONB NOT NULL DEFAULT '{}'::jsonb
        """,
        """
        ALTER TABLE ats_report_runs
        ADD COLUMN IF NOT EXISTS feedback_events_analyzed INTEGER NOT NULL DEFAULT 0
        """,
    ):
        await connection.execute(text(statement))


async def _promote_json_columns_to_jsonb(connection) -> None:
    json_columns = {
        "ats_report_runs": ("ranking_weights",),
        "candidate_feedback_events": ("details",),
        "candidates": ("skills", "structured_resume"),
        "resume_report_results": (
            "parsing_warnings",
            "reasons",
            "issues",
            "suggestions",
            "missing_keywords",
            "matched_keywords",
            "sections",
            "formatting_signals",
        ),
    }
    for table_name, columns in json_columns.items():
        for column_name in columns:
            result = await connection.execute(
                text(
                    """
                    SELECT data_type
                    FROM information_schema.columns
                    WHERE table_schema = current_schema()
                      AND table_name = :table_name
                      AND column_name = :column_name
                    """
                ),
                {"table_name": table_name, "column_name": column_name},
            )
            data_type = result.scalar_one_or_none()
            if data_type == "json":
                await connection.execute(
                    text(
                        f"""
                        ALTER TABLE {table_name}
                        ALTER COLUMN {column_name}
                        TYPE JSONB
                        USING {column_name}::jsonb
                        """
                    )
                )


async def _drop_unused_candidate_columns(connection) -> None:
    for column_name in ("file_name", "vector_id", "graph_synced_at", "ingestion_error"):
        await connection.execute(
            text(f"ALTER TABLE candidates DROP COLUMN IF EXISTS {column_name}")
        )

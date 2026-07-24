from __future__ import annotations

from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.models.base import Base


settings = get_settings()
engine = create_async_engine(
    settings.database_url,
    echo=settings.database_echo,
    pool_pre_ping=True,
)
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
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


async def init_db() -> None:
    await _ensure_database_exists()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def check_database_health() -> bool:
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False

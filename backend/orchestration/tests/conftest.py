from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.security import AuthContext
from app.models.base import Base
from app.models.entities import *  # noqa: F401,F403
from app.models.enums import UserRole


@pytest.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture
def manager_context() -> AuthContext:
    return AuthContext(
        user_id="manager-001",
        email="manager@example.com",
        role=UserRole.PROJECT_MANAGER,
        stage="authenticated",
        token="test-token",
    )


@pytest.fixture
def candidate_context() -> AuthContext:
    return AuthContext(
        user_id="candidate-user-001",
        email="candidate@example.com",
        role=UserRole.CANDIDATE,
        stage="authenticated",
        token="test-token",
    )

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db_session
from app.schemas.common import HealthDependencyStatus, HealthResponse

router = APIRouter(tags=["Health"])


async def _probe_dependency(
    operation,
    *,
    timeout_seconds: int,
) -> dict[str, str]:
    try:
        return await asyncio.wait_for(operation, timeout=timeout_seconds)
    except asyncio.TimeoutError:
        return {"status": "error", "detail": "timeout"}
    except Exception as exc:
        return {"status": "error", "detail": str(exc) or exc.__class__.__name__}


async def _probe_database(
    session: AsyncSession,
    *,
    timeout_seconds: int,
) -> dict[str, str]:
    await asyncio.wait_for(session.execute(text("SELECT 1")), timeout=timeout_seconds)
    return {"status": "ok"}


@router.get("/health", response_model=HealthResponse)
async def healthcheck(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> HealthResponse:
    settings = get_settings()
    dependencies: dict[str, HealthDependencyStatus] = {}
    timeout_seconds = max(1, settings.healthcheck_timeout_seconds)

    database_status, vector_status, graph_status = await asyncio.gather(
        _probe_dependency(
            _probe_database(session, timeout_seconds=timeout_seconds),
            timeout_seconds=timeout_seconds,
        ),
        _probe_dependency(
            request.app.state.vector_store.healthcheck(fast=True),
            timeout_seconds=timeout_seconds,
        ),
        _probe_dependency(
            request.app.state.graph_store.healthcheck(fast=True),
            timeout_seconds=timeout_seconds,
        ),
    )

    dependencies["database"] = HealthDependencyStatus(**database_status)
    resume_sync_status = request.app.state.resume_sync_manager.build_status()
    dependencies["pinecone"] = HealthDependencyStatus(**vector_status)
    dependencies["neo4j"] = HealthDependencyStatus(**graph_status)
    dependencies["resume_sync"] = HealthDependencyStatus(
        status="running" if resume_sync_status.running else "ok",
        detail=(
            resume_sync_status.last_summary.completed_at.isoformat()
            if resume_sync_status.last_summary and resume_sync_status.last_summary.completed_at
            else "pending first sync"
        ),
    )
    dependencies["embedding_model"] = HealthDependencyStatus(
        status="ok" if settings.embedding_model_dir.exists() else "missing",
        detail=str(settings.embedding_model_dir),
    )
    dependencies["reranker_model"] = HealthDependencyStatus(
        status="ok" if settings.reranker_model_dir.exists() else "missing",
        detail=str(settings.reranker_model_dir),
    )
    return HealthResponse(
        service=settings.app_name,
        version=settings.app_version,
        dependencies=dependencies,
    )

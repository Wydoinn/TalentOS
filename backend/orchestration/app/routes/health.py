from __future__ import annotations

from datetime import datetime, timezone

import httpx
from fastapi import APIRouter

from app.core.config import get_settings
from app.core.database import check_database_health
from app.schemas.common import HealthDependencyStatus, HealthResponse


router = APIRouter(tags=["health"])
settings = get_settings()


async def _probe_http(url: str) -> tuple[str, str | None]:
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(url)
            response.raise_for_status()
        return "ok", None
    except Exception as exc:
        return "degraded", str(exc)


@router.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "status": "ok",
        "docs": "/docs",
        "health": "/health",
    }


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    db_status = "ok" if await check_database_health() else "degraded"
    auth_status, auth_detail = await _probe_http(f"{settings.authentication_service_url}/health")
    ats_status, ats_detail = await _probe_http(f"{settings.ats_service_url}/api/health")
    anti_status, anti_detail = await _probe_http(f"{settings.anti_spoofing_service_url}/health")

    dependencies = {
        "database": HealthDependencyStatus(status=db_status),
        "authentication": HealthDependencyStatus(status=auth_status, detail=auth_detail),
        "ats": HealthDependencyStatus(status=ats_status, detail=ats_detail),
        "anti_spoofing": HealthDependencyStatus(status=anti_status, detail=anti_detail),
    }

    global_status = "ok" if all(item.status == "ok" for item in dependencies.values()) else "degraded"
    return HealthResponse(
        service=settings.app_name,
        version=settings.app_version,
        status=global_status,
        timestamp=datetime.now(timezone.utc),
        dependencies=dependencies,
    )

"""Health and readiness endpoints."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from app.api.schemas import HealthResponse, ReadyResponse
from app.config import get_settings
from app.models.base import registry
from app.session.store import get_session_store

router = APIRouter(tags=["observability"])
settings = get_settings()


def _stt_ready() -> bool:
    return settings.STT_BACKEND != "whisper" or settings.STT_MODEL_DIR.exists()


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Return a lightweight liveness probe."""
    return HealthResponse(
        status="ok",
        version=settings.APP_VERSION,
        timestamp=datetime.now(timezone.utc),
    )


@router.get("/ready", response_model=ReadyResponse)
async def ready() -> ReadyResponse:
    """Return readiness based on model and session-store availability."""
    model_status = registry.status()
    model_status["stt"] = _stt_ready()

    store_ok = await get_session_store().ping()
    required_models_ready = registry.all_required_ready()
    overall_ready = store_ok and (
        required_models_ready or not settings.READY_REQUIRE_ALL_MODELS
    )

    return ReadyResponse(
        status="ready" if overall_ready else "degraded",
        models_loaded=model_status,
        session_store=store_ok,
    )

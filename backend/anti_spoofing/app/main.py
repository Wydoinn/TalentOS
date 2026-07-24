from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from time import perf_counter

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import health, sessions
from app.api.schemas import ErrorResponse
from app.config import get_settings
from app.models.audio_spoof import AudioSpoofModel
from app.models.base import registry
from app.models.face_detector import FaceDetectorModel
from app.models.face_embedding import FaceEmbeddingModel
from app.models.face_spoof import FaceSpoofModel
from app.utils.logging import get_logger, setup_logging

settings = get_settings()
logger = get_logger(__name__)


def _register_models() -> None:
    registry.clear()
    registry.register(FaceDetectorModel())
    registry.register(FaceSpoofModel())
    registry.register(FaceEmbeddingModel())
    registry.register(AudioSpoofModel())


@asynccontextmanager
async def lifespan(_app: FastAPI):
    setup_logging(settings.LOG_LEVEL)
    logger.info("Starting %s v%s", settings.APP_NAME, settings.APP_VERSION)

    _register_models()
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, registry.load_all)

    missing = registry.missing_required()
    if missing:
        logger.error(
            "Required models failed to load: %s. Sessions will be rejected with "
            "MODEL_UNAVAILABLE until the local weights are available in '%s'.",
            ", ".join(missing),
            settings.MODELS_DIR,
        )
    else:
        logger.info("All required models loaded")

    if settings.MODEL_WARMUP:
        for name, model in registry.items():
            if not model.is_ready():
                continue
            try:
                await loop.run_in_executor(None, model.warm_up)
                logger.debug("Warm-up completed for %s", name)
            except Exception as exc:
                logger.debug("Warm-up skipped for %s: %s", name, exc)

    logger.info("Service ready at http://%s:%s/docs", settings.HOST, settings.PORT)
    yield
    logger.info("Shutting down")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description=(
            "Session-based multi-modal anti-spoofing for AI HR interviews. "
            "Verifies real human presence via face, voice, challenge-response, "
            "and identity consistency signals."
        ),
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def add_timing_header(request: Request, call_next):
        started_at = perf_counter()
        response = await call_next(request)
        response.headers["X-Process-Time-Ms"] = f"{(perf_counter() - started_at) * 1000:.1f}"
        return response

    @app.exception_handler(ValueError)
    async def _handle_value_error(_request: Request, exc: ValueError):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=ErrorResponse(error="validation_error", detail=str(exc)).model_dump(),
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(_request: Request, exc: Exception):
        logger.exception("Unhandled request error")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(error="internal_server_error").model_dump(),
        )

    app.include_router(health.router)
    app.include_router(sessions.router)
    return app


app = create_app()

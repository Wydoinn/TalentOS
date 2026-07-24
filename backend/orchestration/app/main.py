from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal, init_db
from app.core.exceptions import ApiError, ApiErrorField, error_payload
from app.models.entities import Role
from app.routes.ai import router as ai_router
from app.routes.assessment import router as assessment_router
from app.routes.health import router as health_router
from app.routes.internal import router as internal_router
from app.routes.jobs import router as jobs_router
from app.routes.notifications import router as notifications_router
from app.routes.scheduling import router as scheduling_router


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)
settings = get_settings()


async def _seed_roles() -> None:
    roles = [
        {
            "code": "PROJECT_MANAGER",
            "name": "Hiring Manager",
            "description": "Manager who owns jobs and hiring workflow.",
            "permissions": [
                "jobs:create",
                "jobs:rank",
                "schedules:manage",
                "assessment:monitor",
            ],
        },
        {
            "code": "CANDIDATE",
            "name": "Candidate",
            "description": "Candidate who can schedule and attend assessments.",
            "permissions": [
                "schedules:book",
                "assessment:join",
            ],
        },
    ]

    async with AsyncSessionLocal() as session:
        for role in roles:
            existing = await session.scalar(select(Role).where(Role.code == role["code"]))
            if existing is None:
                session.add(
                    Role(
                        code=role["code"],
                        name=role["name"],
                        description=role["description"],
                        permissions=role["permissions"],
                        is_system=True,
                    )
                )
        await session.commit()


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    await _seed_roles()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        lifespan=lifespan,
        description=(
            "TalentOS orchestration layer for jobs, candidate ranking, scheduling, "
            "assessment sessions, proctoring event ingestion, Gemini workflows, "
            "notifications, analytics, and realtime room signaling."
        ),
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(ApiError)
    async def handle_api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(code=exc.code, message=exc.message, fields=exc.fields),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [
            ApiErrorField(
                field=".".join(str(part) for part in error["loc"] if part != "body"),
                message=error["msg"],
            )
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=error_payload(
                code="invalid_request",
                message="Request validation failed.",
                fields=fields,
            ),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled orchestration error", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content=error_payload(
                code="internal_server_error",
                message="An unexpected server error occurred.",
            ),
        )

    app.include_router(health_router)
    app.include_router(internal_router)
    app.include_router(jobs_router)
    app.include_router(scheduling_router)
    app.include_router(assessment_router)
    app.include_router(ai_router)
    app.include_router(notifications_router)

    return app


app = create_app()

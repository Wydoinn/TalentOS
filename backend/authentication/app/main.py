from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api_errors import ApiException, ApiFieldError, build_error_response
from app.core.config import get_settings
from app.db.session import init_db
from app.routes import auth_router, candidate_router, system_router
from app.services.email import EmailService
from app.services.pinecone_service import PineconeService


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()

    email_service = EmailService()
    if not email_service.is_configured():
        logger.warning(
            "SMTP is not configured. OTP endpoints will return 503 until configured."
        )

    pinecone_service = PineconeService()
    if pinecone_service.is_configured():
        reachable, detail = pinecone_service.check_health()
        if reachable is False:
            logger.warning("Pinecone is configured but not ready: %s", detail)
    else:
        logger.warning(
            "Pinecone is not configured. Candidate face registration and verification will fail until configured."
        )

    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Passwordless authentication API with explicit sign-up and login OTP flows, "
            "plus candidate-only face registration during sign-up and face verification "
            "during login, backed by PostgreSQL and Pinecone."
        ),
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_allow_origins),
        allow_origin_regex=settings.cors_allow_origin_regex,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(ApiException)
    async def handle_api_exception(_: Request, exc: ApiException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=build_error_response(
                code=exc.code,
                message=exc.message,
                fields=exc.fields,
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        fields = [
            ApiFieldError(
                field=".".join(str(part) for part in error["loc"] if part != "body"),
                message=error["msg"],
            )
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=build_error_response(
                code="invalid_request",
                message="Request validation failed.",
                fields=fields,
            ),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled application error.", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content=build_error_response(
                code="internal_server_error",
                message="An unexpected server error occurred.",
            ),
        )

    app.include_router(system_router)
    app.include_router(auth_router)
    app.include_router(candidate_router)
    return app


app = create_app()

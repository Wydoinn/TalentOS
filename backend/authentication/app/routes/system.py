from __future__ import annotations

from fastapi import APIRouter

from app.core.config import get_settings
from app.db.session import check_database_health
from app.schemas.common import HealthDependencyStatus, HealthResponse
from app.services.email import EmailService
from app.services.pinecone_service import PineconeService
from app.utils.time import utcnow


settings = get_settings()
router = APIRouter(tags=["system"])


@router.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "status": "ok",
        "docs_url": "/docs",
        "health_url": "/health",
    }


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    email_service = EmailService()
    pinecone_service = PineconeService()
    pinecone_reachable, pinecone_detail = pinecone_service.check_health()

    return HealthResponse(
        status="ok",
        service=settings.app_name,
        timestamp=utcnow(),
        providers={
            "database": HealthDependencyStatus(
                configured=True,
                reachable=check_database_health(),
            ),
            "email": HealthDependencyStatus(
                configured=email_service.is_configured(),
                reachable=None,
                detail=None if email_service.is_configured() else "SMTP is not configured.",
            ),
            "pinecone": HealthDependencyStatus(
                configured=pinecone_service.is_configured(),
                reachable=pinecone_reachable,
                detail=pinecone_detail,
            ),
        },
    )

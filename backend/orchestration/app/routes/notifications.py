from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.exceptions import ApiError
from app.core.security import AuthContext, get_auth_context
from app.schemas.notifications import NotificationResponse
from app.services.notification_service import NotificationService


router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("/me", response_model=list[NotificationResponse])
async def my_notifications(
    context: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_db_session),
) -> list[NotificationResponse]:
    if not context.email:
        raise ApiError(
            status_code=400,
            code="missing_email_claim",
            message="Token must include an email claim.",
        )

    service = NotificationService(session)
    notifications = await service.list_notifications(recipient_email=context.email.lower())
    return [
        NotificationResponse(
            id=item.id,
            recipient_email=item.recipient_email,
            notification_type=item.notification_type,
            subject=item.subject,
            body=item.body,
            html_body=(
                str((item.notification_metadata or {}).get("html_body"))
                if (item.notification_metadata or {}).get("html_body")
                else None
            ),
            status=item.status,
            metadata=item.notification_metadata or {},
            sent_at=item.sent_at,
            created_at=item.created_at,
        )
        for item in notifications
    ]

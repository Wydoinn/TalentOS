from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.models.enums import NotificationStatus, NotificationType


class NotificationResponse(BaseModel):
    id: str
    recipient_email: str
    notification_type: NotificationType
    subject: str
    body: str
    html_body: str | None = None
    status: NotificationStatus
    metadata: dict
    sent_at: datetime | None
    created_at: datetime

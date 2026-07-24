from __future__ import annotations

import base64
import json
from urllib.parse import parse_qs, urlparse

from app.core.config import Settings
from app.models.enums import NotificationType
from app.services.notification_service import NotificationService


def _decode_payload(encoded: str) -> dict[str, str]:
    padded = encoded + ("=" * ((4 - len(encoded) % 4) % 4))
    raw = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
    return json.loads(raw)


async def test_notification_service_builds_encoded_invite_and_session_links(db_session):
    settings = Settings(candidate_portal_base_url="https://talentos.example.com")
    service = NotificationService(db_session, settings)

    invite_link = service.build_invitation_link(
        invitation_token="invite-token-123",
        candidate_email="candidate@example.com",
        job_id="job-001",
    )

    session_link = service.build_session_link(
        invitation_token="invite-token-123",
        candidate_email="candidate@example.com",
        job_id="job-001",
        schedule_id="sched-123",
        slot_id="slot-456",
    )

    invite_query = parse_qs(urlparse(invite_link).query)
    session_query = parse_qs(urlparse(session_link).query)

    assert invite_link.startswith("https://talentos.example.com/auth/candidate/access?invite=")
    assert session_link.startswith("https://talentos.example.com/auth/candidate/access?session=")

    invite_payload = _decode_payload(invite_query["invite"][0])
    session_payload = _decode_payload(session_query["session"][0])

    assert invite_payload == {
        "candidate_email": "candidate@example.com",
        "flow": "invite",
        "invitation_token": "invite-token-123",
        "job_id": "job-001",
    }

    assert session_payload == {
        "candidate_email": "candidate@example.com",
        "flow": "l0_session",
        "invitation_token": "invite-token-123",
        "job_id": "job-001",
        "schedule_id": "sched-123",
        "slot_id": "slot-456",
    }


async def test_notification_service_renders_html_email_metadata(db_session):
    service = NotificationService(db_session, Settings(candidate_portal_base_url="https://talentos.example.com"))

    notification = await service.send_notification(
        recipient_email="candidate@example.com",
        notification_type=NotificationType.L0_INVITE,
        subject="Interview Invitation",
        body="Plain text body",
        metadata={
            "greeting_name": "Jordan",
            "headline": "Welcome to the next stage",
            "cta_label": "Continue",
            "cta_url": "https://talentos.example.com/auth/candidate/access?invite=test",
            "highlights": [{"label": "Role", "value": "Backend Engineer"}],
        },
    )

    html_body = (notification.notification_metadata or {}).get("html_body")
    assert isinstance(html_body, str)
    assert "#CB1E4B" in html_body
    assert "Welcome to the next stage" in html_body
    assert "Continue" in html_body

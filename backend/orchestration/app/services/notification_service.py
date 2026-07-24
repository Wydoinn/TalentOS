from __future__ import annotations

import base64
import html
import json
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.models.entities import Notification
from app.models.enums import NotificationStatus, NotificationType


class NotificationService:
    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()

    def is_email_configured(self) -> bool:
        return bool(self.settings.smtp_host and self.settings.smtp_from_email)

    def build_invitation_link(
        self,
        *,
        invitation_token: str,
        candidate_email: str,
        job_id: str,
    ) -> str:
        encoded = self._encode_candidate_access_payload(
            {
                "flow": "invite",
                "invitation_token": invitation_token,
                "candidate_email": candidate_email,
                "job_id": job_id,
            }
        )
        base = self.settings.candidate_portal_base_url.rstrip("/")
        return f"{base}/auth/candidate/access?invite={quote(encoded, safe='')}"

    def build_session_link(
        self,
        *,
        invitation_token: str,
        candidate_email: str,
        job_id: str,
        schedule_id: str,
        slot_id: str,
    ) -> str:
        encoded = self._encode_candidate_access_payload(
            {
                "flow": "l0_session",
                "invitation_token": invitation_token,
                "candidate_email": candidate_email,
                "job_id": job_id,
                "schedule_id": schedule_id,
                "slot_id": slot_id,
            }
        )
        base = self.settings.candidate_portal_base_url.rstrip("/")
        return f"{base}/auth/candidate/access?session={quote(encoded, safe='')}"

    async def send_notification(
        self,
        *,
        recipient_email: str,
        notification_type: NotificationType,
        subject: str,
        body: str,
        html_body: str | None = None,
        metadata: dict | None = None,
    ) -> Notification:
        resolved_metadata = dict(metadata or {})
        resolved_html_body = html_body or self._render_html_email(
            subject=subject,
            body=body,
            metadata=resolved_metadata,
        )
        resolved_metadata.setdefault("html_body", resolved_html_body)

        notification = Notification(
            recipient_email=recipient_email,
            notification_type=notification_type,
            subject=subject,
            body=body,
            notification_metadata=resolved_metadata,
            status=NotificationStatus.QUEUED,
        )
        self.session.add(notification)
        await self.session.flush()

        if self.is_email_configured():
            try:
                self._send_email(
                    recipient_email=recipient_email,
                    subject=subject,
                    body=body,
                    html_body=resolved_html_body,
                )
                notification.status = NotificationStatus.SENT
                notification.sent_at = datetime.now(timezone.utc)
            except Exception as exc:
                notification.status = NotificationStatus.FAILED
                notification.notification_metadata = {
                    **(notification.notification_metadata or {}),
                    "delivery_error": str(exc),
                }
        await self.session.flush()
        return notification

    async def list_notifications(self, *, recipient_email: str) -> list[Notification]:
        records = await self.session.scalars(
            select(Notification)
            .where(Notification.recipient_email == recipient_email)
            .order_by(Notification.created_at.desc())
        )
        return list(records)

    def _send_email(
        self,
        *,
        recipient_email: str,
        subject: str,
        body: str,
        html_body: str | None = None,
    ) -> None:
        message = EmailMessage()
        message["From"] = self.settings.smtp_from_email
        message["To"] = recipient_email
        message["Subject"] = subject
        message.set_content(body)
        if html_body:
            message.add_alternative(html_body, subtype="html")

        if self.settings.smtp_use_ssl:
            with smtplib.SMTP_SSL(
                self.settings.smtp_host,
                self.settings.smtp_port,
                timeout=self.settings.smtp_timeout_seconds,
            ) as server:
                if self.settings.smtp_username:
                    server.login(self.settings.smtp_username, self.settings.smtp_password or "")
                server.send_message(message)
            return

        with smtplib.SMTP(
            self.settings.smtp_host,
            self.settings.smtp_port,
            timeout=self.settings.smtp_timeout_seconds,
        ) as server:
            if self.settings.smtp_use_tls:
                server.starttls()
            if self.settings.smtp_username:
                server.login(self.settings.smtp_username, self.settings.smtp_password or "")
            server.send_message(message)

    def _render_html_email(self, *, subject: str, body: str, metadata: dict) -> str:
        greeting_name = self._read_text(metadata.get("greeting_name")) or "there"
        headline = self._read_text(metadata.get("headline")) or subject
        preheader = self._read_text(metadata.get("preheader")) or headline
        intro = self._coerce_text_list(metadata.get("intro")) or [
            block.strip()
            for block in body.split("\n\n")
            if block.strip()
        ]
        highlights = self._coerce_highlights(metadata.get("highlights"))
        steps = self._coerce_text_list(metadata.get("steps"))
        cta_url = self._read_text(metadata.get("cta_url"))
        cta_label = self._read_text(metadata.get("cta_label")) or "Open TalentOS"
        footer_note = (
            self._read_text(metadata.get("footer_note"))
            or "This is an automated TalentOS notification. Please do not share secure links."
        )

        intro_html = "".join(
            f"<p style='margin:0 0 14px;color:#4b4b68;font-size:15px;line-height:1.7;'>{html.escape(paragraph)}</p>"
            for paragraph in intro
        )

        highlights_html = ""
        if highlights:
            highlight_rows = "".join(
                (
                    "<tr>"
                    f"<td style='padding:10px 0;color:#7a7b98;font-size:12px;text-transform:uppercase;letter-spacing:0.08em;'>"
                    f"{html.escape(item['label'])}</td>"
                    f"<td style='padding:10px 0;color:#202040;font-size:14px;font-weight:600;text-align:right;'>"
                    f"{html.escape(item['value'])}</td>"
                    "</tr>"
                )
                for item in highlights
            )
            highlights_html = (
                "<div style='margin:22px 0;padding:18px 20px;border:1px solid rgba(52,50,91,0.10);"
                "border-radius:18px;background:linear-gradient(180deg,#ffffff 0%,#f8f4fb 100%);'>"
                "<table role='presentation' width='100%' cellspacing='0' cellpadding='0' style='border-collapse:collapse;'>"
                f"{highlight_rows}</table></div>"
            )

        steps_html = ""
        if steps:
            step_items = "".join(
                (
                    "<li style='margin:0 0 12px;color:#34325B;font-size:14px;line-height:1.6;'>"
                    f"{html.escape(step)}</li>"
                )
                for step in steps
            )
            steps_html = (
                "<div style='margin:24px 0 0;'>"
                "<div style='margin:0 0 10px;color:#792F8C;font-size:12px;font-weight:700;"
                "letter-spacing:0.08em;text-transform:uppercase;'>Instructions</div>"
                f"<ol style='padding-left:20px;margin:0;'>{step_items}</ol>"
                "</div>"
            )

        cta_html = ""
        if cta_url:
            cta_html = (
                "<div style='margin:28px 0 0;'>"
                f"<a href='{html.escape(cta_url, quote=True)}' "
                "style='display:inline-block;padding:14px 24px;border-radius:999px;"
                "background:linear-gradient(135deg,#CB1E4B 0%,#A62568 48%,#792F8C 100%);"
                "color:#ffffff;font-size:14px;font-weight:700;text-decoration:none;'>"
                f"{html.escape(cta_label)}</a></div>"
            )

        return (
            "<!doctype html><html><head><meta charset='utf-8' />"
            f"<title>{html.escape(subject)}</title>"
            "</head><body style='margin:0;padding:0;background:#f4f2f8;'>"
            f"<div style='display:none;max-height:0;overflow:hidden;opacity:0;'>{html.escape(preheader)}</div>"
            "<table role='presentation' width='100%' cellspacing='0' cellpadding='0' style='border-collapse:collapse;'>"
            "<tr><td align='center' style='padding:28px 16px;'>"
            "<table role='presentation' width='100%' cellspacing='0' cellpadding='0' style='max-width:680px;border-collapse:collapse;'>"
            "<tr><td style='padding:0 0 18px;color:#34325B;font-size:12px;font-weight:700;"
            "letter-spacing:0.10em;text-transform:uppercase;'>TalentOS</td></tr>"
            "<tr><td style='background:#ffffff;border-radius:28px;overflow:hidden;"
            "box-shadow:0 24px 70px rgba(52,50,91,0.12);'>"
            "<div style='padding:34px 36px;background:linear-gradient(135deg,#fff7fa 0%,#f7effb 55%,#eff2ff 100%);"
            "border-bottom:1px solid rgba(52,50,91,0.08);'>"
            "<div style='margin:0 0 10px;color:#A62568;font-size:12px;font-weight:700;"
            "letter-spacing:0.10em;text-transform:uppercase;'>TalentOS Workflow Update</div>"
            f"<h1 style='margin:0;color:#232142;font-size:30px;line-height:1.2;font-weight:800;'>{html.escape(headline)}</h1>"
            f"<p style='margin:12px 0 0;color:#555579;font-size:15px;line-height:1.7;'>Hello {html.escape(greeting_name)},</p>"
            "</div>"
            "<div style='padding:30px 36px 34px;'>"
            f"{intro_html}{highlights_html}{steps_html}{cta_html}"
            "<div style='margin:28px 0 0;padding-top:18px;border-top:1px solid rgba(52,50,91,0.08);"
            "color:#77789a;font-size:12px;line-height:1.7;'>"
            f"{html.escape(footer_note)}</div></div></td></tr></table></td></tr></table></body></html>"
        )

    @staticmethod
    def _encode_candidate_access_payload(payload: dict[str, str]) -> str:
        raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    @staticmethod
    def _read_text(value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @classmethod
    def _coerce_text_list(cls, value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        return [item for item in (cls._read_text(entry) for entry in value) if item]

    @classmethod
    def _coerce_highlights(cls, value: object) -> list[dict[str, str]]:
        if isinstance(value, dict):
            return [
                {"label": str(label).strip(), "value": str(item).strip()}
                for label, item in value.items()
                if str(label).strip() and str(item).strip()
            ]

        if not isinstance(value, list):
            return []

        normalized: list[dict[str, str]] = []
        for entry in value:
            if not isinstance(entry, dict):
                continue
            label = cls._read_text(entry.get("label"))
            value_text = cls._read_text(entry.get("value"))
            if label and value_text:
                normalized.append({"label": label, "value": value_text})
        return normalized

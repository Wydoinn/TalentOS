from __future__ import annotations

import html
import smtplib
import ssl
from email.message import EmailMessage

from app.api_errors import ApiException
from app.core.config import Settings, get_settings


class EmailService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def is_configured(self) -> bool:
        return bool(
            self.settings.smtp_host
            and self.settings.smtp_port
            and self.settings.smtp_from_email
        )

    def send_otp_email(self, *, email: str, otp_code: str) -> None:
        if not self.is_configured():
            raise ApiException(
                status_code=503,
                code="email_service_not_configured",
                message="Email delivery is not configured for OTP dispatch.",
            )

        message = self._build_otp_message(email=email, otp_code=otp_code)

        try:
            if self.settings.smtp_use_ssl:
                with smtplib.SMTP_SSL(
                    self.settings.smtp_host,
                    self.settings.smtp_port,
                    timeout=self.settings.smtp_timeout_seconds,
                ) as client:
                    self._authenticate(client)
                    client.send_message(message)
                return

            with smtplib.SMTP(
                self.settings.smtp_host,
                self.settings.smtp_port,
                timeout=self.settings.smtp_timeout_seconds,
            ) as client:
                if self.settings.smtp_use_tls:
                    client.ehlo()
                    client.starttls(context=ssl.create_default_context())
                    client.ehlo()
                self._authenticate(client)
                client.send_message(message)
        except (OSError, smtplib.SMTPException) as exc:
            raise ApiException(
                status_code=503,
                code="email_delivery_failed",
                message="Unable to deliver the OTP email right now.",
            ) from exc

    def _build_otp_message(self, *, email: str, otp_code: str) -> EmailMessage:
        message = EmailMessage()
        message["Subject"] = "Your TalentOS verification code"
        message["From"] = self.settings.smtp_from_email
        message["To"] = email
        message.set_content(self._otp_text_body(otp_code=otp_code))
        message.add_alternative(self._otp_html_body(otp_code=otp_code), subtype="html")
        return message

    def _otp_text_body(self, *, otp_code: str) -> str:
        return (
            "Hello,\n\n"
            "Use the following one-time verification code to continue in TalentOS:\n\n"
            f"{otp_code}\n\n"
            f"This code expires in {self.settings.otp_expiry_minutes} minutes and can be used once.\n\n"
            "Security reminders:\n"
            "- Never share this code with anyone.\n"
            "- TalentOS support will never ask for your OTP.\n\n"
            "If you did not request this code, you can safely ignore this email."
        )

    def _otp_html_body(self, *, otp_code: str) -> str:
        expiry = html.escape(str(self.settings.otp_expiry_minutes))
        code = html.escape(otp_code)
        return (
            "<!doctype html><html><head><meta charset='utf-8' />"
            "<title>Your TalentOS verification code</title></head>"
            "<body style='margin:0;padding:0;background:#f4f2f8;'>"
            "<table role='presentation' width='100%' cellspacing='0' cellpadding='0' style='border-collapse:collapse;'>"
            "<tr><td align='center' style='padding:28px 16px;'>"
            "<table role='presentation' width='100%' cellspacing='0' cellpadding='0' "
            "style='max-width:620px;border-collapse:collapse;'>"
            "<tr><td style='padding:0 0 18px;color:#34325B;font-size:12px;font-weight:700;"
            "letter-spacing:0.10em;text-transform:uppercase;'>TalentOS</td></tr>"
            "<tr><td style='background:#ffffff;border-radius:28px;overflow:hidden;"
            "box-shadow:0 24px 70px rgba(52,50,91,0.12);'>"
            "<div style='padding:34px 36px;background:linear-gradient(135deg,#fff7fa 0%,#f7effb 55%,#eff2ff 100%);"
            "border-bottom:1px solid rgba(52,50,91,0.08);'>"
            "<div style='margin:0 0 10px;color:#A62568;font-size:12px;font-weight:700;"
            "letter-spacing:0.10em;text-transform:uppercase;'>Secure Sign In</div>"
            "<h1 style='margin:0;color:#232142;font-size:30px;line-height:1.2;font-weight:800;'>Your verification code</h1>"
            "<p style='margin:12px 0 0;color:#555579;font-size:15px;line-height:1.7;'>Use this one-time code to continue in TalentOS.</p>"
            "</div>"
            "<div style='padding:32px 36px 36px;'>"
            "<div style='display:inline-block;padding:16px 22px;border-radius:20px;background:#34325B;"
            "color:#ffffff;font-size:32px;font-weight:800;letter-spacing:0.28em;'>"
            f"{code}</div>"
            f"<p style='margin:20px 0 0;color:#4b4b68;font-size:15px;line-height:1.7;'>This code expires in {expiry} minutes and can be used once.</p>"
            "<div style='margin:22px 0 0;padding:18px 20px;border:1px solid rgba(52,50,91,0.10);"
            "border-radius:18px;background:linear-gradient(180deg,#ffffff 0%,#f8f4fb 100%);'>"
            "<div style='margin:0 0 8px;color:#792F8C;font-size:12px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;'>Security reminders</div>"
            "<ul style='padding-left:18px;margin:0;color:#34325B;font-size:14px;line-height:1.7;'>"
            "<li>Never share this code with anyone.</li>"
            "<li>TalentOS support will never ask for your OTP.</li>"
            "</ul></div>"
            "<div style='margin:24px 0 0;padding-top:18px;border-top:1px solid rgba(52,50,91,0.08);"
            "color:#77789a;font-size:12px;line-height:1.7;'>If you did not request this code, you can safely ignore this email.</div>"
            "</div></td></tr></table></td></tr></table></body></html>"
        )

    def _authenticate(self, client: smtplib.SMTP) -> None:
        if self.settings.smtp_username and self.settings.smtp_password:
            client.login(self.settings.smtp_username, self.settings.smtp_password)

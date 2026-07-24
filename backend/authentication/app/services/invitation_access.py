from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.api_errors import ApiException
from app.core.config import Settings, get_settings


@dataclass(frozen=True, slots=True)
class CandidateInvitationValidationResult:
    valid: bool
    candidate_email: str | None = None
    schedule_status: str | None = None
    job_id: str | None = None
    schedule_id: str | None = None
    slot_id: str | None = None


class InvitationAccessService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def validate_candidate_invitation(
        self,
        *,
        invitation_token: str,
        candidate_email: str,
        flow: str = "invite",
        schedule_id: str | None = None,
        slot_id: str | None = None,
    ) -> CandidateInvitationValidationResult:
        base_url = self.settings.orchestration_service_url.strip().rstrip("/")
        if not base_url:
            raise ApiException(
                status_code=503,
                code="invitation_validation_unavailable",
                message="Candidate invitation validation is unavailable right now.",
            )

        payload = json.dumps(
            {
                "invitation_token": invitation_token,
                "candidate_email": candidate_email,
                "flow": flow,
                "schedule_id": schedule_id,
                "slot_id": slot_id,
            }
        ).encode("utf-8")

        request = Request(
            url=f"{base_url}/internal/candidate-access/validate",
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        service_token = (self.settings.orchestration_service_token or "").strip()
        if service_token:
            request.add_header("X-Service-Token", service_token)

        try:
            with urlopen(
                request,
                timeout=self.settings.orchestration_service_timeout_seconds,
            ) as response:
                raw_body = response.read().decode("utf-8")
        except HTTPError as exc:
            if exc.code in {401, 403}:
                raise ApiException(
                    status_code=503,
                    code="invitation_validation_denied",
                    message="Candidate invitation validation is unavailable right now.",
                ) from exc
            raise ApiException(
                status_code=503,
                code="invitation_validation_failed",
                message="Unable to validate candidate invitation right now.",
            ) from exc
        except (URLError, OSError) as exc:
            raise ApiException(
                status_code=503,
                code="invitation_validation_failed",
                message="Unable to validate candidate invitation right now.",
            ) from exc

        try:
            payload_json = json.loads(raw_body) if raw_body else {}
        except json.JSONDecodeError as exc:
            raise ApiException(
                status_code=503,
                code="invitation_validation_failed",
                message="Unable to validate candidate invitation right now.",
            ) from exc

        matched_email = str(payload_json.get("candidate_email") or "").strip().lower() or None
        normalized_email = candidate_email.strip().lower()
        valid = bool(payload_json.get("valid")) and matched_email == normalized_email

        return CandidateInvitationValidationResult(
            valid=valid,
            candidate_email=matched_email,
            schedule_status=str(payload_json.get("schedule_status") or "").strip() or None,
            job_id=str(payload_json.get("job_id") or "").strip() or None,
            schedule_id=str(payload_json.get("schedule_id") or "").strip() or None,
            slot_id=str(payload_json.get("slot_id") or "").strip() or None,
        )

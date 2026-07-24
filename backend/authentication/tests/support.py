from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from fastapi.testclient import TestClient

from app.services import face_verification as face_verification_module
from app.services.invitation_access import CandidateInvitationValidationResult


TEST_OTP = "123456"
TEST_INVITATION_TOKEN = "invite-token-1234567890"


def unit_embedding(axis: int) -> np.ndarray:
    vector = np.zeros(512, dtype=np.float32)
    vector[axis] = 1.0
    return vector


def mock_otp_delivery(monkeypatch, otp_code: str = TEST_OTP) -> list[dict[str, str]]:
    deliveries: list[dict[str, str]] = []

    def fake_send(self, *, email: str, otp_code: str) -> None:
        deliveries.append({"email": email, "otp_code": otp_code})

    monkeypatch.setattr("app.services.auth.generate_otp_code", lambda _: otp_code)
    monkeypatch.setattr("app.services.email.EmailService.send_otp_email", fake_send)

    def fake_validate_invitation(
        self,
        *,
        invitation_token: str,
        candidate_email: str,
        flow: str = "invite",
        schedule_id: str | None = None,
        slot_id: str | None = None,
    ):
        return CandidateInvitationValidationResult(
            valid=bool(invitation_token),
            candidate_email=candidate_email.strip().lower(),
            schedule_status="BOOKED" if flow == "l0_session" else "INVITED",
            job_id="job-test",
            schedule_id=schedule_id or "schedule-test",
            slot_id=slot_id or "slot-test",
        )

    monkeypatch.setattr(
        "app.services.invitation_access.InvitationAccessService.validate_candidate_invitation",
        fake_validate_invitation,
    )
    return deliveries


@dataclass(slots=True)
class FakeFaceEnvironment:
    stored_embeddings: dict[str, np.ndarray] = field(default_factory=dict)
    behaviors: dict[bytes, np.ndarray | Exception] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.behaviors.setdefault(b"registration-image", unit_embedding(0))
        self.behaviors.setdefault(b"verification-image", unit_embedding(0))
        self.behaviors.setdefault(b"verification-mismatch", unit_embedding(1))

    def set_embedding(self, image_bytes: bytes, *, axis: int) -> None:
        self.behaviors[image_bytes] = unit_embedding(axis)

    def set_error(self, image_bytes: bytes, error: Exception) -> None:
        self.behaviors[image_bytes] = error

    def resolve_embedding(self, image_bytes: bytes) -> np.ndarray:
        behavior = self.behaviors.get(image_bytes, self.behaviors[b"verification-image"])
        if isinstance(behavior, Exception):
            raise behavior
        return np.asarray(behavior, dtype=np.float32).copy()


def install_face_services(monkeypatch, environment: FakeFaceEnvironment) -> FakeFaceEnvironment:
    class FakeFaceEmbeddingService:
        def extract_normalized_embedding(
            self,
            image_bytes: bytes,
            *,
            image_label: str = "image",
        ) -> np.ndarray:
            return environment.resolve_embedding(image_bytes)

    class FakePineconeService:
        def __init__(self, settings=None) -> None:
            self.settings = settings

        def upsert_user_embedding(self, *, user_id: str, embedding: np.ndarray, role) -> None:
            environment.stored_embeddings[user_id] = np.asarray(embedding, dtype=np.float32)

        def fetch_user_embedding(self, *, user_id: str) -> np.ndarray:
            return environment.stored_embeddings[user_id]

        def delete_user_embedding(self, *, user_id: str) -> None:
            environment.stored_embeddings.pop(user_id, None)

    monkeypatch.setattr(
        face_verification_module,
        "get_face_embedding_service",
        lambda: FakeFaceEmbeddingService(),
    )
    monkeypatch.setattr(face_verification_module, "PineconeService", FakePineconeService)
    return environment


@dataclass(frozen=True, slots=True)
class AuthenticationApiClient:
    client: TestClient

    def root(self):
        return self.client.get("/")

    def health(self):
        return self.client.get("/health")

    def send_signup_otp(self, *, email: str, role: str, invitation_token: str | None = None):
        payload: dict[str, str] = {"email": email, "role": role}
        if invitation_token:
            payload["invitation_token"] = invitation_token
        return self.client.post(
            "/auth/signup/send-otp",
            json=payload,
        )

    def verify_signup_otp(
        self,
        *,
        email: str,
        role: str,
        otp_code: str = TEST_OTP,
        invitation_token: str | None = None,
    ):
        payload: dict[str, str] = {"email": email, "role": role, "otp_code": otp_code}
        if invitation_token:
            payload["invitation_token"] = invitation_token
        return self.client.post(
            "/auth/signup/verify-otp",
            json=payload,
        )

    def send_login_otp(self, *, email: str, role: str, invitation_token: str | None = None):
        payload: dict[str, str] = {"email": email, "role": role}
        if invitation_token:
            payload["invitation_token"] = invitation_token
        return self.client.post(
            "/auth/login/send-otp",
            json=payload,
        )

    def verify_login_otp(
        self,
        *,
        email: str,
        role: str,
        otp_code: str = TEST_OTP,
        invitation_token: str | None = None,
    ):
        payload: dict[str, str] = {"email": email, "role": role, "otp_code": otp_code}
        if invitation_token:
            payload["invitation_token"] = invitation_token
        return self.client.post(
            "/auth/login/verify-otp",
            json=payload,
        )

    def validate_candidate_access(
        self,
        *,
        email: str,
        invitation_token: str,
        flow: str = "invite",
        schedule_id: str | None = None,
        slot_id: str | None = None,
    ):
        payload: dict[str, str] = {
            "email": email,
            "invitation_token": invitation_token,
            "flow": flow,
        }
        if schedule_id:
            payload["schedule_id"] = schedule_id
        if slot_id:
            payload["slot_id"] = slot_id
        return self.client.post("/auth/candidate-access/validate", json=payload)

    def register_face(
        self,
        *,
        token: str | None,
        image_bytes: bytes = b"registration-image",
        filename: str = "register.jpg",
        content_type: str = "image/jpeg",
    ):
        headers = {}
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"

        return self.client.post(
            "/candidate/register-face",
            headers=headers,
            files={"image": (filename, image_bytes, content_type)},
        )

    def verify_face(
        self,
        *,
        token: str | None,
        image_bytes: bytes = b"verification-image",
        filename: str = "verify.jpg",
        content_type: str = "image/jpeg",
        device_info: str | None = None,
        user_agent: str | None = None,
    ):
        headers = {}
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        if user_agent is not None:
            headers["User-Agent"] = user_agent

        data: dict[str, str] = {}
        if device_info is not None:
            data["device_info"] = device_info

        return self.client.post(
            "/candidate/verify-face",
            headers=headers,
            data=data,
            files={"image": (filename, image_bytes, content_type)},
        )

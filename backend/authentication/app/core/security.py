from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from random import SystemRandom
from typing import Any

import jwt

from app.api_errors import ApiException
from app.core.config import get_settings
from app.core.enums import AuthStage, UserRole


@dataclass(frozen=True, slots=True)
class TokenBundle:
    access_token: str
    token_type: str
    expires_at: datetime
    expires_in_seconds: int


def normalize_email(email: str) -> str:
    return email.strip().lower()


def generate_otp_code(length: int) -> str:
    random_source = SystemRandom()
    return "".join(str(random_source.randrange(10)) for _ in range(length))


def hash_otp_code(*, email: str, role: UserRole, otp_code: str) -> str:
    settings = get_settings()
    payload = f"{normalize_email(email)}:{role.value}:{otp_code}".encode("utf-8")
    return hmac.new(
        settings.otp_secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()


def verify_otp_code(*, email: str, role: UserRole, otp_code: str, otp_hash: str) -> bool:
    candidate_hash = hash_otp_code(email=email, role=role, otp_code=otp_code)
    return hmac.compare_digest(candidate_hash, otp_hash)


def create_access_token(
    *,
    user_id: str,
    role: UserRole,
    stage: AuthStage,
    extra_claims: dict[str, Any] | None = None,
) -> TokenBundle:
    settings = get_settings()
    issued_at = datetime.now(timezone.utc)
    ttl_minutes = (
        settings.pending_token_ttl_minutes
        if stage != AuthStage.AUTHENTICATED
        else settings.access_token_ttl_minutes
    )
    expires_at = issued_at + timedelta(minutes=ttl_minutes)

    payload: dict[str, Any] = {
        "sub": user_id,
        "role": role.value,
        "stage": stage.value,
        "type": "access",
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    if extra_claims:
        payload.update(extra_claims)

    token = jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return TokenBundle(
        access_token=token,
        token_type="bearer",
        expires_at=expires_at,
        expires_in_seconds=int((expires_at - issued_at).total_seconds()),
    )


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.InvalidTokenError as exc:
        raise ApiException(
            status_code=401,
            code="invalid_token",
            message="The access token is invalid or expired.",
        ) from exc

    if payload.get("type") != "access":
        raise ApiException(
            status_code=401,
            code="invalid_token_type",
            message="The supplied token type is not accepted.",
        )
    return payload

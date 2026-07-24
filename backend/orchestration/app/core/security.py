from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings
from app.core.exceptions import ApiError
from app.models.enums import UserRole


bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True, slots=True)
class AuthContext:
    user_id: str
    email: str | None
    role: UserRole
    stage: str
    token: str


def decode_auth_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.auth_jwt_secret_key,
            algorithms=[settings.auth_jwt_algorithm],
        )
    except jwt.InvalidTokenError as exc:
        raise ApiError(
            status_code=401,
            code="invalid_token",
            message="The access token is invalid or expired.",
        ) from exc

    if payload.get("type") != "access":
        raise ApiError(
            status_code=401,
            code="invalid_token_type",
            message="Unsupported token type.",
        )
    return payload


def get_auth_context(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> AuthContext:
    if credentials is None:
        raise ApiError(
            status_code=401,
            code="missing_token",
            message="Bearer token is required.",
        )

    payload = decode_auth_token(credentials.credentials)
    user_id = str(payload.get("sub") or "")
    role_value = payload.get("role")
    stage = str(payload.get("stage") or "")
    email = payload.get("email")

    if not user_id or not role_value or not stage:
        raise ApiError(
            status_code=401,
            code="invalid_token_payload",
            message="Token payload is incomplete.",
        )

    try:
        role = UserRole(role_value)
    except ValueError as exc:
        raise ApiError(
            status_code=401,
            code="invalid_token_payload",
            message="Token role is invalid.",
        ) from exc

    return AuthContext(
        user_id=user_id,
        email=str(email) if email else None,
        role=role,
        stage=stage,
        token=credentials.credentials,
    )


def require_roles(*roles: UserRole):
    role_set = set(roles)

    def dependency(context: AuthContext = Depends(get_auth_context)) -> AuthContext:
        if context.role not in role_set:
            raise ApiError(
                status_code=403,
                code="insufficient_role",
                message="You do not have permission for this action.",
            )
        return context

    return dependency

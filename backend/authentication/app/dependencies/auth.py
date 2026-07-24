from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.api_errors import ApiException
from app.core.enums import AuthStage, UserRole
from app.core.security import decode_access_token
from app.db.models import User
from app.db.session import get_db


bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True, slots=True)
class AuthenticatedContext:
    user: User
    role: UserRole
    stage: AuthStage


def get_current_context(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> AuthenticatedContext:
    if credentials is None:
        raise ApiException(
            status_code=401,
            code="missing_token",
            message="An access token is required for this endpoint.",
        )

    payload = decode_access_token(credentials.credentials)
    user_id = payload.get("sub")
    role_value = payload.get("role")
    stage_value = payload.get("stage")

    if not user_id or not role_value or not stage_value:
        raise ApiException(
            status_code=401,
            code="invalid_token_payload",
            message="The access token payload is incomplete.",
        )

    try:
        user_uuid = uuid.UUID(str(user_id))
        role = UserRole(role_value)
        stage = AuthStage(stage_value)
    except ValueError as exc:
        raise ApiException(
            status_code=401,
            code="invalid_token_payload",
            message="The access token contains invalid authorization claims.",
        ) from exc

    user = db.get(User, user_uuid)
    if user is None:
        raise ApiException(
            status_code=401,
            code="user_not_found",
            message="The user for this access token no longer exists.",
        )

    if user.role != role:
        raise ApiException(
            status_code=401,
            code="role_mismatch",
            message="The access token role does not match the current user record.",
        )

    return AuthenticatedContext(user=user, role=role, stage=stage)


def require_roles(*roles: UserRole, allow_stages: set[AuthStage] | None = None):
    role_set = set(roles)

    def dependency(
        context: AuthenticatedContext = Depends(get_current_context),
    ) -> AuthenticatedContext:
        if context.role not in role_set:
            raise ApiException(
                status_code=403,
                code="insufficient_role",
                message="You do not have permission to access this resource.",
            )

        if allow_stages is not None and context.stage not in allow_stages:
            raise ApiException(
                status_code=403,
                code="invalid_auth_stage",
                message="The current token is not authorized for this action.",
            )

        return context

    return dependency

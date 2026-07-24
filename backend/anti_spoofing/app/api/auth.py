"""JWT auth helpers for session-scoped access tokens."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import ExpiredSignatureError, JWTError, jwt

from app.config import get_settings

settings = get_settings()
bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def create_session_token(session_id: str, candidate_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": session_id,
        "cid": candidate_id,
        "exp": now + timedelta(minutes=settings.JWT_EXPIRE_MINUTES),
        "iat": now,
        "type": "session",
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_session_token(token: str) -> dict[str, object]:
    try:
        return jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except ExpiredSignatureError:
        raise _unauthorized("Token has expired - create a new session") from None
    except JWTError as exc:
        raise _unauthorized(f"Invalid token: {exc}") from exc


async def require_session_token(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> dict[str, object]:
    if credentials is None:
        raise _unauthorized("Authorization header required")
    return decode_session_token(credentials.credentials)

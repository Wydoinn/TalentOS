from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.core.security import TokenBundle


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime
    expires_in_seconds: int

    @classmethod
    def from_token_bundle(cls, token: TokenBundle) -> "TokenResponse":
        return cls(
            access_token=token.access_token,
            token_type=token.token_type,
            expires_at=token.expires_at,
            expires_in_seconds=token.expires_in_seconds,
        )


class HealthDependencyStatus(BaseModel):
    configured: bool
    reachable: bool | None = None
    detail: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    timestamp: datetime
    providers: dict[str, HealthDependencyStatus]

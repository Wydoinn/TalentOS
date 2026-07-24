from __future__ import annotations

import json
import uuid
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from app.api.schemas import OverallStatus, SessionStatus
from app.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


@dataclass
class SessionData:
    session_id: str
    candidate_id: str
    job_id: str | None
    metadata: dict
    status: SessionStatus
    created_at: datetime
    expires_at: datetime
    retry_count: int = 0
    trust_score: float = settings.INITIAL_TRUST_SCORE
    anomaly_count: int = 0
    challenge: dict | None = None
    latest_result: dict | None = None
    challenge_verified: bool = False
    issue_history: list[str] = field(default_factory=list)
    last_challenge_type: str | None = None
    final_decision: OverallStatus | None = None
    finalized_at: datetime | None = None
    locked_at: datetime | None = None

    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) > self.expires_at

    def is_locked(self) -> bool:
        return self.status == SessionStatus.LOCKED or self.locked_at is not None

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "candidate_id": self.candidate_id,
            "job_id": self.job_id,
            "metadata": self.metadata,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "retry_count": self.retry_count,
            "trust_score": self.trust_score,
            "anomaly_count": self.anomaly_count,
            "challenge": self.challenge,
            "latest_result": self.latest_result,
            "challenge_verified": self.challenge_verified,
            "issue_history": self.issue_history,
            "last_challenge_type": self.last_challenge_type,
            "final_decision": self.final_decision.value if self.final_decision else None,
            "finalized_at": self.finalized_at.isoformat() if self.finalized_at else None,
            "locked_at": self.locked_at.isoformat() if self.locked_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SessionData":
        return cls(
            session_id=data["session_id"],
            candidate_id=data["candidate_id"],
            job_id=data.get("job_id"),
            metadata=data.get("metadata", {}),
            status=SessionStatus(data["status"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"]),
            retry_count=data.get("retry_count", 0),
            trust_score=data.get("trust_score", settings.INITIAL_TRUST_SCORE),
            anomaly_count=data.get("anomaly_count", 0),
            challenge=data.get("challenge"),
            latest_result=data.get("latest_result"),
            challenge_verified=data.get("challenge_verified", False),
            issue_history=data.get("issue_history", []),
            last_challenge_type=data.get("last_challenge_type"),
            final_decision=OverallStatus(data["final_decision"]) if data.get("final_decision") else None,
            finalized_at=datetime.fromisoformat(data["finalized_at"]) if data.get("finalized_at") else None,
            locked_at=datetime.fromisoformat(data["locked_at"]) if data.get("locked_at") else None,
        )


class MemorySessionStore:
    def __init__(self) -> None:
        self._store: dict[str, SessionData] = {}

    async def get(self, session_id: str) -> SessionData | None:
        session = self._store.get(session_id)
        if session is None:
            return None
        if session.is_expired():
            self._store.pop(session_id, None)
            return None
        return deepcopy(session)

    async def save(self, session: SessionData) -> None:
        self._store[session.session_id] = deepcopy(session)

    async def delete(self, session_id: str) -> None:
        self._store.pop(session_id, None)

    async def ping(self) -> bool:
        return True


class RedisSessionStore:
    _PREFIX = "antispoofing:session:"

    def __init__(self) -> None:
        self._client = None

    async def _get_client(self):
        if self._client is None:
            import redis.asyncio as aioredis

            self._client = aioredis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
            )
        return self._client

    def _key(self, session_id: str) -> str:
        return f"{self._PREFIX}{session_id}"

    async def get(self, session_id: str) -> SessionData | None:
        try:
            client = await self._get_client()
            raw = await client.get(self._key(session_id))
            if raw is None:
                return None
            session = SessionData.from_dict(json.loads(raw))
            if session.is_expired():
                await self.delete(session_id)
                return None
            return session
        except Exception as exc:
            logger.error("Redis GET failed: %s", exc)
            return None

    async def save(self, session: SessionData) -> None:
        try:
            client = await self._get_client()
            ttl = int((session.expires_at - datetime.now(timezone.utc)).total_seconds())
            if ttl > 0:
                await client.setex(
                    self._key(session.session_id),
                    ttl,
                    json.dumps(session.to_dict()),
                )
        except Exception as exc:
            logger.error("Redis SET failed: %s", exc)

    async def delete(self, session_id: str) -> None:
        try:
            await (await self._get_client()).delete(self._key(session_id))
        except Exception as exc:
            logger.error("Redis DEL failed: %s", exc)

    async def ping(self) -> bool:
        try:
            return bool(await (await self._get_client()).ping())
        except Exception:
            return False


_store: MemorySessionStore | RedisSessionStore | None = None


def get_session_store() -> MemorySessionStore | RedisSessionStore:
    global _store
    if _store is None:
        if settings.SESSION_STORE_BACKEND == "redis":
            logger.info("Using Redis session store")
            _store = RedisSessionStore()
        else:
            logger.info("Using in-memory session store")
            _store = MemorySessionStore()
    return _store


def reset_session_store() -> None:
    global _store
    _store = None


def make_session_id() -> str:
    return str(uuid.uuid4())


def make_challenge_id() -> str:
    return str(uuid.uuid4())[:8].upper()


def make_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(seconds=settings.SESSION_TTL_SECONDS)

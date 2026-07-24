from __future__ import annotations

import logging
from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Lock
from time import monotonic

from fastapi import Request

from app.api_errors import ApiException

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RateLimitWindow:
    timestamps: deque[float]


class InMemoryRateLimiter:
    """Single-process in-memory rate limiter.
    
    WARNING: This does NOT work across multiple workers/processes.
    For production multi-process deployments, use a Redis-backed limiter.
    This is suitable for single-worker local deployments.
    """

    def __init__(self) -> None:
        self._windows: dict[str, RateLimitWindow] = defaultdict(
            lambda: RateLimitWindow(timestamps=deque())
        )
        self._lock = Lock()

    def check(self, key: str, *, max_requests: int, window_seconds: int) -> None:
        current_time = monotonic()

        with self._lock:
            window = self._windows[key].timestamps
            # Evict expired timestamps
            while window and (current_time - window[0]) >= window_seconds:
                window.popleft()

            if len(window) >= max_requests:
                raise ApiException(
                    status_code=429,
                    code="rate_limit_exceeded",
                    message="Too many requests. Please try again shortly.",
                )

            window.append(current_time)


# Singleton limiter — swap with a Redis-backed implementation for multi-worker deployments
rate_limiter = InMemoryRateLimiter()


def rate_limit(*, scope: str, max_requests: int, window_seconds: int):
    """FastAPI dependency for rate limiting by IP + scope.
    
    Uses IP address as the rate-limit key. Note: In production behind a reverse
    proxy, ensure X-Forwarded-For is handled to get the real client IP.
    """
    async def dependency(request: Request) -> None:
        # Respect X-Forwarded-For when behind a trusted proxy
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()
        else:
            client_ip = request.client.host if request.client else "unknown"

        key = f"{scope}:{client_ip}"
        rate_limiter.check(
            key,
            max_requests=max_requests,
            window_seconds=window_seconds,
        )

    return dependency

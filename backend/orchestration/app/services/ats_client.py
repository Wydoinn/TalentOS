from __future__ import annotations

import httpx

from app.core.config import Settings, get_settings
from app.core.exceptions import ApiError


class ATSClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    async def run_resume_check(self, payload: dict) -> dict:
        try:
            async with httpx.AsyncClient(
                base_url=self.settings.ats_service_url,
                timeout=90.0,
            ) as client:
                response = await client.post("/api/resumes/check", json=payload)
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, dict):
                    raise ValueError("ATS response payload is malformed")
                return data
        except Exception as exc:
            raise ApiError(
                status_code=502,
                code="ats_unavailable",
                message=f"ATS service is unavailable: {exc}",
            ) from exc

    async def check_health(self) -> tuple[str, str | None]:
        try:
            async with httpx.AsyncClient(
                base_url=self.settings.ats_service_url,
                timeout=10.0,
            ) as client:
                response = await client.get("/api/health")
                response.raise_for_status()
            return "ok", None
        except Exception as exc:
            return "degraded", str(exc)

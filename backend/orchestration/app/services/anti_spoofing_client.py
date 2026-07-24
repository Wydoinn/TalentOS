from __future__ import annotations

from typing import Any

import httpx

from app.core.config import Settings, get_settings


class AntiSpoofingClientError(Exception):
    def __init__(self, message: str, status_code: int = 503) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class AntiSpoofingClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    async def create_session(self, *, candidate_id: str, job_id: str | None) -> dict | None:
        return await self._request_json(
            method="POST",
            path="/sessions",
            json={
                "candidate_id": candidate_id,
                "job_id": job_id,
                "metadata": {"source": "orchestration"},
            },
            timeout=self._timeout(),
        )

    async def get_session(self, *, session_id: str, access_token: str) -> dict | None:
        return await self._request_json(
            method="GET",
            path=f"/sessions/{session_id}",
            access_token=access_token,
            timeout=self._timeout(),
        )

    async def issue_challenge(
        self,
        *,
        session_id: str,
        access_token: str,
        challenge_type: str | None = None,
    ) -> dict | None:
        payload: dict[str, Any] = {}
        if challenge_type:
            payload["challenge_type"] = challenge_type

        return await self._request_json(
            method="POST",
            path=f"/sessions/{session_id}/challenge",
            access_token=access_token,
            json=payload,
            timeout=self._timeout(),
        )

    async def analyze(
        self,
        *,
        session_id: str,
        access_token: str,
        video_bytes: bytes,
        filename: str,
        content_type: str,
    ) -> dict | None:
        return await self._request_json(
            method="POST",
            path=f"/sessions/{session_id}/analyze",
            access_token=access_token,
            files={
                "video": (
                    filename,
                    video_bytes,
                    content_type,
                )
            },
            timeout=self._timeout(read=self.settings.anti_spoofing_analysis_timeout_seconds),
        )

    async def finalize(self, *, session_id: str, access_token: str) -> dict | None:
        return await self._request_json(
            method="POST",
            path=f"/sessions/{session_id}/finalize",
            access_token=access_token,
            timeout=self._timeout(),
        )

    async def lock(self, *, session_id: str, access_token: str) -> dict | None:
        return await self._request_json(
            method="POST",
            path=f"/sessions/{session_id}/lock",
            access_token=access_token,
            timeout=self._timeout(),
        )

    async def check_health(self) -> tuple[str, str | None]:
        try:
            async with httpx.AsyncClient(
                base_url=self.settings.anti_spoofing_service_url,
                timeout=self._timeout(),
            ) as client:
                response = await client.get("/health")
                response.raise_for_status()
            return "ok", None
        except Exception as exc:
            return "degraded", str(exc)

    async def _request_json(
        self,
        *,
        method: str,
        path: str,
        access_token: str | None = None,
        json: dict[str, Any] | None = None,
        files: dict[str, tuple[str, bytes, str]] | None = None,
        timeout: httpx.Timeout | None = None,
    ) -> dict:
        headers: dict[str, str] = {}
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"

        try:
            async with httpx.AsyncClient(
                base_url=self.settings.anti_spoofing_service_url,
                timeout=timeout or self._timeout(),
            ) as client:
                response = await client.request(
                    method=method,
                    url=path,
                    headers=headers,
                    json=json,
                    files=files,
                )
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, dict):
                    raise AntiSpoofingClientError(
                        "Anti-spoofing service returned an invalid response.",
                        status_code=502,
                    )
                return data
        except httpx.HTTPStatusError as exc:
            message = self._extract_error_message(exc.response)
            raise AntiSpoofingClientError(message, status_code=exc.response.status_code) from exc
        except httpx.HTTPError as exc:
            raise AntiSpoofingClientError(
                f"Unable to reach anti-spoofing service: {exc}",
                status_code=503,
            ) from exc

    def _timeout(self, *, read: float | None = None) -> httpx.Timeout:
        connect_timeout = max(float(self.settings.anti_spoofing_connect_timeout_seconds), 1.0)
        read_timeout = max(
            float(
                self.settings.anti_spoofing_read_timeout_seconds
                if read is None else read
            ),
            1.0,
        )
        return httpx.Timeout(
            connect=connect_timeout,
            read=read_timeout,
            write=read_timeout,
            pool=connect_timeout,
        )

    @staticmethod
    def _extract_error_message(response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            payload = None

        if isinstance(payload, dict):
            detail = payload.get("detail")
            if isinstance(detail, str) and detail.strip():
                return detail.strip()

            nested_error = payload.get("error")
            if isinstance(nested_error, str) and nested_error.strip():
                return nested_error.strip()

        text = response.text.strip()
        if text:
            return text

        return f"Anti-spoofing service returned HTTP {response.status_code}."

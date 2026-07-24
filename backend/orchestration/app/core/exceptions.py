from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ApiErrorField:
    field: str
    message: str


class ApiError(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        fields: list[ApiErrorField] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.fields = fields or []


def error_payload(
    *,
    code: str,
    message: str,
    fields: list[ApiErrorField] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "error": {
            "code": code,
            "message": message,
        }
    }
    if fields:
        payload["error"]["fields"] = [
            {"field": field.field, "message": field.message}
            for field in fields
        ]
    return payload

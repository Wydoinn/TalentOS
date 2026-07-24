from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel, Field


class ApiFieldError(BaseModel):
    field: str
    message: str


class ApiErrorDetail(BaseModel):
    code: str
    message: str
    fields: list[ApiFieldError] = Field(default_factory=list)


class ApiErrorResponse(BaseModel):
    error: ApiErrorDetail


@dataclass(slots=True)
class ApiException(Exception):
    status_code: int
    code: str
    message: str
    fields: list[ApiFieldError] = field(default_factory=list)


def build_error_response(
    *,
    code: str,
    message: str,
    fields: list[ApiFieldError] | None = None,
) -> dict[str, object]:
    return ApiErrorResponse(
        error=ApiErrorDetail(
            code=code,
            message=message,
            fields=fields or [],
        )
    ).model_dump()

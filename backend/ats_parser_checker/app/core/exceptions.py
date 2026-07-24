from typing import Any


class AppException(Exception):
    def __init__(
        self,
        detail: str,
        *,
        status_code: int = 400,
        code: str = "application_error",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code
        self.code = code
        self.metadata = metadata or {}


class NotFoundException(AppException):
    def __init__(self, detail: str, metadata: dict[str, Any] | None = None) -> None:
        super().__init__(
            detail,
            status_code=404,
            code="resource_not_found",
            metadata=metadata,
        )


class ConflictException(AppException):
    def __init__(self, detail: str, metadata: dict[str, Any] | None = None) -> None:
        super().__init__(
            detail,
            status_code=409,
            code="resource_conflict",
            metadata=metadata,
        )


class ValidationException(AppException):
    def __init__(self, detail: str, metadata: dict[str, Any] | None = None) -> None:
        super().__init__(
            detail,
            status_code=422,
            code="validation_error",
            metadata=metadata,
        )


class ExternalServiceException(AppException):
    def __init__(self, detail: str, metadata: dict[str, Any] | None = None) -> None:
        super().__init__(
            detail,
            status_code=503,
            code="external_service_error",
            metadata=metadata,
        )

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    error: dict


class HealthDependencyStatus(BaseModel):
    status: str
    detail: str | None = None


class HealthResponse(BaseModel):
    service: str
    version: str
    dependencies: dict[str, HealthDependencyStatus] = Field(default_factory=dict)

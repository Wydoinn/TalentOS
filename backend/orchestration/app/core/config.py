from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT.parent
ENV_PREFIX = "ORCH_"


def _strip_matching_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _read_dotenv(dotenv_path: Path) -> dict[str, str]:
    if not dotenv_path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = _strip_matching_quotes(value.strip())
        if key:
            values[key] = value
    return values


def _load_env_files() -> None:
    merged = {
        **_read_dotenv(BACKEND_ROOT / ".env"),
        **_read_dotenv(PROJECT_ROOT / ".env"),
    }
    for key, value in merged.items():
        os.environ.setdefault(key, value)


def _split_csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        case_sensitive=False,
        extra="ignore",
        env_prefix=ENV_PREFIX,
    )

    app_name: str = "TalentOS Orchestration API"
    app_version: str = "1.0.0"
    app_env: str = "development"
    debug: bool = False
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/orchestration"
    database_echo: bool = False

    cors_allowed_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]
    )

    auth_jwt_secret_key: str = "replace-with-a-shared-secret"
    auth_jwt_algorithm: str = "HS256"

    authentication_service_url: str = "http://127.0.0.1:8000"
    ats_service_url: str = "http://127.0.0.1:8090"
    anti_spoofing_service_url: str = "http://127.0.0.1:8080"
    anti_spoofing_connect_timeout_seconds: float = 15.0
    anti_spoofing_read_timeout_seconds: float = 20.0
    anti_spoofing_analysis_timeout_seconds: float = 180.0
    candidate_portal_base_url: str = "http://127.0.0.1:3000"
    internal_service_token: str = ""
    stt_backend: str = "whisper"
    stt_model_dir: Path = BACKEND_ROOT / "models" / "faster-whisper-large-v3-turbo"
    stt_device: str = "cpu"
    stt_compute_type: str = "int8"
    stt_beam_size: int = 1
    stt_language: str = "en"

    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3-flash-preview"

    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str | None = None
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False
    smtp_timeout_seconds: int = 15

    default_invite_top_n: int = 5
    invite_expiry_hours: int = 72
    schedule_reminder_lead_hours: int = 4
    assessment_heartbeat_timeout_seconds: int = 45

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def parse_cors_allowed_origins(cls, value: Any) -> Any:
        if isinstance(value, str):
            raw = value.strip()
            if not raw.startswith("["):
                return _split_csv(raw)
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _load_env_files()
    auth_shared_secret = os.getenv("AUTH_JWT_SECRET_KEY")
    if auth_shared_secret:
                os.environ.setdefault("ORCH_AUTH_JWT_SECRET_KEY", auth_shared_secret)
    settings = Settings()
    if isinstance(settings.cors_allowed_origins, str):
        settings.cors_allowed_origins = _split_csv(settings.cors_allowed_origins)
    return settings

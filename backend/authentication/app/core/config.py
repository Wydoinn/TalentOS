from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT.parent
ENV_PREFIX = "AUTH_"


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


def _split_csv(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _get_env(name: str, default: str | None = None) -> str | None:
    prefixed_name = f"{ENV_PREFIX}{name}"
    if prefixed_name in os.environ:
        return os.environ[prefixed_name]
    raw_value = os.getenv(name)
    if raw_value is not None:
        return raw_value
    return default


def _get_bool(name: str, default: bool) -> bool:
    raw_value = _get_env(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str
    app_version: str
    environment: str
    project_root: Path
    database_url: str
    database_echo: bool
    database_pool_size: int
    database_max_overflow: int
    model_root: Path
    max_upload_bytes: int
    jwt_secret_key: str
    jwt_algorithm: str
    access_token_ttl_minutes: int
    pending_token_ttl_minutes: int
    otp_expiry_minutes: int
    otp_length: int
    otp_secret: str
    smtp_host: str | None
    smtp_port: int
    smtp_username: str | None
    smtp_password: str | None
    smtp_from_email: str | None
    smtp_use_tls: bool
    smtp_use_ssl: bool
    smtp_timeout_seconds: int
    pinecone_api_key: str | None
    pinecone_index_name: str | None
    pinecone_namespace: str
    pinecone_cloud: str
    pinecone_region: str
    pinecone_auto_create_index: bool
    face_similarity_threshold: float
    max_face_attempts: int
    face_attempt_window_minutes: int
    send_otp_rate_limit: int
    send_otp_rate_window_seconds: int
    verify_otp_rate_limit: int
    verify_otp_rate_window_seconds: int
    register_face_rate_limit: int
    register_face_rate_window_seconds: int
    verify_face_rate_limit: int
    verify_face_rate_window_seconds: int
    cors_allow_origins: tuple[str, ...]
    cors_allow_origin_regex: str | None
    orchestration_service_url: str
    orchestration_service_token: str | None
    orchestration_service_timeout_seconds: int


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _load_env_files()
    jwt_secret_key = _get_env("JWT_SECRET_KEY", "change-me-in-production")
    otp_secret = _get_env("OTP_SECRET", jwt_secret_key)

    return Settings(
        app_name=_get_env("APP_NAME", "Authentication API"),
        app_version=_get_env("APP_VERSION", "1.0.0"),
        environment=_get_env("APP_ENV", "development"),
        project_root=PROJECT_ROOT,
        database_url=_get_env(
            "DATABASE_URL",
            "postgresql+psycopg2://postgres:postgres@localhost:5432/authentication",
        ),
        database_echo=_get_bool("DATABASE_ECHO", False),
        database_pool_size=int(_get_env("DATABASE_POOL_SIZE", "10")),
        database_max_overflow=int(_get_env("DATABASE_MAX_OVERFLOW", "20")),
        model_root=Path(_get_env("FACE_MODEL_ROOT", str(BACKEND_ROOT / "models"))),
        max_upload_bytes=int(_get_env("MAX_UPLOAD_BYTES", str(5 * 1024 * 1024))),
        jwt_secret_key=jwt_secret_key,
        jwt_algorithm=_get_env("JWT_ALGORITHM", "HS256"),
        access_token_ttl_minutes=int(_get_env("ACCESS_TOKEN_TTL_MINUTES", "60")),
        pending_token_ttl_minutes=int(_get_env("PENDING_TOKEN_TTL_MINUTES", "10")),
        otp_expiry_minutes=int(_get_env("OTP_EXPIRY_MINUTES", "5")),
        otp_length=int(_get_env("OTP_LENGTH", "6")),
        otp_secret=otp_secret,
        smtp_host=_get_env("SMTP_HOST"),
        smtp_port=int(_get_env("SMTP_PORT", "587")),
        smtp_username=_get_env("SMTP_USERNAME"),
        smtp_password=_get_env("SMTP_PASSWORD"),
        smtp_from_email=_get_env("SMTP_FROM_EMAIL"),
        smtp_use_tls=_get_bool("SMTP_USE_TLS", True),
        smtp_use_ssl=_get_bool("SMTP_USE_SSL", False),
        smtp_timeout_seconds=int(_get_env("SMTP_TIMEOUT_SECONDS", "15")),
        pinecone_api_key=_get_env("PINECONE_API_KEY"),
        pinecone_index_name=_get_env("PINECONE_INDEX_NAME"),
        pinecone_namespace=_get_env("PINECONE_NAMESPACE", "authentication"),
        pinecone_cloud=_get_env("PINECONE_CLOUD", "aws"),
        pinecone_region=_get_env("PINECONE_REGION", "us-east-1"),
        pinecone_auto_create_index=_get_bool("PINECONE_AUTO_CREATE_INDEX", True),
        face_similarity_threshold=float(_get_env("FACE_SIMILARITY_THRESHOLD", "0.6")),
        max_face_attempts=int(_get_env("MAX_FACE_ATTEMPTS", "5")),
        face_attempt_window_minutes=int(_get_env("FACE_ATTEMPT_WINDOW_MINUTES", "15")),
        send_otp_rate_limit=int(_get_env("SEND_OTP_RATE_LIMIT", "5")),
        send_otp_rate_window_seconds=int(_get_env("SEND_OTP_RATE_WINDOW_SECONDS", "60")),
        verify_otp_rate_limit=int(_get_env("VERIFY_OTP_RATE_LIMIT", "10")),
        verify_otp_rate_window_seconds=int(
            _get_env("VERIFY_OTP_RATE_WINDOW_SECONDS", "300")
        ),
        register_face_rate_limit=int(_get_env("REGISTER_FACE_RATE_LIMIT", "10")),
        register_face_rate_window_seconds=int(
            _get_env("REGISTER_FACE_RATE_WINDOW_SECONDS", "300")
        ),
        verify_face_rate_limit=int(_get_env("VERIFY_FACE_RATE_LIMIT", "15")),
        verify_face_rate_window_seconds=int(
            _get_env("VERIFY_FACE_RATE_WINDOW_SECONDS", "300")
        ),
        cors_allow_origins=_split_csv(_get_env("CORS_ALLOW_ORIGINS", "")),
        cors_allow_origin_regex=_get_env(
            "CORS_ALLOW_ORIGIN_REGEX",
            r"https?://(localhost|127\.0\.0\.1)(:\d+)?$",
        )
        or None,
        orchestration_service_url=_get_env(
            "ORCHESTRATION_SERVICE_URL",
            "http://127.0.0.1:8001",
        ),
        orchestration_service_token=_get_env("ORCHESTRATION_SERVICE_TOKEN"),
        orchestration_service_timeout_seconds=int(
            _get_env("ORCHESTRATION_SERVICE_TIMEOUT_SECONDS", "8")
        ),
    )

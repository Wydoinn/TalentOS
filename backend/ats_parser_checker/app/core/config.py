import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app.utils.documents import SUPPORTED_RESUME_EXTENSIONS

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT.parent
ENV_PREFIX = "ATS_"


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


def _apply_legacy_env_aliases() -> None:
    for field_name in Settings.model_fields:
        prefixed_name = f"{ENV_PREFIX}{field_name.upper()}"
        legacy_name = field_name.upper()
        if prefixed_name not in os.environ and legacy_name in os.environ:
            os.environ[prefixed_name] = os.environ[legacy_name]


def _make_absolute(path: Path) -> Path:
    expanded = path.expanduser()
    if not expanded.is_absolute():
        expanded = Path.cwd() / expanded
    return expanded.resolve(strict=False)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        case_sensitive=False,
        extra="ignore",
        env_prefix=ENV_PREFIX,
    )

    app_name: str = "ATS Parser and Checker API"
    app_version: str = "1.0.0"
    app_env: str = "development"
    debug: bool = False
    log_level: str = "INFO"
    api_prefix: str = "/api"
    cors_allowed_origins: list[str] = Field(default_factory=lambda: ["*"])

    database_url: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/ats_parser_checker"
    )
    pinecone_api_key: str | None = None
    pinecone_index_name: str = "candidate-resumes"
    pinecone_namespace: str = "candidates"
    pinecone_cloud: str = "aws"
    pinecone_region: str = "us-east-1"
    pinecone_metric: str = "cosine"
    vector_dimension: int = 1024
    pinecone_connect_timeout_seconds: int = 10
    pinecone_read_timeout_seconds: int = 15

    neo4j_uri: str | None = None
    neo4j_username: str | None = None
    neo4j_password: str | None = None
    neo4j_connect_timeout_seconds: int = 10
    neo4j_query_timeout_seconds: int = 15
    healthcheck_timeout_seconds: int = 4

    models_dir: Path = BACKEND_ROOT / "models"
    embedding_model_dir: Path = BACKEND_ROOT / "models" / "bge-large-en-v1.5"
    reranker_model_dir: Path = BACKEND_ROOT / "models" / "bge-reranker-base"
    resume_source_dir: Path = PROJECT_ROOT / "resumes"
    allowed_resume_extensions: Annotated[tuple[str, ...], NoDecode] = SUPPORTED_RESUME_EXTENSIONS
    resume_sync_interval_seconds: int = 15
    model_warmup_on_startup: bool = True
    reranker_batch_size: int = 16
    retrieval_top_k: int = 25
    candidate_pool_size: int = 20
    final_results_limit: int = 5
    hybrid_vector_weight: float = 0.7
    hybrid_lexical_weight: float = 0.3
    final_weight_retrieval: float = 0.30
    final_weight_graph: float = 0.15
    final_weight_reranker: float = 0.35
    final_weight_ats: float = 0.20
    experience_filter_grace_years: float = 1.0
    experience_penalty_min: float = 0.15
    experience_penalty_max: float = 0.30
    feedback_min_events_to_learn: int = 8
    feedback_max_weight_blend: float = 0.45
    diversity_skill_weight: float = 0.12
    diversity_experience_weight: float = 0.08
    diversity_dedup_penalty_weight: float = 0.18
    diversity_duplicate_threshold: float = 0.72

    @field_validator("debug", mode="before")
    @classmethod
    def parse_debug_flag(cls, value: object) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        lowered = str(value).strip().lower()
        if lowered in {"1", "true", "yes", "on", "debug", "development", "dev"}:
            return True
        if lowered in {"0", "false", "no", "off", "release", "production", "prod"}:
            return False
        raise ValueError("DEBUG must be a boolean-like value")

    @field_validator("database_url")
    @classmethod
    def validate_postgres_database_url(cls, value: str) -> str:
        if not value.startswith("postgresql+asyncpg://"):
            raise ValueError(
                "DATABASE_URL must use PostgreSQL with the asyncpg driver "
                "(postgresql+asyncpg://...)"
            )
        return value

    @field_validator("allowed_resume_extensions", mode="before")
    @classmethod
    def validate_allowed_resume_extensions(cls, value: object) -> tuple[str, ...]:
        if value is None:
            return SUPPORTED_RESUME_EXTENSIONS

        raw_values: list[str]
        if isinstance(value, str):
            raw_values = value.split(",")
        elif isinstance(value, (list, tuple, set)):
            raw_values = [str(item) for item in value]
        else:
            raise ValueError("ALLOWED_RESUME_EXTENSIONS must be a string or sequence")

        normalized: list[str] = []
        for item in raw_values:
            candidate = item.strip().lower()
            if not candidate:
                continue
            if not candidate.startswith("."):
                candidate = f".{candidate}"
            if candidate not in normalized:
                normalized.append(candidate)

        if not normalized:
            raise ValueError("At least one supported resume extension must be configured")

        unsupported = [
            extension
            for extension in normalized
            if extension not in SUPPORTED_RESUME_EXTENSIONS
        ]
        if unsupported:
            raise ValueError(
                "Only PDF and DOCX resume formats are supported: "
                + ", ".join(unsupported)
            )

        return tuple(normalized)

    @field_validator(
        "reranker_batch_size",
        "retrieval_top_k",
        "candidate_pool_size",
        "final_results_limit",
    )
    @classmethod
    def validate_positive_int_setting(cls, value: int) -> int:
        if value < 1:
            raise ValueError("Retrieval and reranker settings must be positive integers")
        return value

    @field_validator(
        "hybrid_vector_weight",
        "hybrid_lexical_weight",
        "final_weight_retrieval",
        "final_weight_graph",
        "final_weight_reranker",
        "final_weight_ats",
        "feedback_max_weight_blend",
        "diversity_skill_weight",
        "diversity_experience_weight",
        "diversity_dedup_penalty_weight",
        "diversity_duplicate_threshold",
        "experience_filter_grace_years",
        "experience_penalty_min",
        "experience_penalty_max",
    )
    @classmethod
    def validate_probability_like_setting(cls, value: float) -> float:
        if not 0 <= value <= 1:
            raise ValueError("Weight and threshold settings must be between 0 and 1")
        return value

    @field_validator("experience_filter_grace_years")
    @classmethod
    def validate_non_negative_float_setting(cls, value: float) -> float:
        if value < 0:
            raise ValueError("Experience filter grace must be non-negative")
        return value

    @field_validator("feedback_min_events_to_learn")
    @classmethod
    def validate_feedback_min_events(cls, value: int) -> int:
        if value < 1:
            raise ValueError("FEEDBACK_MIN_EVENTS_TO_LEARN must be a positive integer")
        return value

    @model_validator(mode="after")
    def validate_weight_groups(self) -> "Settings":
        hybrid_total = self.hybrid_vector_weight + self.hybrid_lexical_weight
        if hybrid_total <= 0:
            raise ValueError("Hybrid retrieval weights must sum to a positive value")

        final_total = (
            self.final_weight_retrieval
            + self.final_weight_graph
            + self.final_weight_reranker
            + self.final_weight_ats
        )
        if final_total <= 0:
            raise ValueError("Final ranking weights must sum to a positive value")
        return self

    @model_validator(mode="after")
    def resolve_paths(self) -> "Settings":
        self.models_dir = _make_absolute(self.models_dir)
        self.embedding_model_dir = _make_absolute(self.embedding_model_dir)
        self.reranker_model_dir = _make_absolute(self.reranker_model_dir)
        self.resume_source_dir = _make_absolute(self.resume_source_dir)
        return self


@lru_cache
def get_settings() -> Settings:
    _load_env_files()
    _apply_legacy_env_aliases()
    return Settings()

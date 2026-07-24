"""Application settings loaded from environment variables."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT.parent
ENV_PREFIX = "ANTI_SPOOFING_"


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
        prefixed_name = f"{ENV_PREFIX}{field_name}"
        legacy_name = field_name
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
        env_prefix=ENV_PREFIX,
    )

    APP_NAME: str = "AntiSpoofing API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    HOST: str = "0.0.0.0"
    PORT: int = 8080
    WORKERS: int = 1

    JWT_SECRET_KEY: str = "CHANGE_ME_VERY_LONG_SECRET_KEY_32+"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60
    ALLOWED_ORIGINS: list[str] = ["*"]

    SESSION_TTL_SECONDS: int = 3600
    MAX_RETRIES_BEFORE_FAIL: int = 3
    SESSION_STORE_BACKEND: Literal["redis", "memory"] = "memory"
    REDIS_URL: str = "redis://localhost:6379/0"

    MAX_FILE_SIZE_MB: int = 50
    MIN_VIDEO_DURATION_SEC: float = 4.0
    MAX_VIDEO_DURATION_SEC: float = 15.0
    FRAME_SAMPLE_RATE: int = 5
    MAX_FRAMES: int = 30

    MODELS_DIR: Path = BACKEND_ROOT / "models"
    INSIGHTFACE_MODEL_DIR: Path | None = None
    FACE_SPOOF_MODEL_PATH: Path | None = None
    AUDIO_SPOOF_MODEL_DIR: Path | None = None
    STT_MODEL_DIR: Path | None = None
    DEVICE: str = "cpu"
    MODEL_WARMUP: bool = True

    FACE_DETECTION_MIN_CONFIDENCE: float = 0.6
    FACE_MIN_SIZE_PX: int = 60
    FACE_ALIGN_SIZE: int = 112
    INSIGHTFACE_DET_SIZE: int = 640

    FACE_SPOOF_INPUT_SIZE: int = 128
    FACE_SPOOF_CROP_SCALE: float = 1.6
    FACE_SPOOF_REAL_INDEX: int = 0
    FACE_SPOOF_MEAN: Annotated[list[float], NoDecode] = [151.2405, 119.5950, 107.8395]
    FACE_SPOOF_STD: Annotated[list[float], NoDecode] = [63.0105, 56.4570, 55.0035]
    FAS_THRESHOLD_REAL: float = 0.55
    FAS_THRESHOLD_SPOOF: float = 0.40

    AUDIO_SAMPLE_RATE: int = 16000
    AUDIO_CLIP_SAMPLES: int = 64600
    AUDIO_MIN_RMS_DB: float = -40.0
    AUDIO_SPOOF_THRESHOLD: float = 0.55

    CHALLENGE_PHRASE_POOL: list[str] = [
        "silver mountain",
        "quiet river",
        "hidden forest",
        "bright sunrise",
        "golden shadow",
        "crystal echo",
        "silent thunder",
        "midnight breeze",
        "rapid whisper",
        "gentle storm",
        "frozen flame",
        "broken compass",
        "rising ember",
        "shallow ocean",
        "dark horizon",
        "soft lightning",
    ]
    CHALLENGE_DIGIT_CODES: list[str] = [
        "4829",
        "7391",
        "6058",
        "9143",
        "2570",
        "8642",
        "3907",
        "5718",
        "6284",
        "1496",
        "7035",
        "2861",
        "9572",
        "4108",
        "8327",
        "6951",
    ]
    CHALLENGE_PHRASE_PROMPT_TEMPLATES: list[str] = [
        'Say only this phrase: "{value}".',
        'Repeat exactly: "{value}".',
        'Speak this phrase clearly: "{value}".',
    ]
    CHALLENGE_DIGIT_PROMPT_TEMPLATES: list[str] = [
        "Read these digits: {value}.",
        "Repeat this code: {value}.",
        "Speak only these digits: {value}.",
    ]
    CHALLENGE_TIMEOUT_SEC: float = 45.0
    CHALLENGE_REQUIRED_ACTIONS: int = 2
    CHALLENGE_PHRASE_SIMILARITY: float = 0.65
    CHALLENGE_TOKEN_SIMILARITY: float = 0.75
    CHALLENGE_PASS_THRESHOLD: float = 70.0

    SCORE_PASS_THRESHOLD: float = 75.0
    SCORE_FAIL_THRESHOLD: float = 45.0
    LOW_COMPONENT_SCORE_THRESHOLD: float = 45.0
    NEUTRAL_COMPONENT_SCORE: float = 55.0
    MIN_PASS_EVIDENCE_COVERAGE: float = 0.60
    MAX_REASON_PENALTY: float = 40.0

    WEIGHT_FACE: float = 0.30
    WEIGHT_AUDIO: float = 0.25
    WEIGHT_CHALLENGE: float = 0.25
    WEIGHT_TAMPER: float = 0.10
    WEIGHT_IDENTITY: float = 0.10

    TAMPER_DUPLICATE_THRESHOLD: float = 0.98
    TAMPER_MOTION_STAGNATION_RATIO: float = 0.80
    TAMPER_MAX_FREEZE_FRAMES: int = 5

    IDENTITY_COSINE_THRESHOLD: float = 0.40
    IDENTITY_MIN_CONSISTENT_RATIO: float = 0.70

    LIVENESS_BLINK_EAR_THRESHOLD: float = 0.22
    LIVENESS_REQUIRED_BLINKS: int = 2
    LIVENESS_HEAD_TURN_DEG: float = 15.0

    INITIAL_TRUST_SCORE: float = 50.0
    TRUST_SCORE_SMOOTHING: float = 0.6
    TRUST_SCORE_FAIL_FLOOR: float = 25.0
    READY_REQUIRE_ALL_MODELS: bool = True

    STT_BACKEND: Literal["whisper", "disabled"] = "whisper"
    STT_COMPUTE_TYPE: str = "int8"
    STT_BEAM_SIZE: int = 5

    @field_validator("DEBUG", "MODEL_WARMUP", "READY_REQUIRE_ALL_MODELS", mode="before")
    @classmethod
    def _parse_bool(cls, value: Any) -> Any:
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on", "debug", "development", "dev"}:
                return True
            if normalized in {"0", "false", "no", "off", "release", "production", "prod"}:
                return False
        return value

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def _parse_origins(cls, value: Any) -> Any:
        if isinstance(value, str):
            value = value.strip()
            if not value.startswith("["):
                return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator(
        "SESSION_STORE_BACKEND",
        "DEVICE",
        "STT_BACKEND",
        "MODELS_DIR",
        "INSIGHTFACE_MODEL_DIR",
        "FACE_SPOOF_MODEL_PATH",
        "AUDIO_SPOOF_MODEL_DIR",
        "STT_MODEL_DIR",
        mode="before",
    )
    @classmethod
    def _strip_comments(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.split("#", 1)[0].strip()
        return value

    @field_validator("FACE_SPOOF_MEAN", "FACE_SPOOF_STD", mode="before")
    @classmethod
    def _parse_float_list(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [float(item.strip()) for item in value.split(",") if item.strip()]
        return value

    @model_validator(mode="after")
    def _resolve_model_paths(self) -> "Settings":
        self.MODELS_DIR = _make_absolute(self.MODELS_DIR)
        self.INSIGHTFACE_MODEL_DIR = _make_absolute(
            self.INSIGHTFACE_MODEL_DIR or (self.MODELS_DIR / "buffalo_l")
        )
        self.FACE_SPOOF_MODEL_PATH = _make_absolute(
            self.FACE_SPOOF_MODEL_PATH or (self.MODELS_DIR / "anti-spoof-mn3.onnx")
        )
        self.AUDIO_SPOOF_MODEL_DIR = _make_absolute(
            self.AUDIO_SPOOF_MODEL_DIR or (self.MODELS_DIR / "mms-300m-anti-deepfake")
        )
        self.STT_MODEL_DIR = _make_absolute(
            self.STT_MODEL_DIR or (self.MODELS_DIR / "faster-whisper-large-v3-turbo")
        )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _load_env_files()
    _apply_legacy_env_aliases()
    return Settings()

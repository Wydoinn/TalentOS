from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

_TEST_ENV = {
    "SESSION_STORE_BACKEND": "memory",
    "MODEL_WARMUP": "false",
    "JWT_SECRET_KEY": "test-secret-key-for-testing-only-32chars",
    "MIN_VIDEO_DURATION_SEC": "1.0",
    "STT_BACKEND": "disabled",
}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def configure_test_environment(monkeypatch):
    from app.config import get_settings

    for key, value in _TEST_ENV.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def mock_models_loaded():
    status = {
        "face_detector": True,
        "face_spoof": True,
        "face_embedding": True,
        "audio_spoof": True,
    }

    from app.models import base as model_base

    with (
        patch.object(model_base.registry, "load_all", return_value=status),
        patch.object(model_base.registry, "status", return_value=status),
        patch.object(model_base.registry, "all_required_ready", return_value=True),
        patch.object(model_base.registry, "missing_required", return_value=[]),
    ):
        yield


@pytest.fixture
async def client(mock_models_loaded):
    from app.main import create_app
    from app.session.store import reset_session_store

    reset_session_store()
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as api_client:
        yield api_client
    reset_session_store()


@pytest.fixture
def dummy_mp4() -> bytes:
    return b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x01isomiso2mp41" + b"\x00" * 1024


@pytest.fixture
def pass_result():
    from app.api.schemas import AnalysisResult, OverallStatus, RiskLevel

    return AnalysisResult(
        overall_status=OverallStatus.PASS,
        overall_score=82.0,
        face_score=85.0,
        audio_score=80.0,
        challenge_score=88.0,
        tamper_score=90.0,
        identity_consistency_score=84.0,
        reasons=[],
        human_readable_summary="Passed verification.",
        risk_level=RiskLevel.LOW,
        top_issues=[],
        confidence="84%",
        frame_count=12,
        faces_detected=1,
        audio_duration_sec=5.2,
        challenge_verified=True,
        processing_time_ms=450.0,
    )


@pytest.fixture
def flag_result():
    from app.api.schemas import AnalysisResult, OverallStatus, RiskLevel

    return AnalysisResult(
        overall_status=OverallStatus.FLAG,
        overall_score=62.0,
        face_score=68.0,
        audio_score=59.0,
        challenge_score=55.0,
        tamper_score=84.0,
        identity_consistency_score=70.0,
        reasons=["KEYWORD_MISMATCH"],
        human_readable_summary="Flagged for review.",
        risk_level=RiskLevel.MEDIUM,
        top_issues=["KEYWORD_MISMATCH"],
        confidence="67%",
        frame_count=12,
        faces_detected=1,
        audio_duration_sec=5.2,
        challenge_verified=False,
        processing_time_ms=450.0,
    )

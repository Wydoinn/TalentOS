from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest


def _frame(value: int = 128) -> np.ndarray:
    return np.full((100, 100, 3), value, dtype=np.uint8)


def test_duplicate_frames_are_detected():
    from app.pipeline.tamper_detector import TamperDetector

    result = TamperDetector().analyze([_frame()] * 10, np.zeros(96000, np.float32), {})

    assert result.duplicate_frames_detected is True
    assert "DUPLICATE_FRAMES" in result.flags


def test_varied_frames_are_not_marked_as_duplicates():
    from app.pipeline.tamper_detector import TamperDetector

    rng = np.random.default_rng(42)
    frames = [rng.integers(0, 255, (100, 100, 3), dtype=np.uint8) for _ in range(10)]
    audio = (np.random.default_rng(0).standard_normal(96000) * 0.1).astype(np.float32)

    result = TamperDetector().analyze(frames, audio, {})

    assert result.duplicate_frames_detected is False


def test_silence_is_detected():
    from app.pipeline.tamper_detector import TamperDetector

    result = TamperDetector().analyze([_frame()] * 5, np.zeros(96000, np.float32), {})

    assert result.audio_silence is True


def test_active_audio_is_not_marked_as_silence():
    from app.pipeline.tamper_detector import TamperDetector

    audio = (np.random.default_rng(1).standard_normal(96000) * 0.3).astype(np.float32)
    result = TamperDetector().analyze([_frame()] * 5, audio, {})

    assert result.audio_silence is False


def test_frame_freeze_is_detected_from_preprocessor_hint():
    from app.pipeline.tamper_detector import TamperDetector

    audio = (np.random.default_rng(2).standard_normal(96000) * 0.1).astype(np.float32)
    result = TamperDetector().analyze([_frame()] * 5, audio, {"frozen_frames": 10})

    assert result.frame_freeze is True


def test_tamper_score_drops_when_multiple_signals_are_present():
    from app.pipeline.tamper_detector import TamperDetector

    result = TamperDetector().analyze(
        [_frame()] * 10,
        np.zeros(96000, np.float32),
        {"frozen_frames": 10, "motion_stagnation_ratio": 0.95},
    )

    assert result.score < 50.0


@pytest.mark.anyio
async def test_memory_store_save_and_get():
    from app.session.store import MemorySessionStore, SessionData, SessionStatus

    store = MemorySessionStore()
    session = SessionData(
        "session-1",
        "candidate-1",
        None,
        {},
        SessionStatus.CREATED,
        datetime.now(timezone.utc),
        datetime.now(timezone.utc) + timedelta(hours=1),
    )

    await store.save(session)
    stored = await store.get("session-1")

    assert stored is not None
    assert stored.candidate_id == "candidate-1"


@pytest.mark.anyio
async def test_memory_store_drops_expired_session():
    from app.session.store import MemorySessionStore, SessionData, SessionStatus

    store = MemorySessionStore()
    session = SessionData(
        "session-2",
        "candidate-2",
        None,
        {},
        SessionStatus.CREATED,
        datetime.now(timezone.utc) - timedelta(hours=2),
        datetime.now(timezone.utc) - timedelta(hours=1),
    )

    await store.save(session)

    assert await store.get("session-2") is None


@pytest.mark.anyio
async def test_memory_store_delete_removes_session():
    from app.session.store import MemorySessionStore, SessionData, SessionStatus

    store = MemorySessionStore()
    session = SessionData(
        "session-3",
        "candidate-3",
        None,
        {},
        SessionStatus.CREATED,
        datetime.now(timezone.utc),
        datetime.now(timezone.utc) + timedelta(hours=1),
    )

    await store.save(session)
    await store.delete("session-3")

    assert await store.get("session-3") is None


@pytest.mark.anyio
async def test_memory_store_ping_returns_true():
    from app.session.store import MemorySessionStore

    assert await MemorySessionStore().ping() is True

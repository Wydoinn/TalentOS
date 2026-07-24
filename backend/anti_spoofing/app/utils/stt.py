"""Speech-to-text helpers for challenge verification."""
from __future__ import annotations

import asyncio

import numpy as np

from app.config import get_settings
from app.models.weights import require_local_path
from app.utils.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

_WHISPER_SAMPLE_RATE = 16000
_whisper_model = None


def _device_name() -> str:
    return "cuda" if settings.DEVICE.lower().startswith("cuda") else "cpu"


def _get_whisper():
    global _whisper_model
    if _whisper_model is not None:
        return _whisper_model

    if settings.STT_BACKEND != "whisper":
        return None

    try:
        from faster_whisper import WhisperModel

        source = require_local_path(settings.STT_MODEL_DIR, label="STT model directory")
        logger.info(
            "Loading faster-whisper from '%s' (device=%s, compute_type=%s)",
            source,
            _device_name(),
            settings.STT_COMPUTE_TYPE,
        )
        _whisper_model = WhisperModel(
            str(source),
            device=_device_name(),
            compute_type=settings.STT_COMPUTE_TYPE,
        )
        logger.info("faster-whisper ready")
        return _whisper_model
    except Exception as exc:
        logger.error(
            "faster-whisper failed to load local model: %s. "
            "Challenge keyword verification will be softened until the local STT model is available.",
            exc,
        )
        return None


async def transcribe_audio(waveform: np.ndarray, sample_rate: int) -> str | None:
    """Transcribe audio in a worker thread."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _transcribe_sync, waveform, sample_rate)


def _transcribe_sync(waveform: np.ndarray, sample_rate: int) -> str | None:
    model = _get_whisper()
    if model is None:
        return None

    audio = waveform.astype(np.float32)
    if sample_rate != _WHISPER_SAMPLE_RATE:
        try:
            import librosa

            audio = librosa.resample(
                audio,
                orig_sr=sample_rate,
                target_sr=_WHISPER_SAMPLE_RATE,
            )
        except Exception as exc:
            logger.warning("STT resample failed: %s", exc)
            return None

    peak = np.abs(audio).max()
    if peak <= 1e-6:
        logger.debug("STT audio is too quiet to transcribe")
        return None
    audio = audio / peak

    try:
        segments, _ = model.transcribe(
            audio,
            language="en",
            condition_on_previous_text=False,
            temperature=0.0,
            beam_size=settings.STT_BEAM_SIZE,
            vad_filter=True,
        )
        text = " ".join(segment.text.strip() for segment in segments if segment.text).strip()
        if text:
            logger.debug("STT transcript: '%s'", text)
            return text
        return None
    except Exception as exc:
        logger.warning("STT transcription error: %s", exc)
        return None

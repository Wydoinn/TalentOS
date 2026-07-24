from __future__ import annotations

import asyncio
import io
import logging
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from app.core.config import Settings
from app.core.exceptions import ApiError

logger = logging.getLogger(__name__)

_TARGET_SAMPLE_RATE = 16000


class SpeechTranscriptionService:
    _model: Any = None
    _loaded_model_path: str | None = None

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def transcribe_audio_bytes(self, audio_bytes: bytes) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._transcribe_sync, audio_bytes)

    def _transcribe_sync(self, audio_bytes: bytes) -> dict[str, Any]:
        waveform, sample_rate = self._decode_audio(audio_bytes)
        if waveform.size == 0:
            raise ApiError(
                status_code=422,
                code="empty_audio",
                message="The recorded answer was empty. Please record your response again.",
            )

        waveform = self._normalize_waveform(waveform, sample_rate)
        duration_seconds = round(float(waveform.shape[0]) / _TARGET_SAMPLE_RATE, 2)

        model = self._get_model()
        try:
            segments, _ = model.transcribe(
                waveform,
                language=self.settings.stt_language,
                condition_on_previous_text=False,
                temperature=0.0,
                beam_size=self.settings.stt_beam_size,
                vad_filter=True,
            )
        except Exception as exc:  # pragma: no cover - model/runtime errors are environment specific.
            logger.exception("Speech transcription failed")
            raise ApiError(
                status_code=503,
                code="transcription_unavailable",
                message=f"Unable to transcribe the spoken answer right now: {exc}",
            ) from exc

        transcript = " ".join(segment.text.strip() for segment in segments if getattr(segment, "text", "")).strip()
        if not transcript:
            raise ApiError(
                status_code=422,
                code="transcription_empty",
                message="No clear speech was detected. Please speak clearly and try again.",
            )

        return {
            "transcript": transcript,
            "model": f"faster-whisper:{Path(self.settings.stt_model_dir).name}",
            "duration_seconds": duration_seconds,
        }

    def _decode_audio(self, audio_bytes: bytes) -> tuple[np.ndarray, int]:
        try:
            waveform, sample_rate = sf.read(io.BytesIO(audio_bytes), dtype="float32", always_2d=False)
        except Exception as exc:
            raise ApiError(
                status_code=422,
                code="invalid_audio",
                message=f"The recorded answer could not be decoded as audio: {exc}",
            ) from exc

        if isinstance(waveform, np.ndarray) and waveform.ndim > 1:
            waveform = np.mean(waveform, axis=1)

        return np.asarray(waveform, dtype=np.float32), int(sample_rate)

    def _normalize_waveform(self, waveform: np.ndarray, sample_rate: int) -> np.ndarray:
        audio = waveform.astype(np.float32)

        if sample_rate != _TARGET_SAMPLE_RATE:
            try:
                import librosa

                audio = librosa.resample(audio, orig_sr=sample_rate, target_sr=_TARGET_SAMPLE_RATE)
            except Exception as exc:
                raise ApiError(
                    status_code=422,
                    code="audio_resample_failed",
                    message=f"The recorded answer could not be prepared for transcription: {exc}",
                ) from exc

        peak = float(np.abs(audio).max()) if audio.size else 0.0
        if peak <= 1e-6:
            raise ApiError(
                status_code=422,
                code="audio_too_quiet",
                message="The spoken answer was too quiet. Please retry in a quieter place and speak louder.",
            )

        return audio / peak

    def _get_model(self):
        model_path = str(Path(self.settings.stt_model_dir).resolve())
        if self.__class__._model is not None and self.__class__._loaded_model_path == model_path:
            return self.__class__._model

        model_dir = Path(model_path)
        if not model_dir.exists():
            raise ApiError(
                status_code=503,
                code="transcription_model_missing",
                message=f"Whisper model directory was not found: {model_dir}",
            )

        if self.settings.stt_backend != "whisper":
            raise ApiError(
                status_code=503,
                code="transcription_disabled",
                message="Spoken answer transcription is disabled for this environment.",
            )

        try:
            from faster_whisper import WhisperModel
        except Exception as exc:  # pragma: no cover - import depends on runtime environment.
            raise ApiError(
                status_code=503,
                code="transcription_dependency_missing",
                message=f"faster-whisper is not available: {exc}",
            ) from exc

        logger.info(
            "Loading orchestration faster-whisper from '%s' (device=%s, compute_type=%s)",
            model_dir,
            self.settings.stt_device,
            self.settings.stt_compute_type,
        )
        self.__class__._model = WhisperModel(
            str(model_dir),
            device=self.settings.stt_device,
            compute_type=self.settings.stt_compute_type,
        )
        self.__class__._loaded_model_path = model_path
        logger.info("Orchestration faster-whisper ready")
        return self.__class__._model

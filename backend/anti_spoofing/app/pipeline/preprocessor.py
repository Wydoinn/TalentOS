"""
Media preprocessing for uploaded video clips.

The preprocessor validates the payload, extracts sampled frames with OpenCV,
and extracts audio with ffmpeg when it is available.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter

import cv2
import numpy as np

from app.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

_ALLOWED_EXTENSIONS = {".mp4", ".webm", ".mov", ".avi", ".mkv"}

_MAGIC = {
    b"\x00\x00\x00\x18ftyp": "video/mp4",
    b"\x00\x00\x00\x20ftyp": "video/mp4",
    b"\x00\x00\x00\x14ftyp": "video/quicktime",
    b"\x1aE\xdf\xa3": "video/webm",
}


@dataclass
class MediaInfo:
    width: int
    height: int
    fps: float
    total_frames: int
    duration_sec: float


@dataclass
class PreprocessedMedia:
    frames: list[np.ndarray]
    audio_waveform: np.ndarray | None
    audio_sample_rate: int
    media_info: MediaInfo
    tamper_hints: dict = field(default_factory=dict)


class MediaPreprocessor:
    def __init__(self) -> None:
        self._max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024

    def process(self, data: bytes, filename: str) -> PreprocessedMedia:
        self._validate(data, filename)

        started_at = perf_counter()
        with tempfile.NamedTemporaryFile(suffix=Path(filename).suffix, delete=False) as temp_file:
            temp_file.write(data)
            temp_path = temp_file.name

        try:
            frames, info, tamper_hints = self._extract_frames(temp_path)
            audio, sample_rate = self._extract_audio(temp_path)
        finally:
            with suppress(OSError):
                os.unlink(temp_path)

        logger.debug(
            "Media processed in %.0f ms | frames=%s audio_samples=%s",
            (perf_counter() - started_at) * 1000,
            len(frames),
            len(audio) if audio is not None else 0,
        )
        return PreprocessedMedia(
            frames=frames,
            audio_waveform=audio,
            audio_sample_rate=sample_rate,
            media_info=info,
            tamper_hints=tamper_hints,
        )

    def _validate(self, data: bytes, filename: str) -> None:
        if len(data) > self._max_bytes:
            raise ValueError(
                f"File too large: {len(data) // 1024 // 1024} MB "
                f"(max {settings.MAX_FILE_SIZE_MB} MB)"
            )

        extension = Path(filename).suffix.lower()
        if extension not in _ALLOWED_EXTENSIONS:
            raise ValueError(f"Unsupported file extension: {extension!r}")

        self._check_magic(data)

    def _check_magic(self, data: bytes) -> None:
        header = data[:12]
        for magic in _MAGIC:
            if header[:len(magic)] == magic:
                return
        logger.debug("Magic-byte check was inconclusive; proceeding to codec validation.")

    def _extract_frames(self, path: str) -> tuple[list[np.ndarray], MediaInfo, dict]:
        capture = cv2.VideoCapture(path)
        if not capture.isOpened():
            raise ValueError("Cannot open video file; codec may be unsupported")

        fps = self._normalize_fps(capture.get(cv2.CAP_PROP_FPS))
        metadata_total_frames = self._normalize_frame_count(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        width = max(int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)), 0)
        height = max(int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)), 0)

        sample_indices = (
            self._build_sample_indices(metadata_total_frames, fps)
            if metadata_total_frames is not None
            else []
        )
        sample_step = self._sample_step(fps)
        frames: list[np.ndarray] = []
        sampled_positions: list[int] = []
        motion_values: list[float] = []
        frozen_count = 0
        frame_index = 0
        previous_gray = None
        sample_position = 0
        next_sample_index = sample_indices[sample_position] if sample_indices else None
        last_frame: np.ndarray | None = None
        last_timestamp_ms = 0.0

        def append_sampled_frame(current_frame: np.ndarray, current_index: int) -> None:
            nonlocal previous_gray, frozen_count, width, height
            frames.append(current_frame.copy())
            sampled_positions.append(current_index)
            if width <= 0 or height <= 0:
                height, width = current_frame.shape[:2]
            gray = cv2.cvtColor(current_frame, cv2.COLOR_BGR2GRAY)
            if previous_gray is not None:
                motion = float(cv2.absdiff(gray, previous_gray).mean())
                motion_values.append(motion)
                if motion < 0.5:
                    frozen_count += 1
            previous_gray = gray

        while True:
            ok, frame = capture.read()
            if not ok:
                break

            last_frame = frame
            position_ms = capture.get(cv2.CAP_PROP_POS_MSEC)
            if np.isfinite(position_ms) and position_ms > 0:
                last_timestamp_ms = max(last_timestamp_ms, float(position_ms))

            should_sample = False
            if metadata_total_frames is not None:
                should_sample = next_sample_index is not None and frame_index == next_sample_index
            else:
                should_sample = frame_index % sample_step == 0

            if should_sample:
                append_sampled_frame(frame, frame_index)
                if metadata_total_frames is not None:
                    sample_position += 1
                    next_sample_index = (
                        sample_indices[sample_position]
                        if sample_position < len(sample_indices)
                        else None
                    )
                    if next_sample_index is None:
                        frame_index += 1
                        break

            frame_index += 1

        capture.release()

        actual_total_frames = metadata_total_frames if metadata_total_frames is not None else frame_index
        if (
            last_frame is not None
            and frame_index > 0
            and (not sampled_positions or sampled_positions[-1] != frame_index - 1)
        ):
            append_sampled_frame(last_frame, frame_index - 1)

        if len(frames) > settings.MAX_FRAMES:
            reduced_positions = np.linspace(
                0,
                len(frames) - 1,
                num=settings.MAX_FRAMES,
                dtype=int,
            )
            frames = [frames[position] for position in reduced_positions.tolist()]
            motion_values = self._sample_motion_values(frames)
            frozen_count = sum(1 for motion in motion_values if motion < 0.5)

        duration = self._estimate_duration(
            fps=fps,
            metadata_total_frames=metadata_total_frames,
            actual_total_frames=actual_total_frames,
            last_timestamp_ms=last_timestamp_ms,
        )

        if duration < settings.MIN_VIDEO_DURATION_SEC:
            raise ValueError(
                f"Video too short: {duration:.1f}s "
                f"(minimum {settings.MIN_VIDEO_DURATION_SEC}s)"
            )
        if duration > settings.MAX_VIDEO_DURATION_SEC:
            raise ValueError(
                f"Video too long: {duration:.1f}s "
                f"(maximum {settings.MAX_VIDEO_DURATION_SEC}s)"
            )

        if len(frames) < 2:
            raise ValueError("Insufficient frames extracted from video")

        tamper_hints: dict = {}
        if motion_values:
            tamper_hints["mean_motion"] = float(np.mean(motion_values))
            tamper_hints["frozen_frames"] = frozen_count
            tamper_hints["motion_stagnation_ratio"] = (
                sum(1 for motion in motion_values if motion < 0.5) / len(motion_values)
            )

        return frames, MediaInfo(width, height, fps, actual_total_frames, duration), tamper_hints

    def _build_sample_indices(self, total_frames: int, fps: float) -> list[int]:
        target_frames = min(total_frames, settings.MAX_FRAMES)
        if target_frames <= 0:
            return []

        sample_step = self._sample_step(fps)

        sampled_indices = list(range(0, total_frames, sample_step))
        if not sampled_indices or sampled_indices[-1] != total_frames - 1:
            sampled_indices.append(total_frames - 1)

        if len(sampled_indices) <= target_frames:
            return sampled_indices

        reduced_positions = np.linspace(
            0,
            len(sampled_indices) - 1,
            num=target_frames,
            dtype=int,
        )
        return [sampled_indices[position] for position in reduced_positions.tolist()]

    def _sample_step(self, fps: float) -> int:
        if fps > 0 and settings.FRAME_SAMPLE_RATE > 0:
            return max(int(round(fps / settings.FRAME_SAMPLE_RATE)), 1)
        return 1

    def _normalize_fps(self, raw_fps: float) -> float:
        if not np.isfinite(raw_fps) or raw_fps <= 0.0 or raw_fps > 240.0:
            return 25.0
        return float(raw_fps)

    def _normalize_frame_count(self, raw_count: float) -> int | None:
        if not np.isfinite(raw_count):
            return None
        normalized = int(raw_count)
        if normalized <= 0 or normalized > 100000:
            return None
        return normalized

    def _estimate_duration(
        self,
        *,
        fps: float,
        metadata_total_frames: int | None,
        actual_total_frames: int,
        last_timestamp_ms: float,
    ) -> float:
        if (
            metadata_total_frames is not None
            and fps > 0
            and np.isfinite(metadata_total_frames / fps)
        ):
            duration = metadata_total_frames / fps
            if duration > 0:
                return float(duration)

        if np.isfinite(last_timestamp_ms) and last_timestamp_ms > 0:
            return float(last_timestamp_ms / 1000.0)

        if fps > 0 and actual_total_frames > 0:
            return float(actual_total_frames / fps)

        return 0.0

    def _sample_motion_values(self, frames: list[np.ndarray]) -> list[float]:
        motion_values: list[float] = []
        if len(frames) < 2:
            return motion_values

        previous_gray = cv2.cvtColor(frames[0], cv2.COLOR_BGR2GRAY)
        for frame in frames[1:]:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            motion_values.append(float(cv2.absdiff(gray, previous_gray).mean()))
            previous_gray = gray
        return motion_values

    def _extract_audio(self, path: str) -> tuple[np.ndarray | None, int]:
        target_sample_rate = settings.AUDIO_SAMPLE_RATE

        try:
            import shutil

            ffmpeg = shutil.which("ffmpeg")
            if ffmpeg:
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as wav_file:
                    wav_path = wav_file.name
                try:
                    result = subprocess.run(
                        [
                            ffmpeg,
                            "-loglevel",
                            "error",
                            "-y",
                            "-i",
                            path,
                            "-ac",
                            "1",
                            "-ar",
                            str(target_sample_rate),
                            "-f",
                            "wav",
                            wav_path,
                        ],
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    if result.returncode == 0:
                        import soundfile as sf

                        audio, sample_rate = sf.read(wav_path, dtype="float32")
                        return audio, sample_rate

                    logger.debug("ffmpeg returned %s: %s", result.returncode, result.stderr[:200])
                finally:
                    with suppress(OSError):
                        os.unlink(wav_path)
        except Exception as exc:
            logger.debug("ffmpeg audio extraction failed: %s", exc)

        logger.warning(
            "Audio extraction failed because ffmpeg is unavailable or decoding failed. "
            "The pipeline will continue without audio."
        )
        return None, target_sample_rate

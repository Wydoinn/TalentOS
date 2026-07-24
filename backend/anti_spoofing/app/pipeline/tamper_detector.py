"""Tamper and replay checks for uploaded media."""
from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from app.config import get_settings

settings = get_settings()


@dataclass
class TamperResult:
    score: float
    duplicate_frames_detected: bool
    duplicate_ratio: float
    mean_frame_delta: float
    motion_stagnation: bool
    audio_silence: bool
    frame_freeze: bool
    metadata_anomaly: bool
    flags: list[str] = field(default_factory=list)


class TamperDetector:
    def analyze(
        self,
        frames: list[np.ndarray],
        audio: np.ndarray | None,
        tamper_hints: dict,
    ) -> TamperResult:
        flags: list[str] = []
        penalties = 0.0

        duplicate_frames, duplicate_ratio, mean_frame_delta = self._duplicate_frames(
            frames,
            tamper_hints,
        )
        if duplicate_frames:
            flags.append("DUPLICATE_FRAMES")
            penalties += 12.0

        motion_stagnation = self._motion_stagnation(frames, tamper_hints)
        if motion_stagnation:
            flags.append("LOW_MOTION")
            penalties += 25.0

        frame_freeze = tamper_hints.get("frozen_frames", 0) > settings.TAMPER_MAX_FREEZE_FRAMES
        if frame_freeze:
            flags.append("FRAME_FREEZE")
            penalties += 20.0

        audio_silence = self._is_silence(audio)
        if audio_silence:
            flags.append("AUDIO_SILENCE")
            penalties += 15.0

        # Resolution inconsistencies can indicate stitched or tampered media.
        metadata_anomaly = (
            len({(frame.shape[0], frame.shape[1]) for frame in frames}) > 2
            if len(frames) >= 2
            else False
        )
        if metadata_anomaly:
            flags.append("METADATA_ANOMALY")
            penalties += 5.0

        return TamperResult(
            score=round(max(0.0, 100.0 - penalties), 1),
            duplicate_frames_detected=duplicate_frames,
            duplicate_ratio=round(duplicate_ratio, 4),
            mean_frame_delta=round(mean_frame_delta, 4),
            motion_stagnation=motion_stagnation,
            audio_silence=audio_silence,
            frame_freeze=frame_freeze,
            metadata_anomaly=metadata_anomaly,
            flags=flags,
        )

    def _duplicate_frames(self, frames: list[np.ndarray], hints: dict) -> tuple[bool, float, float]:
        if len(frames) < 3:
            return False, 0.0, 0.0

        duplicate_count = 0
        frame_deltas: list[float] = []
        for index in range(1, len(frames)):
            previous_frame = cv2.resize(frames[index - 1], (64, 64))
            current_frame = cv2.resize(frames[index], (64, 64))

            previous_histogram = cv2.calcHist(
                [previous_frame],
                [0, 1, 2],
                None,
                [8, 8, 8],
                [0, 256] * 3,
            )
            current_histogram = cv2.calcHist(
                [current_frame],
                [0, 1, 2],
                None,
                [8, 8, 8],
                [0, 256] * 3,
            )
            cv2.normalize(previous_histogram, previous_histogram)
            cv2.normalize(current_histogram, current_histogram)

            previous_gray = cv2.cvtColor(previous_frame, cv2.COLOR_BGR2GRAY)
            current_gray = cv2.cvtColor(current_frame, cv2.COLOR_BGR2GRAY)
            frame_delta = float(cv2.absdiff(previous_gray, current_gray).mean())
            frame_deltas.append(frame_delta)

            if (
                cv2.compareHist(
                    previous_histogram,
                    current_histogram,
                    cv2.HISTCMP_CORREL,
                )
                > settings.TAMPER_DUPLICATE_THRESHOLD
                and frame_delta < 1.25
            ):
                duplicate_count += 1

        duplicate_ratio = duplicate_count / (len(frames) - 1)
        mean_frame_delta = float(np.mean(frame_deltas)) if frame_deltas else 0.0
        if hints.get("motion_stagnation_ratio", 0.0) < 0.35 and mean_frame_delta > 1.25:
            return False, duplicate_ratio, mean_frame_delta

        detected = (
            duplicate_ratio > settings.TAMPER_MOTION_STAGNATION_RATIO
            and mean_frame_delta < 1.25
        )
        return detected, duplicate_ratio, mean_frame_delta

    def _motion_stagnation(self, frames: list[np.ndarray], hints: dict) -> bool:
        # Use the precomputed hint when available.
        if "motion_stagnation_ratio" in hints:
            return hints["motion_stagnation_ratio"] > settings.TAMPER_MOTION_STAGNATION_RATIO
        if len(frames) < 3:
            return False

        motions = []
        for index in range(1, len(frames)):
            previous_gray = cv2.cvtColor(
                cv2.resize(frames[index - 1], (64, 64)),
                cv2.COLOR_BGR2GRAY,
            )
            current_gray = cv2.cvtColor(
                cv2.resize(frames[index], (64, 64)),
                cv2.COLOR_BGR2GRAY,
            )
            motions.append(float(cv2.absdiff(previous_gray, current_gray).mean()))
        return (
            sum(1 for motion in motions if motion < 1.0) / len(motions)
            > settings.TAMPER_MOTION_STAGNATION_RATIO
        )

    def _is_silence(self, audio: np.ndarray | None) -> bool:
        if audio is None or len(audio) == 0:
            return True

        audio_f32 = audio.astype(np.float32)
        rms_db = 20 * float(np.log10(float(np.sqrt(np.mean(audio_f32 ** 2))) + 1e-10))
        peak_db = 20 * float(np.log10(float(np.max(np.abs(audio_f32))) + 1e-10))
        return bool(
            rms_db < settings.AUDIO_MIN_RMS_DB
            and peak_db < settings.AUDIO_MIN_RMS_DB + 12.0
        )

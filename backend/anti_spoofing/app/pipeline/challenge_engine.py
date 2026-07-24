"""Challenge generation, liveness analysis, and verification utilities."""
from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher

import numpy as np

from app.config import get_settings

settings = get_settings()
_RANDOM = random.SystemRandom()
_CHALLENGE_TYPES = ("phrase", "digit_code")


@dataclass
class Challenge:
    challenge_id: str
    challenge_type: str
    prompt: str
    expected_keyword: str
    required_actions: list[str]
    created_at: datetime
    expires_at: datetime

    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) > self.expires_at

    def to_dict(self) -> dict:
        return {
            "challenge_id": self.challenge_id,
            "challenge_type": self.challenge_type,
            "prompt": self.prompt,
            "expected_keyword": self.expected_keyword,
            "required_actions": self.required_actions,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Challenge":
        return cls(
            challenge_id=data["challenge_id"],
            challenge_type=data["challenge_type"],
            prompt=data["prompt"],
            expected_keyword=data["expected_keyword"],
            required_actions=data["required_actions"],
            created_at=datetime.fromisoformat(data["created_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"]),
        )


@dataclass
class ChallengeVerificationResult:
    score: float
    speech_detected: bool
    keyword_matched: bool
    blink_detected: bool
    head_turn_detected: bool
    left_turn_detected: bool
    right_turn_detected: bool
    action_sequence_valid: bool
    timed_out: bool
    transcript: str | None = None
    reasons: list[str] = field(default_factory=list)


_ACTION_LABELS = {
    "blink_twice": "Blink twice clearly",
    "turn_head_left": "Turn your head to the left",
    "turn_head_right": "Turn your head to the right",
}


class ChallengeEngine:
    def choose_type(
        self,
        requested_type: str | None = None,
        previous_type: str | None = None,
    ) -> str:
        if requested_type in _CHALLENGE_TYPES:
            return requested_type
        if previous_type == "phrase":
            return "digit_code"
        if previous_type == "digit_code":
            return "phrase"
        return _RANDOM.choice(_CHALLENGE_TYPES)

    def generate(
        self,
        challenge_id: str,
        challenge_type: str | None = None,
        previous_type: str | None = None,
    ) -> Challenge:
        now = datetime.now(timezone.utc)
        selected_type = self.choose_type(challenge_type, previous_type)

        if selected_type == "digit_code":
            code = _RANDOM.choice(settings.CHALLENGE_DIGIT_CODES)
            display_value = " ".join(code)
            prompt = _RANDOM.choice(settings.CHALLENGE_DIGIT_PROMPT_TEMPLATES).format(
                value=display_value
            )
            keyword = code
        else:
            phrase = _RANDOM.choice(settings.CHALLENGE_PHRASE_POOL)
            prompt = _RANDOM.choice(settings.CHALLENGE_PHRASE_PROMPT_TEMPLATES).format(
                value=phrase
            )
            keyword = phrase.lower().strip()

        actions = self._build_actions()
        return Challenge(
            challenge_id=challenge_id,
            challenge_type=selected_type,
            prompt=prompt,
            expected_keyword=keyword,
            required_actions=actions,
            created_at=now,
            expires_at=now + timedelta(seconds=settings.CHALLENGE_TIMEOUT_SEC),
        )

    @staticmethod
    def action_label(action: str) -> str:
        return _ACTION_LABELS.get(action, action)

    def build_instructions(self, challenge: Challenge) -> list[str]:
        return [
            challenge.prompt,
            *[f"Then: {self.action_label(action)}" for action in challenge.required_actions],
        ]

    def _build_actions(self) -> list[str]:
        required_count = max(0, min(settings.CHALLENGE_REQUIRED_ACTIONS, 3))
        if required_count == 0:
            return []
        if required_count == 1:
            return [_RANDOM.choice(["blink_twice", "turn_head_left", "turn_head_right"])]

        actions = ["blink_twice", _RANDOM.choice(["turn_head_left", "turn_head_right"])]
        if required_count > len(actions):
            remaining = [
                action for action in ("turn_head_left", "turn_head_right")
                if action not in actions
            ]
            actions.extend(remaining[: required_count - len(actions)])
        return actions


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", text.lower().strip())


def _token_similarity(transcribed: str, expected: str) -> bool:
    transcribed_tokens = _normalize(transcribed).split()
    expected_tokens = _normalize(expected).split()
    if not expected_tokens:
        return False

    matched = sum(
        1
        for expected_token in expected_tokens
        if any(
            SequenceMatcher(None, expected_token, transcribed_token).ratio()
            >= settings.CHALLENGE_TOKEN_SIMILARITY
            for transcribed_token in transcribed_tokens
        )
    )
    return matched / len(expected_tokens) >= 0.8


def match_keyword(transcribed: str, expected: str) -> bool:
    normalized_transcribed = _normalize(transcribed)
    normalized_expected = _normalize(expected)

    if not normalized_expected:
        return False
    if normalized_expected in normalized_transcribed:
        return True
    if _token_similarity(transcribed, expected):
        return True

    return (
        SequenceMatcher(None, normalized_transcribed, normalized_expected).ratio()
        >= settings.CHALLENGE_PHRASE_SIMILARITY
    )


class ChallengeVerifier:
    def verify(
        self,
        challenge: Challenge,
        transcript: str | None,
        liveness: dict,
        audio_waveform: np.ndarray | None,
        evaluated_at: datetime | None = None,
    ) -> ChallengeVerificationResult:
        reference_time = evaluated_at or datetime.now(timezone.utc)
        if reference_time > challenge.expires_at:
            return ChallengeVerificationResult(
                score=0.0,
                speech_detected=False,
                keyword_matched=False,
                blink_detected=False,
                head_turn_detected=False,
                left_turn_detected=False,
                right_turn_detected=False,
                action_sequence_valid=False,
                timed_out=True,
                transcript=transcript,
                reasons=["CHALLENGE_TIMEOUT", "CHALLENGE_EXPIRED"],
            )

        reasons: list[str] = []
        transcript_available = bool(transcript and transcript.strip())
        speech_ok = self._has_speech(audio_waveform) or transcript_available

        if not speech_ok:
            reasons.append("NO_AUDIO")

        keyword_ok = False
        if speech_ok and transcript_available:
            keyword_ok = match_keyword(transcript or "", challenge.expected_keyword)
            if not keyword_ok:
                reasons.append("KEYWORD_MISMATCH")
        elif speech_ok:
            reasons.append("STT_UNAVAILABLE")

        blink_ok = True
        left_turn_ok = True
        right_turn_ok = True
        liveness_parts: list[float] = []

        if "blink_twice" in challenge.required_actions:
            blink_ok = liveness.get("blink_detected", False)
            liveness_parts.append(1.0 if blink_ok else 0.0)
            if not blink_ok:
                reasons.append("BLINK_NOT_DETECTED")

        if "turn_head_left" in challenge.required_actions:
            left_turn_ok = liveness.get("left_turn_detected", False)
            liveness_parts.append(1.0 if left_turn_ok else 0.0)
            if not left_turn_ok:
                reasons.append("HEAD_TURN_NOT_DETECTED")

        if "turn_head_right" in challenge.required_actions:
            right_turn_ok = liveness.get("right_turn_detected", False)
            liveness_parts.append(1.0 if right_turn_ok else 0.0)
            if not right_turn_ok:
                reasons.append("HEAD_TURN_NOT_DETECTED")

        required_head_turns = [
            action
            for action in challenge.required_actions
            if action in {"turn_head_left", "turn_head_right"}
        ]
        if required_head_turns:
            head_turn_ok = all(
                (
                    action == "turn_head_left" and left_turn_ok
                ) or (
                    action == "turn_head_right" and right_turn_ok
                )
                for action in required_head_turns
            )
        else:
            head_turn_ok = left_turn_ok or right_turn_ok

        sequence_ok = self._sequence_valid(challenge.required_actions, liveness)
        if not sequence_ok:
            reasons.append("CHALLENGE_SEQUENCE_INVALID")

        motion_failures = []
        if "blink_twice" in challenge.required_actions and not blink_ok:
            motion_failures.append("blink_twice")
        if "turn_head_left" in challenge.required_actions and not left_turn_ok:
            motion_failures.append("turn_head_left")
        if "turn_head_right" in challenge.required_actions and not right_turn_ok:
            motion_failures.append("turn_head_right")
        if motion_failures:
            reasons.append("MOTION_NONCOMPLIANT")

        speech_score = 1.0 if speech_ok else 0.0
        if transcript_available:
            keyword_score = 1.0 if keyword_ok else 0.0
        elif speech_ok:
            keyword_score = 0.45
        else:
            keyword_score = 0.0
        liveness_score = float(np.mean(liveness_parts)) if liveness_parts else 0.6
        sequence_score = 1.0 if sequence_ok else 0.35

        score = round(
            (
                speech_score * 0.20
                + keyword_score * 0.30
                + liveness_score * 0.35
                + sequence_score * 0.15
            )
            * 100.0,
            1,
        )

        return ChallengeVerificationResult(
            score=score,
            speech_detected=speech_ok,
            keyword_matched=keyword_ok,
            blink_detected=blink_ok,
            head_turn_detected=head_turn_ok,
            left_turn_detected=left_turn_ok,
            right_turn_detected=right_turn_ok,
            action_sequence_valid=sequence_ok,
            timed_out=False,
            transcript=transcript,
            reasons=list(dict.fromkeys(reasons)),
        )

    @staticmethod
    def _has_speech(audio: np.ndarray | None) -> bool:
        if audio is None or len(audio) == 0:
            return False
        audio_float = audio.astype(np.float32)
        rms_db = 20 * np.log10(float(np.sqrt(np.mean(audio_float ** 2))) + 1e-10)
        peak_db = 20 * np.log10(float(np.max(np.abs(audio_float))) + 1e-10)
        return bool(
            rms_db > settings.AUDIO_MIN_RMS_DB
            or peak_db > settings.AUDIO_MIN_RMS_DB + 12.0
        )

    @staticmethod
    def _sequence_valid(required: list[str], liveness: dict) -> bool:
        events = liveness.get("event_sequence", [])
        if not required:
            return True

        checks = {
            "blink_twice": liveness.get("blink_detected", False),
            "turn_head_left": liveness.get("left_turn_detected", False),
            "turn_head_right": liveness.get("right_turn_detected", False),
        }

        if not events:
            return all(checks.get(action, False) for action in required)

        if all(checks.get(action, action in events) for action in required):
            return True

        index = 0
        for event in events:
            if index < len(required) and event == required[index]:
                index += 1
        return index == len(required)


class LivenessAnalyzer:
    _LEFT_EYE = [33, 160, 158, 133, 153, 144]
    _RIGHT_EYE = [362, 385, 387, 263, 373, 380]
    _LEFT_EAR = 234
    _RIGHT_EAR = 454
    _NOSE_TIP = 1

    def analyze(self, frames: list[np.ndarray], face_detector) -> dict:
        signals: dict = {
            "blink_detected": False,
            "head_turn_detected": False,
            "left_turn_detected": False,
            "right_turn_detected": False,
            "blink_count": 0,
            "max_head_yaw_deg": 0.0,
            "event_sequence": [],
        }
        if not frames:
            return signals

        ear_series: list[tuple[int, float]] = []
        yaw_series: list[tuple[int, float]] = []

        for frame_index, frame in enumerate(frames):
            landmarks = face_detector.extract_landmarks_for_liveness(frame)
            if landmarks is None:
                continue

            ear = self._compute_ear(landmarks)
            if ear is not None:
                ear_series.append((frame_index, ear))

            yaw = self._compute_yaw(landmarks)
            if yaw is not None:
                yaw_series.append((frame_index, yaw))

        detected_events: list[tuple[int, str]] = []

        if len(ear_series) >= 3:
            blink_count, blink_ok, blink_frame = self._detect_blinks(ear_series)
            signals["blink_count"] = blink_count
            signals["blink_detected"] = blink_ok
            if blink_ok and blink_frame is not None:
                detected_events.append((blink_frame, "blink_twice"))

        if yaw_series:
            baseline_window = yaw_series[: max(1, len(yaw_series) // 4)]
            baseline = float(np.median([yaw for _, yaw in baseline_window]))
            adjusted = [(frame_index, yaw - baseline) for frame_index, yaw in yaw_series]
            max_yaw = float(max(yaw for _, yaw in adjusted))
            min_yaw = float(min(yaw for _, yaw in adjusted))
            signals["max_head_yaw_deg"] = max(abs(max_yaw), abs(min_yaw))

            left_turn_frame = next(
                (
                    frame_index
                    for frame_index, yaw in adjusted
                    if yaw >= settings.LIVENESS_HEAD_TURN_DEG
                ),
                None,
            )
            right_turn_frame = next(
                (
                    frame_index
                    for frame_index, yaw in adjusted
                    if yaw <= -settings.LIVENESS_HEAD_TURN_DEG
                ),
                None,
            )

            signals["left_turn_detected"] = left_turn_frame is not None
            signals["right_turn_detected"] = right_turn_frame is not None
            signals["head_turn_detected"] = (
                signals["left_turn_detected"] or signals["right_turn_detected"]
            )

            if left_turn_frame is not None:
                detected_events.append((left_turn_frame, "turn_head_left"))
            if right_turn_frame is not None:
                detected_events.append((right_turn_frame, "turn_head_right"))

        signals["event_sequence"] = [
            action
            for _, action in sorted(detected_events, key=lambda item: item[0])
        ]
        return signals

    def _compute_ear(self, landmarks: dict) -> float | None:
        try:
            def point(index: int) -> np.ndarray:
                return np.array([landmarks[index][0], landmarks[index][1]], dtype=np.float32)

            left_eye = [point(index) for index in self._LEFT_EYE]
            right_eye = [point(index) for index in self._RIGHT_EYE]

            def ear(points: list[np.ndarray]) -> float:
                vertical_1 = np.linalg.norm(points[1] - points[5])
                vertical_2 = np.linalg.norm(points[2] - points[4])
                horizontal = np.linalg.norm(points[0] - points[3])
                return float((vertical_1 + vertical_2) / (2.0 * horizontal + 1e-6))

            return (ear(left_eye) + ear(right_eye)) / 2.0
        except (KeyError, IndexError):
            return None

    def _compute_yaw(self, landmarks: dict) -> float | None:
        try:
            nose_x = landmarks[self._NOSE_TIP][0]
            left_ear_x = landmarks[self._LEFT_EAR][0]
            right_ear_x = landmarks[self._RIGHT_EAR][0]
            ear_mid_x = (left_ear_x + right_ear_x) / 2.0
            face_width = abs(right_ear_x - left_ear_x)
            if face_width < 1e-6:
                return None
            offset = (nose_x - ear_mid_x) / face_width
            return float(offset * 90.0)
        except (KeyError, IndexError):
            return None

    def _detect_blinks(
        self,
        ears: list[tuple[int, float]],
    ) -> tuple[int, bool, int | None]:
        threshold = settings.LIVENESS_BLINK_EAR_THRESHOLD
        count = 0
        in_blink = False
        completion_frame: int | None = None

        for frame_index, ear in ears:
            if ear < threshold:
                in_blink = True
            elif in_blink:
                count += 1
                in_blink = False
                if count >= settings.LIVENESS_REQUIRED_BLINKS and completion_frame is None:
                    completion_frame = frame_index

        detected = count >= settings.LIVENESS_REQUIRED_BLINKS
        return count, detected, completion_frame

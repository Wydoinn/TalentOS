"""Anti-spoofing pipeline orchestration."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from time import perf_counter
from typing import Any

import numpy as np

from app.api.schemas import AnalysisResult, NextAction, OverallStatus, ReasonCode, RiskLevel
from app.config import get_settings
from app.models.base import registry
from app.models.face_detector import FaceDetection
from app.pipeline.challenge_engine import Challenge, ChallengeVerifier, LivenessAnalyzer
from app.pipeline.fusion import ComponentScores, ScoreFusion
from app.pipeline.identity_checker import IdentityConsistencyChecker
from app.pipeline.preprocessor import MediaPreprocessor
from app.pipeline.tamper_detector import TamperDetector
from app.session.store import SessionData
from app.utils.logging import get_logger
from app.utils.stt import transcribe_audio

logger = get_logger(__name__)
settings = get_settings()

_TRUST_REASON_IMPACT = {
    "FACE_SPOOF_DETECTED": 8,
    "AUDIO_SPOOF_DETECTED": 8,
    "REPLAY_DETECTED": 9,
    "FACE_SWITCH_DETECTED": 7,
    "IDENTITY_INCONSISTENT": 5,
    "MULTIPLE_FACES": 4,
    "KEYWORD_MISMATCH": 3,
    "MOTION_NONCOMPLIANT": 3,
    "CHALLENGE_SEQUENCE_INVALID": 3,
    "NO_FACE_DETECTED": 3,
    "NO_AUDIO": 2,
    "DUPLICATE_FRAMES": 4,
    "LOW_MOTION": 3,
    "FRAME_FREEZE": 3,
    "TRUST_SCORE_LOW": 4,
}


@dataclass
class ComponentAssessment:
    score: float
    confidence: float
    reasons: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)


class AntiSpoofingPipeline:
    def __init__(self) -> None:
        self._preprocessor = MediaPreprocessor()
        self._tamper = TamperDetector()
        self._liveness = LivenessAnalyzer()
        self._challenge_verifier = ChallengeVerifier()
        self._fusion = ScoreFusion()

    async def analyze(
        self,
        video_bytes: bytes,
        filename: str,
        session: SessionData,
        challenge: Challenge | None,
    ) -> AnalysisResult:
        started_at = perf_counter()
        try:
            return await self._run(video_bytes, filename, session, challenge, started_at)
        except Exception:
            elapsed_ms = self._elapsed_ms(started_at)
            logger.exception("Pipeline error for session %s", session.session_id)
            return self._error_result(ReasonCode.PROCESSING_ERROR, "pipeline_exception", elapsed_ms)

    async def _run(
        self,
        video_bytes: bytes,
        filename: str,
        session: SessionData,
        challenge: Challenge | None,
        started_at: float,
    ) -> AnalysisResult:
        analysis_started_at = datetime.now(timezone.utc)
        face_detector = registry.get("face_detector")
        face_spoof = registry.get("face_spoof")
        face_embedding = registry.get("face_embedding")
        audio_spoof = registry.get("audio_spoof")

        if not face_detector or not face_detector.is_ready():
            return self._fail_result(
                ReasonCode.MODEL_UNAVAILABLE,
                "face_detector not loaded",
                self._elapsed_ms(started_at),
            )
        if not face_spoof or not face_spoof.is_ready():
            return self._fail_result(
                ReasonCode.MODEL_UNAVAILABLE,
                "face_spoof not loaded",
                self._elapsed_ms(started_at),
            )
        if not audio_spoof or not audio_spoof.is_ready():
            return self._fail_result(
                ReasonCode.MODEL_UNAVAILABLE,
                "audio_spoof not loaded",
                self._elapsed_ms(started_at),
            )

        session.challenge_verified = False

        try:
            media = self._preprocessor.process(video_bytes, filename)
        except ValueError as exc:
            return self._fail_result(
                ReasonCode.MEDIA_INVALID,
                str(exc),
                self._elapsed_ms(started_at),
            )

        frames = media.frames
        audio = media.audio_waveform
        audio_sample_rate = media.audio_sample_rate

        face_crops: list[np.ndarray] = []
        frame_detections: list[tuple[np.ndarray, FaceDetection]] = []
        faces_per_frame: list[int] = []

        for frame in frames:
            detections = face_detector.infer(frame)
            faces_per_frame.append(len(detections))
            if detections:
                primary_detection = detections[0]
                frame_detections.append((frame, primary_detection))
                if primary_detection.aligned_face is not None:
                    face_crops.append(primary_detection.aligned_face)

        max_faces_detected = max(faces_per_frame) if faces_per_frame else 0
        audio_duration_sec = round(len(audio) / audio_sample_rate, 2) if audio is not None else 0.0

        face_assessment = self._analyze_face_spoof(
            face_spoof,
            frame_detections,
            max_faces_detected,
        )
        audio_assessment = self._analyze_audio_spoof(
            audio_spoof,
            audio,
            audio_sample_rate,
        )

        liveness_signals = self._liveness.analyze(frames, face_detector) if frames else {}
        transcript = None
        if audio is not None and len(audio) > 0:
            transcript = await transcribe_audio(audio, audio_sample_rate)

        challenge_assessment = self._analyze_challenge(
            challenge,
            transcript,
            liveness_signals,
            audio,
            analysis_started_at,
        )
        session.challenge_verified = (
            challenge_assessment.score >= settings.CHALLENGE_PASS_THRESHOLD
            and challenge_assessment.diagnostics.get("speech_detected", False)
            and challenge_assessment.diagnostics.get("action_sequence_valid", False)
        )

        tamper_assessment = self._analyze_tamper(frames, audio, media.tamper_hints)
        identity_assessment = self._analyze_identity(face_embedding, face_crops)

        reason_values = list(
            dict.fromkeys(
                [
                    *face_assessment.reasons,
                    *audio_assessment.reasons,
                    *challenge_assessment.reasons,
                    *tamper_assessment.reasons,
                    *identity_assessment.reasons,
                ]
            )
        )

        fusion = self._fusion.fuse(
            ComponentScores(
                face_score=face_assessment.score,
                audio_score=audio_assessment.score,
                challenge_score=challenge_assessment.score,
                tamper_score=tamper_assessment.score,
                identity_score=identity_assessment.score,
                all_reasons=reason_values,
                face_confidence=face_assessment.confidence,
                audio_confidence=audio_assessment.confidence,
                challenge_confidence=challenge_assessment.confidence,
                tamper_confidence=tamper_assessment.confidence,
                identity_confidence=identity_assessment.confidence,
            )
        )

        fusion_reason_values = [reason.value for reason in fusion.reasons]
        trust_score = self._update_trust(
            session,
            fusion.overall_score,
            fusion.overall_status,
            fusion_reason_values,
        )

        result_status = fusion.overall_status
        result_risk_level = fusion.risk_level
        result_top_issues = list(fusion.top_issues)
        result_reasons = list(fusion.reasons)
        result_summary = fusion.human_readable_summary
        retry_allowed = fusion.overall_status == OverallStatus.FLAG

        if trust_score <= settings.SCORE_FAIL_THRESHOLD:
            if ReasonCode.TRUST_SCORE_LOW not in result_reasons:
                result_reasons.append(ReasonCode.TRUST_SCORE_LOW)
            if ReasonCode.TRUST_SCORE_LOW.value not in result_top_issues:
                result_top_issues.append(ReasonCode.TRUST_SCORE_LOW.value)
            if result_status == OverallStatus.PASS:
                result_status = OverallStatus.FLAG
                result_risk_level = RiskLevel.MEDIUM
                retry_allowed = True
                result_summary = (
                    f"Candidate requires review "
                    f"(score {fusion.overall_score:.0f}/100). "
                    f"Issues: {', '.join(result_top_issues[:5])}."
                )

        component_confidence = {
            "face": round(face_assessment.confidence, 3),
            "audio": round(audio_assessment.confidence, 3),
            "challenge": round(challenge_assessment.confidence, 3),
            "tamper": round(tamper_assessment.confidence, 3),
            "identity": round(identity_assessment.confidence, 3),
        }
        component_diagnostics = {
            "face": face_assessment.diagnostics,
            "audio": audio_assessment.diagnostics,
            "challenge": challenge_assessment.diagnostics,
            "tamper": tamper_assessment.diagnostics,
            "identity": identity_assessment.diagnostics,
            "fusion": {
                "evidence_coverage": fusion.evidence_coverage,
                "reason_penalty": fusion.reason_penalty,
            },
        }

        logger.info(
            "Analysis complete for session %s | score=%.1f status=%s reasons=%s",
            session.session_id,
            fusion.overall_score,
            result_status.value,
            ",".join(reason.value for reason in result_reasons) or "none",
        )
        logger.debug(
            "Component diagnostics for %s: %s",
            session.session_id,
            component_diagnostics,
        )

        return AnalysisResult(
            overall_status=result_status,
            overall_score=fusion.overall_score,
            face_score=fusion.face_score,
            audio_score=fusion.audio_score,
            challenge_score=fusion.challenge_score,
            tamper_score=fusion.tamper_score,
            identity_consistency_score=fusion.identity_consistency_score,
            reasons=result_reasons,
            human_readable_summary=result_summary,
            risk_level=result_risk_level,
            top_issues=result_top_issues[:5],
            confidence=fusion.confidence_pct,
            frame_count=len(frames),
            faces_detected=max_faces_detected,
            audio_duration_sec=audio_duration_sec,
            challenge_verified=session.challenge_verified,
            trust_score=trust_score,
            retry_allowed=retry_allowed,
            processing_time_ms=round(self._elapsed_ms(started_at), 1),
            analyzed_at=datetime.now(timezone.utc),
            decision_ready=result_status != OverallStatus.FLAG,
            next_action=NextAction.FINALIZE_SESSION if result_status != OverallStatus.FLAG else NextAction.ISSUE_CHALLENGE,
            component_confidence=component_confidence,
            component_diagnostics=component_diagnostics,
        )

    @staticmethod
    def _elapsed_ms(started_at: float) -> float:
        return (perf_counter() - started_at) * 1000

    def _analyze_face_spoof(
        self,
        face_spoof,
        frame_detections: list[tuple[np.ndarray, object]],
        max_faces_detected: int,
    ) -> ComponentAssessment:
        real_probabilities: list[float] = []
        spoof_probabilities: list[float] = []

        for frame, detection in frame_detections[:8]:
            result = face_spoof.infer(frame, detection.bbox)
            real_probabilities.append(result.real_prob)
            spoof_probabilities.append(result.spoof_prob)

        reasons: list[str] = []
        if max_faces_detected > 1:
            reasons.append("MULTIPLE_FACES")

        if not real_probabilities:
            reasons.append("NO_FACE_DETECTED")
            return ComponentAssessment(
                score=0.0,
                confidence=0.15,
                reasons=reasons,
                diagnostics={
                    "frames_evaluated": 0,
                    "max_faces_detected": max_faces_detected,
                    "face_available": False,
                },
            )

        frames_evaluated = len(real_probabilities)
        mean_real = float(np.mean(real_probabilities))
        median_real = float(np.median(real_probabilities))
        min_real = float(np.min(real_probabilities))
        max_real = float(np.max(real_probabilities))
        spoof_vote_ratio = float(
            sum(prob <= settings.FAS_THRESHOLD_SPOOF for prob in real_probabilities) / frames_evaluated
        )
        strong_spoof_ratio = float(
            sum(prob >= 0.75 for prob in spoof_probabilities) / frames_evaluated
        )

        if frames_evaluated < 2:
            reasons.append("FACE_QUALITY_LOW")

        if frames_evaluated >= 3 and (
            (spoof_vote_ratio >= 0.7 and median_real <= settings.FAS_THRESHOLD_REAL)
            or strong_spoof_ratio >= 0.5
        ):
            reasons.append("FACE_SPOOF_DETECTED")

        margin = abs(mean_real - settings.FAS_THRESHOLD_REAL)
        confidence = float(
            np.clip(
                0.25
                + min(frames_evaluated / 6.0, 1.0) * 0.45
                + min(margin / 0.35, 1.0) * 0.30,
                0.15,
                1.0,
            )
        )

        return ComponentAssessment(
            score=round(float(np.clip(mean_real * 100.0, 0.0, 100.0)), 1),
            confidence=confidence,
            reasons=list(dict.fromkeys(reasons)),
            diagnostics={
                "frames_evaluated": frames_evaluated,
                "max_faces_detected": max_faces_detected,
                "mean_real_prob": round(mean_real, 4),
                "median_real_prob": round(median_real, 4),
                "min_real_prob": round(min_real, 4),
                "max_real_prob": round(max_real, 4),
                "spoof_vote_ratio": round(spoof_vote_ratio, 4),
                "strong_spoof_ratio": round(strong_spoof_ratio, 4),
            },
        )

    def _analyze_audio_spoof(
        self,
        audio_spoof,
        audio: np.ndarray | None,
        audio_sample_rate: int,
    ) -> ComponentAssessment:
        if audio is None or len(audio) == 0:
            return ComponentAssessment(
                score=0.0,
                confidence=0.15,
                reasons=["NO_AUDIO"],
                diagnostics={
                    "audio_available": False,
                    "audio_duration_sec": 0.0,
                },
            )

        duration_sec = len(audio) / max(audio_sample_rate, 1)
        window_results = [
            audio_spoof.infer(window, audio_sample_rate)
            for window in self._build_audio_windows(audio, audio_sample_rate)
        ]
        real_probabilities = [result.real_prob for result in window_results]
        spoof_probabilities = [result.spoof_prob for result in window_results]
        mean_real = float(np.mean(real_probabilities))
        median_real = float(np.median(real_probabilities))
        mean_spoof = float(np.mean(spoof_probabilities))
        strong_spoof_votes = sum(
            1
            for real_prob, spoof_prob in zip(real_probabilities, spoof_probabilities)
            if spoof_prob >= 0.75 and (spoof_prob - real_prob) >= 0.20
        )
        majority_vote = max(2, (len(window_results) + 1) // 2)
        margin = abs(mean_real - mean_spoof)
        reasons: list[str] = []
        if strong_spoof_votes >= majority_vote:
            reasons.append("AUDIO_SPOOF_DETECTED")

        confidence = float(
            np.clip(
                0.25
                + min(duration_sec / 4.0, 1.0) * 0.40
                + min(margin / 0.5, 1.0) * 0.35,
                0.20,
                1.0,
            )
        )

        return ComponentAssessment(
            score=round(float(np.clip((median_real * 0.6 + mean_real * 0.4) * 100.0, 0.0, 100.0)), 1),
            confidence=confidence,
            reasons=reasons,
            diagnostics={
                "audio_available": True,
                "audio_duration_sec": round(duration_sec, 2),
                "window_count": len(window_results),
                "window_real_probabilities": [round(value, 4) for value in real_probabilities],
                "window_spoof_probabilities": [round(value, 4) for value in spoof_probabilities],
                "mean_real_prob": round(mean_real, 4),
                "median_real_prob": round(median_real, 4),
                "mean_spoof_prob": round(mean_spoof, 4),
                "strong_spoof_votes": strong_spoof_votes,
            },
        )

    def _analyze_challenge(
        self,
        challenge: Challenge | None,
        transcript: str | None,
        liveness_signals: dict,
        audio_waveform: np.ndarray | None,
        evaluated_at: datetime,
    ) -> ComponentAssessment:
        if challenge is None:
            return ComponentAssessment(
                score=settings.NEUTRAL_COMPONENT_SCORE,
                confidence=0.0,
                reasons=["CHALLENGE_NOT_ISSUED"],
                diagnostics={"challenge_available": False},
            )

        result = self._challenge_verifier.verify(
            challenge,
            transcript,
            liveness_signals,
            audio_waveform,
            evaluated_at=evaluated_at,
        )
        completed_actions = sum(
            1
            for action, matched in {
                "blink_twice": result.blink_detected,
                "turn_head_left": result.left_turn_detected,
                "turn_head_right": result.right_turn_detected,
            }.items()
            if action in challenge.required_actions and matched
        )
        action_count = len(challenge.required_actions)
        confidence = float(
            np.clip(
                0.20
                + (0.25 if result.speech_detected else 0.0)
                + (0.20 if transcript else 0.10 if result.speech_detected else 0.0)
                + min(action_count / 3.0, 1.0) * 0.20
                + min(completed_actions / max(action_count, 1), 1.0) * 0.15,
                0.15,
                1.0,
            )
        )

        return ComponentAssessment(
            score=round(float(np.clip(result.score, 0.0, 100.0)), 1),
            confidence=confidence,
            reasons=result.reasons,
            diagnostics={
                "challenge_available": True,
                "challenge_type": challenge.challenge_type,
                "speech_detected": result.speech_detected,
                "keyword_matched": result.keyword_matched,
                "action_sequence_valid": result.action_sequence_valid,
                "blink_detected": result.blink_detected,
                "head_turn_detected": result.head_turn_detected,
                "transcript": transcript,
                "required_actions": challenge.required_actions,
            },
        )

    def _build_audio_windows(
        self,
        audio: np.ndarray,
        audio_sample_rate: int,
    ) -> list[np.ndarray]:
        if audio is None or len(audio) == 0:
            return []

        clip_duration_sec = settings.AUDIO_CLIP_SAMPLES / max(settings.AUDIO_SAMPLE_RATE, 1)
        window_samples = int(max(audio_sample_rate, 1) * clip_duration_sec)
        if window_samples <= 0 or len(audio) <= window_samples:
            return [audio]

        window_count = min(3, max(2, int(np.ceil(len(audio) / window_samples))))
        start_positions = np.linspace(
            0,
            len(audio) - window_samples,
            num=window_count,
            dtype=int,
        ).tolist()
        unique_positions = list(dict.fromkeys(start_positions))
        return [audio[start:start + window_samples] for start in unique_positions]

    def _analyze_tamper(
        self,
        frames: list[np.ndarray],
        audio: np.ndarray | None,
        tamper_hints: dict,
    ) -> ComponentAssessment:
        result = self._tamper.analyze(frames, audio, tamper_hints)
        reasons = list(result.flags)
        if result.duplicate_frames_detected and (result.motion_stagnation or result.frame_freeze):
            reasons.append("REPLAY_DETECTED")

        confidence = float(
            np.clip(
                0.30
                + min(len(frames) / 10.0, 1.0) * 0.45
                + (0.15 if audio is not None and len(audio) > 0 else 0.0),
                0.20,
                1.0,
            )
        )

        return ComponentAssessment(
            score=round(float(np.clip(result.score, 0.0, 100.0)), 1),
            confidence=confidence,
            reasons=list(dict.fromkeys(reasons)),
            diagnostics={
                "duplicate_frames_detected": result.duplicate_frames_detected,
                "duplicate_ratio": result.duplicate_ratio,
                "mean_frame_delta": result.mean_frame_delta,
                "motion_stagnation": result.motion_stagnation,
                "audio_silence": result.audio_silence,
                "frame_freeze": result.frame_freeze,
                "metadata_anomaly": result.metadata_anomaly,
                "tamper_hints": tamper_hints,
            },
        )

    def _analyze_identity(
        self,
        face_embedding,
        face_crops: list[np.ndarray],
    ) -> ComponentAssessment:
        if not face_crops:
            return ComponentAssessment(
                score=0.0,
                confidence=0.10,
                reasons=["NO_FACE_DETECTED"],
                diagnostics={"face_count": 0, "model_available": bool(face_embedding)},
            )

        if not face_embedding or not face_embedding.is_ready():
            logger.debug("Identity check skipped because face_embedding is unavailable")
            return ComponentAssessment(
                score=settings.NEUTRAL_COMPONENT_SCORE,
                confidence=0.0,
                reasons=[],
                diagnostics={"face_count": len(face_crops), "model_available": False},
            )

        identity_result = IdentityConsistencyChecker(face_embedding).analyze(face_crops)
        margin = abs(identity_result.mean_similarity - settings.IDENTITY_COSINE_THRESHOLD)
        confidence = float(
            np.clip(
                0.20
                + min(len(face_crops) / 6.0, 1.0) * 0.45
                + min(margin / 0.5, 1.0) * 0.25,
                0.20,
                1.0,
            )
        )
        if len(face_crops) < 2:
            confidence = min(confidence, 0.45)

        return ComponentAssessment(
            score=round(float(np.clip(identity_result.score, 0.0, 100.0)), 1),
            confidence=confidence,
            reasons=identity_result.flags,
            diagnostics={
                "face_count": identity_result.face_count,
                "consistent": identity_result.consistent,
                "mean_similarity": identity_result.mean_similarity,
                "min_similarity": identity_result.min_similarity,
                "model_available": True,
            },
        )

    def _update_trust(
        self,
        session: SessionData,
        overall_score: float,
        status: OverallStatus,
        reasons: list[str],
    ) -> float:
        unique_reasons = list(dict.fromkeys(reasons))
        penalty = min(sum(_TRUST_REASON_IMPACT.get(reason, 1) for reason in unique_reasons), 18)
        bonus = 4.0 if status == OverallStatus.PASS else 0.0
        target_score = float(np.clip(overall_score - penalty + bonus, 0.0, 100.0))
        smoothed_score = (
            session.trust_score * (1.0 - settings.TRUST_SCORE_SMOOTHING)
            + target_score * settings.TRUST_SCORE_SMOOTHING
        )

        if status == OverallStatus.FAIL and penalty >= 10:
            smoothed_score = min(smoothed_score, max(settings.TRUST_SCORE_FAIL_FLOOR, overall_score))

        session.anomaly_count += sum(
            1 for reason in unique_reasons if reason not in {"INSUFFICIENT_EVIDENCE", "STT_UNAVAILABLE"}
        )
        session.issue_history.extend(unique_reasons)
        session.issue_history = session.issue_history[-25:]
        session.trust_score = round(float(np.clip(smoothed_score, 0.0, 100.0)), 1)

        if (
            session.trust_score <= settings.SCORE_FAIL_THRESHOLD
            and "TRUST_SCORE_LOW" not in session.issue_history
        ):
            session.issue_history.append("TRUST_SCORE_LOW")

        return session.trust_score

    def _fail_result(self, reason: ReasonCode, message: str, elapsed_ms: float) -> AnalysisResult:
        return AnalysisResult(
            overall_status=OverallStatus.FAIL,
            overall_score=0.0,
            face_score=0.0,
            audio_score=0.0,
            challenge_score=0.0,
            tamper_score=0.0,
            identity_consistency_score=0.0,
            reasons=[reason],
            human_readable_summary=f"Verification failed: {message}",
            risk_level=RiskLevel.HIGH,
            top_issues=[reason.value],
            confidence="95%",
            trust_score=0.0,
            retry_allowed=False,
            processing_time_ms=round(elapsed_ms, 1),
            decision_ready=True,
            next_action=NextAction.NONE,
        )

    def _error_result(self, reason: ReasonCode, message: str, elapsed_ms: float) -> AnalysisResult:
        return AnalysisResult(
            overall_status=OverallStatus.FLAG,
            overall_score=0.0,
            face_score=0.0,
            audio_score=0.0,
            challenge_score=0.0,
            tamper_score=0.0,
            identity_consistency_score=0.0,
            reasons=[reason],
            human_readable_summary=f"Processing error ({message}) - please retry",
            risk_level=RiskLevel.MEDIUM,
            top_issues=[reason.value],
            confidence="50%",
            trust_score=0.0,
            retry_allowed=True,
            processing_time_ms=round(elapsed_ms, 1),
            decision_ready=False,
            next_action=NextAction.ISSUE_CHALLENGE,
        )

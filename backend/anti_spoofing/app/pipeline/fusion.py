"""Score fusion and decision logic for anti-spoofing analysis."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from app.api.schemas import OverallStatus, ReasonCode, RiskLevel
from app.config import get_settings

settings = get_settings()

_CRITICAL_SIGNALS = frozenset(
    {
        "FACE_SPOOF_DETECTED",
        "AUDIO_SPOOF_DETECTED",
        "REPLAY_DETECTED",
        "FACE_SWITCH_DETECTED",
        "CHALLENGE_TIMEOUT",
        "CHALLENGE_EXPIRED",
    }
)

_SIGNAL_PENALTIES: dict[str, float] = {
    "FACE_SPOOF_DETECTED": 18.0,
    "AUDIO_SPOOF_DETECTED": 18.0,
    "REPLAY_DETECTED": 20.0,
    "FACE_SWITCH_DETECTED": 16.0,
    "MULTIPLE_FACES": 10.0,
    "IDENTITY_INCONSISTENT": 12.0,
    "KEYWORD_MISMATCH": 8.0,
    "MOTION_NONCOMPLIANT": 8.0,
    "BLINK_NOT_DETECTED": 5.0,
    "HEAD_TURN_NOT_DETECTED": 5.0,
    "CHALLENGE_SEQUENCE_INVALID": 6.0,
    "NO_AUDIO": 7.0,
    "AUDIO_SILENCE": 6.0,
    "NO_FACE_DETECTED": 10.0,
    "FACE_QUALITY_LOW": 5.0,
    "DUPLICATE_FRAMES": 4.0,
    "LOW_MOTION": 7.0,
    "FRAME_FREEZE": 7.0,
    "METADATA_ANOMALY": 3.0,
    "TRUST_SCORE_LOW": 8.0,
    "STT_UNAVAILABLE": 3.0,
    "INSUFFICIENT_EVIDENCE": 6.0,
}


@dataclass
class ComponentScores:
    face_score: float
    audio_score: float
    challenge_score: float
    tamper_score: float
    identity_score: float
    all_reasons: list[str] = field(default_factory=list)

    face_confidence: float = 1.0
    audio_confidence: float = 1.0
    challenge_confidence: float = 1.0
    tamper_confidence: float = 1.0
    identity_confidence: float = 1.0


@dataclass
class FusionResult:
    overall_status: OverallStatus
    overall_score: float
    face_score: float
    audio_score: float
    challenge_score: float
    tamper_score: float
    identity_consistency_score: float
    risk_level: RiskLevel
    reasons: list[ReasonCode]
    top_issues: list[str]
    confidence_pct: str
    human_readable_summary: str
    evidence_coverage: float
    reason_penalty: float


class ScoreFusion:
    def fuse(self, scores: ComponentScores) -> FusionResult:
        weights = {
            "face": settings.WEIGHT_FACE,
            "audio": settings.WEIGHT_AUDIO,
            "challenge": settings.WEIGHT_CHALLENGE,
            "tamper": settings.WEIGHT_TAMPER,
            "identity": settings.WEIGHT_IDENTITY,
        }
        raw_scores = {
            "face": scores.face_score,
            "audio": scores.audio_score,
            "challenge": scores.challenge_score,
            "tamper": scores.tamper_score,
            "identity": scores.identity_score,
        }
        confidences = {
            "face": self._clip_confidence(scores.face_confidence),
            "audio": self._clip_confidence(scores.audio_confidence),
            "challenge": self._clip_confidence(scores.challenge_confidence),
            "tamper": self._clip_confidence(scores.tamper_confidence),
            "identity": self._clip_confidence(scores.identity_confidence),
        }

        effective_scores = {
            name: self._effective_score(raw_scores[name], confidences[name])
            for name in raw_scores
        }
        weighted_sum = sum(weights[name] * effective_scores[name] for name in weights)
        evidence_coverage = sum(weights[name] * confidences[name] for name in weights)

        reason_values = list(dict.fromkeys(scores.all_reasons))
        if evidence_coverage < settings.MIN_PASS_EVIDENCE_COVERAGE and "INSUFFICIENT_EVIDENCE" not in reason_values:
            reason_values.append("INSUFFICIENT_EVIDENCE")

        reason_penalty = min(
            sum(_SIGNAL_PENALTIES.get(reason, 0.0) for reason in set(reason_values)),
            settings.MAX_REASON_PENALTY,
        )
        critical_count = sum(1 for reason in set(reason_values) if reason in _CRITICAL_SIGNALS)
        low_component_count = sum(
            1
            for name, raw in raw_scores.items()
            if raw < settings.LOW_COMPONENT_SCORE_THRESHOLD and confidences[name] >= 0.55
        )

        coverage_adjustment = (evidence_coverage - 0.65) * 10.0
        overall = float(
            max(
                0.0,
                min(100.0, weighted_sum - reason_penalty + coverage_adjustment),
            )
        )
        overall = round(overall, 1)

        if (
            overall >= settings.SCORE_PASS_THRESHOLD
            and evidence_coverage >= settings.MIN_PASS_EVIDENCE_COVERAGE
            and critical_count == 0
            and low_component_count <= 1
        ):
            status = OverallStatus.PASS
        elif (
            overall <= settings.SCORE_FAIL_THRESHOLD
            or (critical_count >= 2 and overall < settings.SCORE_PASS_THRESHOLD)
            or (critical_count >= 1 and low_component_count >= 2)
            or (low_component_count >= 3 and evidence_coverage >= 0.65)
        ):
            status = OverallStatus.FAIL
        else:
            status = OverallStatus.FLAG

        if evidence_coverage < settings.MIN_PASS_EVIDENCE_COVERAGE and status == OverallStatus.PASS:
            status = OverallStatus.FLAG

        if status == OverallStatus.FAIL or critical_count >= 2:
            risk = RiskLevel.HIGH
        elif status == OverallStatus.FLAG or reason_penalty >= 8.0:
            risk = RiskLevel.MEDIUM
        else:
            risk = RiskLevel.LOW

        reason_map = {reason.value: reason for reason in ReasonCode}
        reason_enums = [reason_map[reason] for reason in reason_values if reason in reason_map]
        top_issues = self._top_issues(reason_values, raw_scores, effective_scores)
        confidence = self._confidence_pct(overall, evidence_coverage, reason_penalty, status)
        summary = self._summary(status, overall, risk, top_issues)

        return FusionResult(
            overall_status=status,
            overall_score=overall,
            face_score=round(raw_scores["face"], 1),
            audio_score=round(raw_scores["audio"], 1),
            challenge_score=round(raw_scores["challenge"], 1),
            tamper_score=round(raw_scores["tamper"], 1),
            identity_consistency_score=round(raw_scores["identity"], 1),
            risk_level=risk,
            reasons=reason_enums,
            top_issues=top_issues,
            confidence_pct=confidence,
            human_readable_summary=summary,
            evidence_coverage=round(evidence_coverage, 3),
            reason_penalty=round(reason_penalty, 1),
        )

    @staticmethod
    def _clip_confidence(value: float) -> float:
        return float(max(0.0, min(1.0, value)))

    @staticmethod
    def _effective_score(raw_score: float, confidence: float) -> float:
        neutral = settings.NEUTRAL_COMPONENT_SCORE
        return neutral + (raw_score - neutral) * confidence

    @staticmethod
    def _top_issues(
        reasons: list[str],
        raw_scores: dict[str, float],
        effective_scores: dict[str, float],
    ) -> list[str]:
        ranked_reasons = sorted(
            set(reasons),
            key=lambda reason: _SIGNAL_PENALTIES.get(reason, 0.0),
            reverse=True,
        )
        top_issues = ranked_reasons[:3]

        component_labels = {
            "face": "FACE_SCORE_LOW",
            "audio": "AUDIO_SCORE_LOW",
            "challenge": "CHALLENGE_SCORE_LOW",
            "tamper": "TAMPER_SCORE_LOW",
            "identity": "IDENTITY_SCORE_LOW",
        }
        for name, score in sorted(effective_scores.items(), key=lambda item: item[1]):
            if raw_scores[name] < settings.LOW_COMPONENT_SCORE_THRESHOLD:
                label = component_labels[name]
                if label not in top_issues:
                    top_issues.append(label)
            if len(top_issues) >= 5:
                break

        return top_issues[:5]

    @staticmethod
    def _confidence_pct(
        overall: float,
        evidence_coverage: float,
        reason_penalty: float,
        status: OverallStatus,
    ) -> str:
        if math.isnan(overall) or math.isinf(overall):
            overall = 0.0

        target = (
            settings.SCORE_PASS_THRESHOLD
            if status == OverallStatus.PASS
            else settings.SCORE_FAIL_THRESHOLD
        )
        margin = abs(overall - target)
        raw_confidence = 45.0 + margin * 1.4 + evidence_coverage * 20.0 + min(reason_penalty, 20.0) * 0.3
        confidence = int(max(35.0, min(96.0, raw_confidence)))
        return f"{confidence}%"

    @staticmethod
    def _summary(
        status: OverallStatus,
        overall: float,
        risk: RiskLevel,
        top_issues: list[str],
    ) -> str:
        issues_str = ", ".join(top_issues) if top_issues else "none"
        if status == OverallStatus.PASS:
            return (
                f"Candidate passed anti-spoofing verification "
                f"(score {overall:.0f}/100, risk: {risk.value})."
            )
        if status == OverallStatus.FAIL:
            return (
                f"Candidate failed verification "
                f"(score {overall:.0f}/100). Issues: {issues_str}."
            )
        return (
            f"Candidate requires review "
            f"(score {overall:.0f}/100). Issues: {issues_str}."
        )

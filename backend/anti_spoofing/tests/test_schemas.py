from __future__ import annotations

import pytest


def test_analysis_result_rejects_out_of_range_score():
    from app.api.schemas import AnalysisResult, OverallStatus, RiskLevel

    with pytest.raises(Exception):
        AnalysisResult(
            overall_status=OverallStatus.PASS,
            overall_score=150.0,
            face_score=80.0,
            audio_score=80.0,
            challenge_score=80.0,
            tamper_score=80.0,
            identity_consistency_score=80.0,
            reasons=[],
            human_readable_summary="",
            risk_level=RiskLevel.LOW,
            top_issues=[],
            confidence="80%",
        )


def test_candidate_id_is_required():
    from app.api.schemas import CreateSessionRequest

    with pytest.raises(Exception):
        CreateSessionRequest(candidate_id="")


def test_reason_codes_include_critical_failures():
    from app.api.schemas import ReasonCode

    values = {reason.value for reason in ReasonCode}

    for code in (
        "FACE_SPOOF_DETECTED",
        "AUDIO_SPOOF_DETECTED",
        "REPLAY_DETECTED",
        "MODEL_UNAVAILABLE",
    ):
        assert code in values


def test_overall_status_values_are_stable():
    from app.api.schemas import OverallStatus

    assert OverallStatus.PASS.value == "PASS"
    assert OverallStatus.FAIL.value == "FAIL"
    assert OverallStatus.FLAG.value == "FLAG"

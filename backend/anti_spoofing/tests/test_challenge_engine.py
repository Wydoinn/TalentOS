from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np


def test_generate_phrase_challenge():
    from app.pipeline.challenge_engine import ChallengeEngine

    challenge = ChallengeEngine().generate("challenge-1", "phrase")

    assert challenge.challenge_type == "phrase"
    assert challenge.prompt
    assert challenge.expected_keyword
    assert "blink_twice" in challenge.required_actions
    assert len(challenge.required_actions) == 2
    assert not challenge.is_expired()


def test_generate_digit_code_challenge():
    from app.pipeline.challenge_engine import ChallengeEngine

    challenge = ChallengeEngine().generate("challenge-2", "digit_code")

    assert challenge.challenge_type == "digit_code"
    assert challenge.expected_keyword.isdigit()


def test_challenge_roundtrip_serialization():
    from app.pipeline.challenge_engine import ChallengeEngine

    challenge = ChallengeEngine().generate("challenge-3", "phrase")
    restored = challenge.__class__.from_dict(challenge.to_dict())

    assert restored.challenge_id == challenge.challenge_id
    assert restored.required_actions == challenge.required_actions
    assert restored.expected_keyword == challenge.expected_keyword


def test_expired_challenge_returns_zero_score():
    from app.pipeline.challenge_engine import ChallengeEngine, ChallengeVerifier

    challenge = ChallengeEngine().generate("challenge-4", "phrase")
    challenge.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    audio = (np.random.default_rng(0).standard_normal(16000) * 0.1).astype(np.float32)

    result = ChallengeVerifier().verify(
        challenge,
        "transcript",
        {"blink_detected": True, "head_turn_detected": True},
        audio,
    )

    assert result.score == 0.0
    assert result.timed_out is True


def test_keyword_match_exact():
    from app.pipeline.challenge_engine import match_keyword

    assert match_keyword("security alpha", "security alpha") is True


def test_keyword_match_substring():
    from app.pipeline.challenge_engine import match_keyword

    assert match_keyword("okay security alpha done", "security alpha") is True


def test_keyword_match_fuzzy():
    from app.pipeline.challenge_engine import match_keyword

    assert match_keyword("securty alfa", "security alpha") is True


def test_keyword_match_rejects_unrelated_phrase():
    from app.pipeline.challenge_engine import match_keyword

    assert match_keyword("completely different words here", "security alpha") is False


def test_challenge_verifier_passes_with_matching_transcript():
    from app.pipeline.challenge_engine import ChallengeEngine, ChallengeVerifier

    challenge = ChallengeEngine().generate("challenge-5", "phrase")
    audio = (np.random.default_rng(1).standard_normal(80000) * 0.3).astype(np.float32)

    result = ChallengeVerifier().verify(
        challenge,
        challenge.expected_keyword,
        {
            "blink_detected": True,
            "left_turn_detected": True,
            "right_turn_detected": True,
            "head_turn_detected": True,
            "event_sequence": challenge.required_actions,
        },
        audio,
    )

    assert result.speech_detected is True
    assert result.keyword_matched is True
    assert result.score >= 70.0


def test_challenge_verifier_softens_when_transcript_is_missing():
    from app.pipeline.challenge_engine import ChallengeEngine, ChallengeVerifier

    challenge = ChallengeEngine().generate("challenge-6", "phrase")
    audio = (np.random.default_rng(2).standard_normal(80000) * 0.3).astype(np.float32)

    result = ChallengeVerifier().verify(
        challenge,
        None,
        {"blink_detected": True, "head_turn_detected": True},
        audio,
    )

    assert result.keyword_matched is False
    assert "STT_UNAVAILABLE" in result.reasons
    assert result.score > 0.0


def test_action_sequence_accepts_out_of_order_events():
    from app.pipeline.challenge_engine import ChallengeEngine, ChallengeVerifier

    challenge = ChallengeEngine().generate("challenge-7", "phrase")

    result = ChallengeVerifier().verify(
        challenge,
        challenge.expected_keyword,
        {
            "blink_detected": "blink_twice" in challenge.required_actions,
            "left_turn_detected": "turn_head_left" in challenge.required_actions,
            "right_turn_detected": "turn_head_right" in challenge.required_actions,
            "head_turn_detected": True,
            "event_sequence": list(reversed(challenge.required_actions)),
        },
        (np.random.default_rng(3).standard_normal(80000) * 0.3).astype(np.float32),
    )

    assert result.action_sequence_valid is True


def test_compute_yaw_uses_face_width():
    from app.config import get_settings
    from app.pipeline.challenge_engine import LivenessAnalyzer

    settings = get_settings()
    analyzer = LivenessAnalyzer()
    landmarks = {
        analyzer._LEFT_EAR: (100.0, 50.0, 0.0),
        analyzer._RIGHT_EAR: (220.0, 50.0, 0.0),
        analyzer._NOSE_TIP: (180.0, 60.0, 0.0),
    }

    yaw = analyzer._compute_yaw(landmarks)

    assert yaw is not None
    assert yaw >= settings.LIVENESS_HEAD_TURN_DEG

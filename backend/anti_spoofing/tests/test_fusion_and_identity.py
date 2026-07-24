from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np


def test_score_fusion_passes_with_strong_scores():
    from app.pipeline.fusion import ComponentScores, ScoreFusion

    result = ScoreFusion().fuse(ComponentScores(90, 88, 85, 95, 92, []))

    assert result.overall_status.value == "PASS"
    assert result.overall_score >= 75.0
    assert result.risk_level.value == "low"


def test_score_fusion_fails_on_face_spoof_signal():
    from app.pipeline.fusion import ComponentScores, ScoreFusion

    result = ScoreFusion().fuse(
        ComponentScores(20, 30, 50, 60, 70, ["FACE_SPOOF_DETECTED"])
    )

    assert result.overall_status.value == "FAIL"
    assert result.overall_score <= 25.0
    assert result.risk_level.value == "high"


def test_score_fusion_fails_on_replay_signal():
    from app.pipeline.fusion import ComponentScores, ScoreFusion

    result = ScoreFusion().fuse(
        ComponentScores(70, 72, 65, 5, 60, ["REPLAY_DETECTED", "DUPLICATE_FRAMES"])
    )

    assert result.overall_status.value == "FAIL"


def test_score_fusion_flags_borderline_result():
    from app.pipeline.fusion import ComponentScores, ScoreFusion

    result = ScoreFusion().fuse(ComponentScores(65, 60, 55, 70, 65, []))

    assert result.overall_status.value == "FLAG"
    assert result.risk_level.value == "medium"


def test_score_fusion_returns_confidence_string():
    from app.pipeline.fusion import ComponentScores, ScoreFusion

    result = ScoreFusion().fuse(ComponentScores(80, 82, 79, 85, 81, []))
    confidence_value = int(result.confidence_pct.rstrip("%"))

    assert result.confidence_pct.endswith("%")
    assert 0 <= confidence_value <= 100


def test_score_fusion_populates_summary():
    from app.pipeline.fusion import ComponentScores, ScoreFusion

    fusion = ScoreFusion()
    clean_result = fusion.fuse(ComponentScores(80, 80, 80, 80, 80, []))
    flagged_result = fusion.fuse(
        ComponentScores(20, 20, 20, 20, 20, ["FACE_SPOOF_DETECTED"])
    )

    assert len(clean_result.human_readable_summary) > 10
    assert len(flagged_result.human_readable_summary) > 10


def test_identity_checker_returns_failure_when_no_faces_are_available():
    from app.models.face_embedding import FaceEmbeddingModel
    from app.pipeline.identity_checker import IdentityConsistencyChecker

    checker = IdentityConsistencyChecker(MagicMock(spec=FaceEmbeddingModel))
    result = checker.analyze([])

    assert result.score == 0.0
    assert result.consistent is False
    assert "NO_FACE_DETECTED" in result.flags


def test_identity_checker_returns_neutral_single_frame_score():
    from app.models.face_embedding import FaceEmbeddingModel
    from app.pipeline.identity_checker import IdentityConsistencyChecker

    checker = IdentityConsistencyChecker(MagicMock(spec=FaceEmbeddingModel))
    crop = np.random.randint(0, 255, (224, 224, 3), dtype=np.uint8)

    result = checker.analyze([crop])

    assert result.score == 70.0
    assert result.consistent is True


def test_identity_checker_scores_identical_embeddings_high():
    from app.models.face_embedding import EmbeddingResult, FaceEmbeddingModel
    from app.pipeline.identity_checker import IdentityConsistencyChecker

    model = MagicMock(spec=FaceEmbeddingModel)
    embedding = np.ones(512, np.float32) / np.sqrt(512)
    model.infer.return_value = EmbeddingResult(embedding, 1.0)
    checker = IdentityConsistencyChecker(model)
    crops = [np.random.randint(0, 255, (224, 224, 3), dtype=np.uint8) for _ in range(5)]

    result = checker.analyze(crops)

    assert result.score >= 80.0
    assert result.consistent is True


def test_identity_checker_flags_inconsistent_embeddings():
    from app.models.face_embedding import EmbeddingResult, FaceEmbeddingModel
    from app.pipeline.identity_checker import IdentityConsistencyChecker

    rng = np.random.default_rng(42)
    model = MagicMock(spec=FaceEmbeddingModel)
    model.infer.side_effect = [
        EmbeddingResult(rng.standard_normal(512).astype(np.float32), 1.0)
        for _ in range(6)
    ]
    checker = IdentityConsistencyChecker(model)
    crops = [np.random.randint(0, 255, (224, 224, 3), dtype=np.uint8) for _ in range(6)]

    result = checker.analyze(crops)

    assert not result.consistent or result.score < 80.0

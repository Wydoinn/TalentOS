"""
Identity consistency checks built on InsightFace embeddings.

The checker compares embeddings across sampled frames to verify that a single
person stays present throughout the clip.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from app.config import get_settings
from app.models.face_embedding import FaceEmbeddingModel
from app.utils.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


@dataclass
class IdentityResult:
    score: float
    consistent: bool
    face_count: int
    mean_similarity: float
    min_similarity: float
    flags: list[str] = field(default_factory=list)


class IdentityConsistencyChecker:
    def __init__(self, model: FaceEmbeddingModel):
        self._embed = model

    def analyze(self, face_crops: list[np.ndarray]) -> IdentityResult:
        if not face_crops:
            return IdentityResult(
                score=0.0,
                consistent=False,
                face_count=0,
                mean_similarity=0.0,
                min_similarity=0.0,
                flags=["NO_FACE_DETECTED"],
            )

        if len(face_crops) == 1:
            return IdentityResult(
                score=70.0,
                consistent=True,
                face_count=1,
                mean_similarity=1.0,
                min_similarity=1.0,
            )

        embeddings: list[np.ndarray] = []
        for crop in face_crops:
            try:
                result = self._embed.infer(crop)
                embeddings.append(result.embedding)
            except Exception as exc:
                logger.debug("Embedding extraction failed for a frame: %s", exc)

        if len(embeddings) < 2:
            return IdentityResult(
                score=50.0,
                consistent=True,
                face_count=len(face_crops),
                mean_similarity=1.0,
                min_similarity=1.0,
                flags=["FACE_QUALITY_LOW"],
            )

        anchor = embeddings[0]
        similarities = [
            FaceEmbeddingModel.cosine_similarity(anchor, embedding)
            for embedding in embeddings[1:]
        ]
        mean_similarity = float(np.mean(similarities))
        min_similarity = float(np.min(similarities))

        threshold = settings.IDENTITY_COSINE_THRESHOLD
        consistent_ratio = sum(1 for similarity in similarities if similarity >= threshold) / len(similarities)
        consistent = consistent_ratio >= settings.IDENTITY_MIN_CONSISTENT_RATIO

        flags: list[str] = []
        if not consistent:
            flags.append("FACE_SWITCH_DETECTED" if min_similarity < 0.0 else "IDENTITY_INCONSISTENT")

        raw_score = mean_similarity * 100.0
        if min_similarity < threshold:
            raw_score = max(0.0, raw_score - (threshold - min_similarity) * 50.0)

        return IdentityResult(
            score=round(float(np.clip(raw_score, 0.0, 100.0)), 1),
            consistent=consistent,
            face_count=len(face_crops),
            mean_similarity=round(mean_similarity, 4),
            min_similarity=round(min_similarity, 4),
            flags=flags,
        )

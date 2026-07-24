from __future__ import annotations

from pathlib import Path
from threading import Lock

import torch
from sentence_transformers import CrossEncoder

from app.utils.scoring import clamp01

_MODEL_SINGLETON: "LocalRerankerModel | None" = None
_LOCK = Lock()


class LocalRerankerModel:
    def __init__(self, model_path: Path, *, batch_size: int = 16) -> None:
        self.model_path = Path(model_path)
        self.batch_size = batch_size
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self._model: CrossEncoder | None = None
        self._load_lock = Lock()
        self._cache_lock = Lock()
        self._pair_cache: dict[tuple[str, str], float] = {}

    def _load(self) -> CrossEncoder:
        if self._model is None:
            with self._load_lock:
                if self._model is None:
                    if not self.model_path.exists():
                        raise FileNotFoundError(f"Reranker model not found at {self.model_path}")
                    self._model = CrossEncoder(
                        str(self.model_path),
                        device=self.device,
                        local_files_only=True,
                    )
        return self._model

    def warmup(self) -> None:
        self.score("warmup", ["warmup"])

    def score(self, query: str, documents: list[str]) -> list[float]:
        if not query.strip() or not documents:
            return []

        normalized_query = query.strip()
        model = self._load()
        results: list[float | None] = [None] * len(documents)
        uncached_indexes: list[int] = []
        uncached_documents: list[str] = []

        with self._cache_lock:
            for index, document in enumerate(documents):
                normalized_document = document.strip()
                cached = self._pair_cache.get((normalized_query, normalized_document))
                if cached is not None:
                    results[index] = cached
                else:
                    uncached_indexes.append(index)
                    uncached_documents.append(normalized_document)

        if uncached_documents:
            logits = model.predict(
                [(normalized_query, document) for document in uncached_documents],
                batch_size=self.batch_size,
                show_progress_bar=False,
                convert_to_numpy=True,
            ).tolist()
            calibrated_scores = self._calibrate_scores([float(value) for value in logits])
            with self._cache_lock:
                for index, document, score in zip(
                    uncached_indexes,
                    uncached_documents,
                    calibrated_scores,
                    strict=False,
                ):
                    self._pair_cache[(normalized_query, document)] = score
                    results[index] = score

        return [round(float(score or 0.0), 4) for score in results]

    @staticmethod
    def _calibrate_scores(logits: list[float]) -> list[float]:
        if not logits:
            return []

        tensor = torch.tensor(logits, dtype=torch.float32)
        sigmoid_scores = torch.sigmoid(tensor / 2.2)
        minimum = float(torch.min(sigmoid_scores))
        maximum = float(torch.max(sigmoid_scores))

        if maximum - minimum < 1e-6:
            return [round(clamp01(float(score)), 4) for score in sigmoid_scores.tolist()]

        spread_scores = (sigmoid_scores - minimum) / (maximum - minimum)
        calibrated = (sigmoid_scores * 0.55) + ((0.15 + (spread_scores * 0.8)) * 0.45)
        return [round(clamp01(float(score)), 4) for score in calibrated.tolist()]


def get_reranker_model(model_path: Path, *, batch_size: int = 16) -> LocalRerankerModel:
    global _MODEL_SINGLETON
    with _LOCK:
        if _MODEL_SINGLETON is None:
            _MODEL_SINGLETON = LocalRerankerModel(model_path, batch_size=batch_size)
    return _MODEL_SINGLETON

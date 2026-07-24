from __future__ import annotations

from pathlib import Path
from threading import Lock

import torch
from sentence_transformers import SentenceTransformer

_MODEL_SINGLETON: "LocalEmbeddingModel | None" = None
_LOCK = Lock()
_BGE_QUERY_PREFIX = "Represent this sentence for searching relevant candidates: "


class LocalEmbeddingModel:
    def __init__(self, model_path: Path, *, batch_size: int = 32) -> None:
        self.model_path = Path(model_path).expanduser().resolve(strict=False)
        self.batch_size = batch_size
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self._model: SentenceTransformer | None = None
        self._load_lock = Lock()
        self._cache_lock = Lock()
        self._passage_cache: dict[str, list[float]] = {}
        self._query_cache: dict[str, list[float]] = {}

    def _load(self) -> SentenceTransformer:
        if self._model is None:
            with self._load_lock:
                if self._model is None:
                    if not self.model_path.exists():
                        raise FileNotFoundError(f"Embedding model not found at {self.model_path}")
                    self._model = SentenceTransformer(
                        self.model_path.as_posix(),
                        device=self.device,
                        local_files_only=True,
                    )
        return self._model

    def warmup(self) -> None:
        self.embed_queries(["warmup"])
        self.embed_passages(["warmup"])

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts, is_query=False)

    def embed_queries(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts, is_query=True)

    def _embed(self, texts: list[str], *, is_query: bool) -> list[list[float]]:
        if not texts:
            return []

        model = self._load()
        cache = self._query_cache if is_query else self._passage_cache
        results: list[list[float] | None] = [None] * len(texts)
        uncached_indexes: list[int] = []
        uncached_texts: list[str] = []

        with self._cache_lock:
            for index, text in enumerate(texts):
                normalized_text = text.strip()
                cached = cache.get(normalized_text)
                if cached is not None:
                    results[index] = list(cached)
                else:
                    uncached_indexes.append(index)
                    uncached_texts.append(normalized_text)

        if uncached_texts:
            encoded = model.encode(
                [self._prepare_text(text, is_query=is_query) for text in uncached_texts],
                batch_size=self.batch_size,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            ).tolist()
            with self._cache_lock:
                for index, text, vector in zip(uncached_indexes, uncached_texts, encoded, strict=False):
                    cache[text] = vector
                    results[index] = list(vector)

        return [vector if vector is not None else [] for vector in results]

    @staticmethod
    def _prepare_text(text: str, *, is_query: bool) -> str:
        normalized = text.strip()
        if is_query:
            return f"{_BGE_QUERY_PREFIX}{normalized}"
        return normalized


def get_embedding_model(model_path: Path) -> LocalEmbeddingModel:
    global _MODEL_SINGLETON
    with _LOCK:
        if _MODEL_SINGLETON is None:
            _MODEL_SINGLETON = LocalEmbeddingModel(model_path)
    return _MODEL_SINGLETON

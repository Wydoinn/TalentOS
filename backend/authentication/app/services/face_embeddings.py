from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

os.environ.setdefault("NO_ALBUMENTATIONS_UPDATE", "1")

from insightface.app import FaceAnalysis

from app.core.config import get_settings


class FaceEmbeddingError(Exception):
    """Base error for face embedding generation."""


class InvalidImageError(FaceEmbeddingError):
    """Raised when the supplied bytes are not a valid image."""


class NoFaceDetectedError(FaceEmbeddingError):
    """Raised when no face is detected in an image."""


class MultipleFacesDetectedError(FaceEmbeddingError):
    """Raised when multiple faces are detected in an image."""


class FaceEmbeddingService:
    def __init__(self, model_root: str) -> None:
        self.model_root = model_root
        self._app: FaceAnalysis | None = None

    def _resolve_face_analysis_root(self) -> Path:
        configured = Path(self.model_root).expanduser().resolve(strict=False)

        if configured.name == "buffalo_l":
            models_dir = configured.parent
            if models_dir.name == "models":
                return models_dir.parent
            return models_dir

        if (configured / "buffalo_l").exists():
            return configured.parent

        return configured

    def _get_app(self) -> FaceAnalysis:
        if self._app is None:
            face_analysis_root = self._resolve_face_analysis_root()
            app = FaceAnalysis(
                name="buffalo_l",
                root=str(face_analysis_root),
                providers=["CPUExecutionProvider"],
            )
            app.prepare(ctx_id=-1, det_size=(640, 640))
            self._app = app
        return self._app

    def decode_image(self, image_bytes: bytes, *, image_label: str = "image") -> np.ndarray:
        image_buffer = np.frombuffer(image_bytes, dtype=np.uint8)
        image = cv2.imdecode(image_buffer, cv2.IMREAD_COLOR)
        if image is None:
            raise InvalidImageError(f"The {image_label} could not be decoded as an image.")
        return image

    def extract_normalized_embedding(
        self,
        image_bytes: bytes,
        *,
        image_label: str = "image",
    ) -> np.ndarray:
        image = self.decode_image(image_bytes, image_label=image_label)

        faces = self._get_app().get(image)
        if not faces:
            raise NoFaceDetectedError(f"No face detected in the {image_label}.")
        if len(faces) > 1:
            raise MultipleFacesDetectedError(f"Multiple faces detected in the {image_label}.")

        embedding = np.asarray(faces[0].embedding, dtype=np.float32).reshape(-1)
        if embedding.shape != (512,):
            raise FaceEmbeddingError(
                f"ArcFace returned an unexpected embedding size: {embedding.shape[0]}"
            )

        norm = float(np.linalg.norm(embedding))
        if norm == 0.0:
            raise FaceEmbeddingError("ArcFace produced a zero-length embedding.")

        return embedding / norm


@lru_cache(maxsize=1)
def get_face_embedding_service() -> FaceEmbeddingService:
    settings = get_settings()
    return FaceEmbeddingService(model_root=str(settings.model_root))

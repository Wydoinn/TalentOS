from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api_errors import ApiException
from app.core.config import Settings, get_settings
from app.core.enums import AuthStage, FaceVerificationStatus, UserRole
from app.core.security import TokenBundle, create_access_token
from app.db.models import FaceVerificationLog, User
from app.services.face_embeddings import (
    FaceEmbeddingError,
    FaceEmbeddingService,
    MultipleFacesDetectedError,
    NoFaceDetectedError,
    get_face_embedding_service,
)
from app.services.pinecone_service import PineconeService
from app.utils.similarity import cosine_similarity
from app.utils.time import utcnow


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class FaceRegistrationResult:
    user: User
    token: TokenBundle


@dataclass(frozen=True, slots=True)
class FaceVerificationResult:
    success: bool
    status: FaceVerificationStatus
    similarity_score: float | None
    threshold: float
    remaining_attempts: int
    token: TokenBundle | None = None


class FaceVerificationService:
    def __init__(
        self,
        db: Session,
        *,
        settings: Settings | None = None,
        pinecone_service: PineconeService | None = None,
        face_embeddings: FaceEmbeddingService | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.pinecone_service = pinecone_service or PineconeService(self.settings)
        self.face_embeddings = face_embeddings or get_face_embedding_service()

    async def register_face(
        self,
        *,
        user: User,
        image_bytes: bytes,
    ) -> FaceRegistrationResult:
        if user.role != UserRole.CANDIDATE:
            raise ApiException(
                status_code=403,
                code="candidate_only",
                message="Face registration is available only for candidates.",
            )

        if not user.is_email_verified:
            raise ApiException(
                status_code=403,
                code="email_not_verified",
                message="Verify your email before registering a face.",
            )

        if user.face_registered:
            raise ApiException(
                status_code=409,
                code="face_already_registered",
                message="A face is already registered for this candidate.",
            )

        try:
            embedding = await self._extract_embedding(
                image_bytes=image_bytes,
                image_label="candidate face image",
            )
        except NoFaceDetectedError as exc:
            raise ApiException(
                status_code=422,
                code="no_face_detected",
                message=str(exc),
            ) from exc
        except MultipleFacesDetectedError as exc:
            raise ApiException(
                status_code=422,
                code="multiple_faces_detected",
                message=str(exc),
            ) from exc
        except FaceEmbeddingError as exc:
            raise ApiException(
                status_code=422,
                code="face_embedding_failed",
                message=str(exc),
            ) from exc

        self.pinecone_service.upsert_user_embedding(
            user_id=str(user.id),
            embedding=embedding,
            role=user.role,
        )

        try:
            user.face_registered = True
            user.updated_at = utcnow()
            self.db.add(user)
            self._commit_or_raise(
                message="Unable to complete face registration right now.",
                code="face_registration_persistence_failed",
            )
            self.db.refresh(user)
        except Exception:
            self.db.rollback()
            try:
                self.pinecone_service.delete_user_embedding(user_id=str(user.id))
            except Exception:
                logger.exception(
                    "Failed to remove the face embedding after registration rollback.",
                    extra={"user_id": str(user.id)},
                )
            raise

        token = create_access_token(
            user_id=str(user.id),
            role=user.role,
            stage=AuthStage.AUTHENTICATED,
            extra_claims={"email": user.email},
        )
        return FaceRegistrationResult(user=user, token=token)

    async def verify_face(
        self,
        *,
        user: User,
        image_bytes: bytes,
        device_info: str | None,
    ) -> FaceVerificationResult:
        if user.role != UserRole.CANDIDATE:
            raise ApiException(
                status_code=403,
                code="candidate_only",
                message="Face verification is available only for candidates.",
            )

        if not user.face_registered:
            raise ApiException(
                status_code=409,
                code="face_not_registered",
                message="This candidate must register a face before verification.",
            )

        recent_failures = self._recent_failure_count(user_id=user.id)
        if recent_failures >= self.settings.max_face_attempts:
            raise ApiException(
                status_code=429,
                code="face_attempt_limit_reached",
                message="Maximum face verification attempts reached. Please try again later.",
            )

        try:
            probe_embedding = await self._extract_embedding(
                image_bytes=image_bytes,
                image_label="verification image",
            )
            stored_embedding = self.pinecone_service.fetch_user_embedding(user_id=str(user.id))
            similarity_score = max(
                -1.0,
                min(1.0, float(cosine_similarity(stored_embedding, probe_embedding))),
            )
        except NoFaceDetectedError as exc:
            self._store_face_verification_log(
                user_id=user.id,
                status=FaceVerificationStatus.FAILED,
                similarity_score=None,
                device_info=device_info,
            )
            raise ApiException(
                status_code=422,
                code="no_face_detected",
                message=str(exc),
            ) from exc
        except MultipleFacesDetectedError as exc:
            self._store_face_verification_log(
                user_id=user.id,
                status=FaceVerificationStatus.FAILED,
                similarity_score=None,
                device_info=device_info,
            )
            raise ApiException(
                status_code=422,
                code="multiple_faces_detected",
                message=str(exc),
            ) from exc
        except FaceEmbeddingError as exc:
            self._store_face_verification_log(
                user_id=user.id,
                status=FaceVerificationStatus.FAILED,
                similarity_score=None,
                device_info=device_info,
            )
            raise ApiException(
                status_code=422,
                code="face_embedding_failed",
                message=str(exc),
            ) from exc
        except ApiException:
            self._store_face_verification_log(
                user_id=user.id,
                status=FaceVerificationStatus.FAILED,
                similarity_score=None,
                device_info=device_info,
            )
            raise

        success = similarity_score >= self.settings.face_similarity_threshold
        status = (
            FaceVerificationStatus.VERIFIED
            if success
            else FaceVerificationStatus.FAILED
        )
        self._store_face_verification_log(
            user_id=user.id,
            status=status,
            similarity_score=similarity_score,
            device_info=device_info,
        )

        token = None
        if success:
            token = create_access_token(
                user_id=str(user.id),
                role=user.role,
                stage=AuthStage.AUTHENTICATED,
                extra_claims={"email": user.email},
            )

        failures_after_attempt = recent_failures + (0 if success else 1)
        return FaceVerificationResult(
            success=success,
            status=status,
            similarity_score=similarity_score,
            threshold=self.settings.face_similarity_threshold,
            remaining_attempts=max(
                0, self.settings.max_face_attempts - failures_after_attempt
            ),
            token=token,
        )

    async def _extract_embedding(
        self,
        *,
        image_bytes: bytes,
        image_label: str,
    ):
        return await run_in_threadpool(
            self.face_embeddings.extract_normalized_embedding,
            image_bytes,
            image_label=image_label,
        )

    def _recent_failure_count(self, *, user_id: uuid.UUID) -> int:
        cutoff = utcnow() - timedelta(minutes=self.settings.face_attempt_window_minutes)
        return int(
            self.db.scalar(
                select(func.count(FaceVerificationLog.id)).where(
                    FaceVerificationLog.user_id == user_id,
                    FaceVerificationLog.status == FaceVerificationStatus.FAILED,
                    FaceVerificationLog.timestamp >= cutoff,
                )
            )
            or 0
        )

    def _store_face_verification_log(
        self,
        *,
        user_id: uuid.UUID,
        status: FaceVerificationStatus,
        similarity_score: float | None,
        device_info: str | None,
    ) -> None:
        self.db.add(
            FaceVerificationLog(
                user_id=user_id,
                status=status,
                similarity_score=similarity_score,
                device_info=device_info,
            )
        )
        self._commit_or_raise(
            message="Unable to store the face verification attempt right now.",
            code="face_verification_log_failed",
        )

    def _commit_or_raise(
        self,
        *,
        message: str,
        code: str = "database_error",
    ) -> None:
        try:
            self.db.commit()
        except SQLAlchemyError as exc:
            self.db.rollback()
            raise ApiException(
                status_code=500,
                code=code,
                message=message,
            ) from exc

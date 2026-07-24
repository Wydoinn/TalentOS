from __future__ import annotations

import logging
import time
from typing import Any

import numpy as np
from pinecone import Pinecone, ServerlessSpec
from pinecone.openapi_support.exceptions import PineconeException

from app.api_errors import ApiException
from app.core.config import Settings, get_settings
from app.core.enums import UserRole


logger = logging.getLogger(__name__)


class PineconeService:
    INDEX_PROVISION_TIMEOUT_SECONDS = 90
    INDEX_READY_TIMEOUT_SECONDS = 120
    INDEX_POLL_INTERVAL_SECONDS = 2

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client: Pinecone | None = None
        self._index: Any | None = None

    def is_configured(self) -> bool:
        return bool(self.settings.pinecone_api_key and self.settings.pinecone_index_name)

    def ensure_index_available(self) -> Any:
        if not self.is_configured():
            raise ApiException(
                status_code=503,
                code="pinecone_not_configured",
                message="Pinecone is not configured for face embedding storage.",
            )

        if self._index is not None:
            return self._index

        try:
            client = self._get_client()
            index_name = self.settings.pinecone_index_name
            auto_create_enabled = self.settings.pinecone_auto_create_index or (
                self.settings.environment.lower() in {"development", "dev", "local", "test"}
            )

            index_exists = client.has_index(index_name)
            if auto_create_enabled and not index_exists:
                self._create_index_if_missing(client=client, index_name=index_name)
                index_exists = self._wait_for_index_existence(client=client, index_name=index_name)

            if not index_exists:
                raise ApiException(
                    status_code=503,
                    code="pinecone_index_missing",
                    message=(
                        "The configured Pinecone index does not exist. "
                        "Enable AUTH_PINECONE_AUTO_CREATE_INDEX=true or create the index manually."
                    ),
                )

            description = self._wait_for_index_ready(client=client, index_name=index_name)
            status = self._get_attribute(description, "status")
            ready = bool(self._get_attribute(status, "ready"))
            if not ready:
                raise ApiException(
                    status_code=503,
                    code="pinecone_index_not_ready",
                    message=(
                        "The Pinecone index is still initializing. "
                        "Wait a moment and retry."
                    ),
                )

            host = self._get_attribute(description, "host")
            if not host:
                raise ApiException(
                    status_code=503,
                    code="pinecone_index_host_missing",
                    message="The Pinecone index host could not be resolved.",
                )

            self._index = client.Index(host=host)
            return self._index
        except ApiException:
            raise
        except Exception as exc:
            raise self._translate_exception(exc) from exc

    def _create_index_if_missing(self, *, client: Pinecone, index_name: str) -> None:
        try:
            client.create_index(
                name=index_name,
                vector_type="dense",
                dimension=512,
                metric="cosine",
                spec=ServerlessSpec(
                    cloud=self.settings.pinecone_cloud,
                    region=self.settings.pinecone_region,
                ),
                deletion_protection="disabled",
                tags={"service": "authentication"},
            )
            logger.info("Created missing Pinecone index '%s' for authentication service.", index_name)
        except Exception as exc:
            if self._is_index_already_exists_error(exc):
                return
            raise

    def _wait_for_index_existence(self, *, client: Pinecone, index_name: str) -> bool:
        deadline = time.monotonic() + self.INDEX_PROVISION_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if client.has_index(index_name):
                return True
            time.sleep(self.INDEX_POLL_INTERVAL_SECONDS)
        return client.has_index(index_name)

    def _wait_for_index_ready(self, *, client: Pinecone, index_name: str) -> Any:
        deadline = time.monotonic() + self.INDEX_READY_TIMEOUT_SECONDS
        latest_description = client.describe_index(name=index_name)

        while time.monotonic() < deadline:
            status = self._get_attribute(latest_description, "status")
            ready = bool(self._get_attribute(status, "ready"))
            if ready:
                return latest_description

            time.sleep(self.INDEX_POLL_INTERVAL_SECONDS)
            latest_description = client.describe_index(name=index_name)

        return latest_description

    def upsert_user_embedding(
        self,
        *,
        user_id: str,
        embedding: np.ndarray,
        role: UserRole,
    ) -> None:
        try:
            index = self.ensure_index_available()
            index.upsert(
                vectors=[
                    {
                        "id": user_id,
                        "values": embedding.astype(np.float32).tolist(),
                        "metadata": {"user_id": user_id, "role": role.value},
                    }
                ],
                namespace=self.settings.pinecone_namespace,
            )
        except ApiException:
            raise
        except Exception as exc:
            raise self._translate_exception(exc) from exc

    def fetch_user_embedding(self, *, user_id: str) -> np.ndarray:
        try:
            index = self.ensure_index_available()
            response = index.fetch(
                ids=[user_id],
                namespace=self.settings.pinecone_namespace,
            )
        except ApiException:
            raise
        except Exception as exc:
            raise self._translate_exception(exc) from exc
        vectors = self._get_attribute(response, "vectors") or {}

        if isinstance(vectors, dict):
            vector_record = vectors.get(user_id)
        else:
            vector_record = getattr(vectors, user_id, None)

        if vector_record is None:
            raise ApiException(
                status_code=409,
                code="face_template_not_found",
                message="No face embedding template exists for this candidate.",
            )

        values = self._get_attribute(vector_record, "values")
        if values is None:
            raise ApiException(
                status_code=500,
                code="face_template_invalid",
                message="The stored face embedding template is unreadable.",
            )

        embedding = np.asarray(list(values), dtype=np.float32).reshape(-1)
        if embedding.shape != (512,):
            raise ApiException(
                status_code=500,
                code="face_template_invalid",
                message="The stored face embedding has an unexpected dimension.",
            )

        norm = float(np.linalg.norm(embedding))
        if norm == 0.0:
            raise ApiException(
                status_code=500,
                code="face_template_invalid",
                message="The stored face embedding template is invalid.",
            )
        return embedding / norm

    def delete_user_embedding(self, *, user_id: str) -> None:
        if not self.is_configured():
            return

        try:
            index = self.ensure_index_available()
            index.delete(ids=[user_id], namespace=self.settings.pinecone_namespace)
        except ApiException:
            raise
        except Exception as exc:
            raise self._translate_exception(exc) from exc

    def check_health(self) -> tuple[bool | None, str | None]:
        if not self.is_configured():
            return None, "Pinecone is not configured."

        try:
            self.ensure_index_available()
        except ApiException as exc:
            return False, exc.message
        except Exception:
            return False, "Unable to connect to Pinecone."
        return True, None

    def _get_client(self) -> Pinecone:
        if self._client is None:
            self._client = Pinecone(
                api_key=self.settings.pinecone_api_key,
            )
        return self._client

    def _translate_exception(self, exc: Exception) -> ApiException:
        logger.exception("Pinecone operation failed.")

        if isinstance(exc, PineconeException):
            return ApiException(
                status_code=503,
                code="pinecone_unavailable",
                message="Pinecone is unavailable right now. Please try again shortly.",
            )

        return ApiException(
            status_code=503,
            code="pinecone_unavailable",
            message="Unable to complete the Pinecone operation right now.",
        )

    @staticmethod
    def _is_index_already_exists_error(exc: Exception) -> bool:
        message = str(exc).upper()
        return "ALREADY EXISTS" in message or "ALREADY_EXISTS" in message

    @staticmethod
    def _get_attribute(value: Any, name: str) -> Any:
        if value is None:
            return None
        if isinstance(value, dict):
            return value.get(name)
        return getattr(value, name, None)

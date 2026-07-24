from __future__ import annotations

from fastapi import UploadFile

from app.api_errors import ApiException
from app.core.config import get_settings


async def read_image_upload(upload: UploadFile, *, field_label: str) -> bytes:
    image_bytes = await upload.read()
    if not image_bytes:
        raise ApiException(
            status_code=400,
            code="empty_upload",
            message=f"The {field_label} upload is empty.",
        )

    if upload.content_type and not upload.content_type.startswith("image/"):
        raise ApiException(
            status_code=415,
            code="unsupported_media_type",
            message=f"The {field_label} must be sent as an image upload.",
        )

    max_upload_bytes = get_settings().max_upload_bytes
    if len(image_bytes) > max_upload_bytes:
        raise ApiException(
            status_code=413,
            code="image_too_large",
            message=(
                f"The {field_label} is too large. Uploads must be smaller than "
                f"{max_upload_bytes // (1024 * 1024)} MB."
            ),
        )

    return image_bytes


def build_device_info(*, request_user_agent: str | None, provided_device_info: str | None) -> str | None:
    normalized_device_info = provided_device_info.strip() if provided_device_info else None
    normalized_user_agent = request_user_agent.strip() if request_user_agent else None

    if normalized_device_info and normalized_user_agent:
        return f"{normalized_device_info} | user-agent={normalized_user_agent}"
    return normalized_device_info or normalized_user_agent

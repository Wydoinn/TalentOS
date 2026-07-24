from __future__ import annotations

import hashlib
from pathlib import Path

import fitz
from docx import Document

from app.core.exceptions import ValidationException

SUPPORTED_RESUME_EXTENSIONS = (".pdf", ".docx")


def is_supported_resume_path(
    file_path: Path,
    *,
    allowed_extensions: tuple[str, ...] | None = None,
) -> bool:
    allowed = allowed_extensions or SUPPORTED_RESUME_EXTENSIONS
    return file_path.suffix.lower() in allowed


def ensure_supported_resume_path(
    file_path: Path,
    *,
    allowed_extensions: tuple[str, ...] | None = None,
) -> Path:
    if not file_path.exists():
        raise ValidationException(f"Resume file was not found: {file_path}")
    if not is_supported_resume_path(file_path, allowed_extensions=allowed_extensions):
        raise ValidationException(
            "Unsupported resume file extension "
            f"'{file_path.suffix.lower()}'. Only PDF and DOCX resumes are accepted."
        )
    return file_path


def compute_file_checksum(file_path: Path) -> str:
    supported_path = ensure_supported_resume_path(file_path)
    hasher = hashlib.sha256()
    with supported_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def extract_text_from_path(file_path: Path) -> str:
    supported_path = ensure_supported_resume_path(file_path)
    suffix = supported_path.suffix.lower()
    if suffix == ".pdf":
        with fitz.open(supported_path) as document:
            text = "\n".join(page.get_text() for page in document)
    else:
        document = Document(supported_path)
        text = "\n".join(paragraph.text for paragraph in document.paragraphs)

    cleaned = text.strip()
    if not cleaned:
        raise ValidationException("Could not extract text from the resume file")
    return cleaned

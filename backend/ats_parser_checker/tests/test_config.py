from __future__ import annotations

import pytest

from app.core.config import Settings
from app.schemas.resume_analysis import ResumeCheckRequest


def test_debug_accepts_release_string() -> None:
    settings = Settings(_env_file=None, debug="release")
    assert settings.debug is False


def test_debug_accepts_dev_string() -> None:
    settings = Settings(_env_file=None, debug="dev")
    assert settings.debug is True


def test_allowed_resume_extensions_reject_unsupported_formats() -> None:
    with pytest.raises(ValueError, match="Only PDF and DOCX"):
        Settings(_env_file=None, allowed_resume_extensions=[".pdf", ".txt"])


def test_resume_check_request_rejects_removed_retrieval_mode() -> None:
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        ResumeCheckRequest(
            job_description="Need Python, FastAPI, Neo4j, and 4 years of backend experience.",
            retrieval_mode="vector",
        )

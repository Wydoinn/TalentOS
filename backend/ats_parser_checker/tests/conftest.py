from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.models import report_run, resume_report  # noqa: F401
from app.models.candidate import Candidate
from app.models.enums import CandidateSource, IngestionStatus


def build_candidate(
    *,
    candidate_id: str,
    name: str,
    source: CandidateSource,
    summary: str,
    skills: list[str],
    experience_years: float,
    raw_text: str | None = None,
    file_path: str | None = None,
) -> Candidate:
    return Candidate(
        id=candidate_id,
        full_name=name,
        email=f"{candidate_id}@example.com",
        phone=None,
        location="Remote",
        source=source,
        availability="Immediate",
        current_title="Engineer",
        total_experience_years=experience_years,
        skills=skills,
        structured_resume={},
        summary=summary,
        raw_text=raw_text or summary,
        file_path=file_path or f"resumes/{source.value}/{candidate_id}.pdf",
        resume_checksum=f"checksum-{candidate_id}",
        ingestion_status=IngestionStatus.completed,
    )

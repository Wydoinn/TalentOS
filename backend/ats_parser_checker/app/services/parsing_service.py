from __future__ import annotations

import asyncio
from pathlib import Path

from app.models.enums import CandidateSource
from app.schemas.ingestion import StructuredResume
from app.utils.documents import extract_text_from_path
from app.utils.resume_parser import parse_resume_text


class ResumeParsingService:
    async def extract_text(self, file_path: Path) -> str:
        return await asyncio.to_thread(extract_text_from_path, file_path)

    async def parse(
        self,
        *,
        raw_text: str,
        source: CandidateSource,
        availability: str | None = None,
        location: str | None = None,
    ) -> StructuredResume:
        return await asyncio.to_thread(
            parse_resume_text,
            raw_text,
            source=source,
            availability=availability,
            location=location,
        )

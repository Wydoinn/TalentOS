from __future__ import annotations

import fitz
import pytest

from app.core.exceptions import ValidationException
from app.utils.ats import inspect_resume_format
from app.utils.documents import ensure_supported_resume_path, is_supported_resume_path


def test_resume_helpers_only_accept_pdf_and_docx(tmp_path) -> None:
    pdf_path = tmp_path / "resume.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")
    docx_path = tmp_path / "resume.docx"
    docx_path.write_bytes(b"placeholder")
    text_path = tmp_path / "notes.txt"
    text_path.write_text("not a resume", encoding="utf-8")

    assert is_supported_resume_path(pdf_path)
    assert is_supported_resume_path(docx_path)
    assert not is_supported_resume_path(text_path)
    assert ensure_supported_resume_path(pdf_path) == pdf_path

    with pytest.raises(ValidationException, match="Only PDF and DOCX"):
        ensure_supported_resume_path(text_path)

    with pytest.raises(ValidationException, match="Only PDF and DOCX"):
        inspect_resume_format(text_path)


def test_inspect_resume_format_uses_builtin_pdf_heuristics(tmp_path) -> None:
    pdf_path = tmp_path / "resume.pdf"
    document = fitz.open()
    page = document.new_page(width=600, height=800)
    page.insert_text((36, 72), "Column one")
    page.insert_text((340, 72), "Column two")
    page.draw_rect(fitz.Rect(48, 220, 552, 360), color=(0, 0, 0), width=1)
    page.draw_line(fitz.Point(48, 260), fitz.Point(552, 260), color=(0, 0, 0), width=1)
    page.draw_line(fitz.Point(48, 300), fitz.Point(552, 300), color=(0, 0, 0), width=1)
    page.insert_text((60, 245), "Skill")
    page.insert_text((220, 245), "Level")
    page.insert_text((380, 245), "Years")
    page.insert_text((60, 285), "Python")
    page.insert_text((220, 285), "Advanced")
    page.insert_text((380, 285), "5")
    document.save(pdf_path)
    document.close()

    score, issues, signals = inspect_resume_format(pdf_path)

    assert score < 1.0
    assert signals["layout_engine"] == "heuristic_builtin"
    assert signals["possible_multi_column"] is True
    assert signals["tables_detected"] >= 1
    assert "Table-based layout detected and may parse inconsistently." in issues
    assert "Possible multi-column layout detected." in issues


def test_inspect_resume_format_handles_plain_pdf_without_layout_runtime(tmp_path) -> None:
    pdf_path = tmp_path / "resume.pdf"
    document = fitz.open()
    page = document.new_page(width=600, height=800)
    page.insert_text((36, 72), "Single column content")
    page.insert_text((36, 108), "Professional summary with experience.")
    document.save(pdf_path)
    document.close()

    score, issues, signals = inspect_resume_format(pdf_path)

    assert 0.0 <= score <= 1.0
    assert isinstance(issues, list)
    assert signals["layout_engine"] == "heuristic_builtin"

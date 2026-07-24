from __future__ import annotations

import logging
import re
from collections import Counter
from pathlib import Path
from typing import Any

import fitz
from docx import Document

from app.core.ats_rules import get_ats_rules
from app.schemas.ingestion import StructuredResume
from app.utils.documents import ensure_supported_resume_path
from app.utils.scoring import clamp01
from app.utils.text import extract_required_skills

logger = logging.getLogger(__name__)

_RULES = get_ats_rules()
_ATS_SCORING_RULES = _RULES["ats_scoring"]
_QUALITY_RULES = _ATS_SCORING_RULES["quality"]
_QUALITY_WEIGHTS = _QUALITY_RULES["weights"]
_QUALITY_SUMMARY_THRESHOLDS = _QUALITY_RULES["summary_thresholds"]
_FORMAT_RULES = _ATS_SCORING_RULES["formatting"]
_EXPERIENCE_HINTS = [
    (item["pattern"], float(item["years"]))
    for item in _ATS_SCORING_RULES["requested_experience_hints"]
]
_EXPERIENCE_RELEVANCE_WEIGHTS = _ATS_SCORING_RULES["experience_relevance_weights"]


def section_status(structured_resume: StructuredResume) -> dict[str, bool]:
    return {
        "skills": bool(structured_resume.skills),
        "experience": bool(structured_resume.experience),
        "projects": bool(structured_resume.projects),
        "education": bool(structured_resume.education),
    }


def section_completeness_score(sections: dict[str, bool]) -> float:
    if not sections:
        return 0.0
    return round(sum(1 for value in sections.values() if value) / len(sections), 4)


def keyword_scores(
    *,
    job_description: str,
    candidate_skills: list[str],
) -> tuple[float, list[str], list[str]]:
    required_keywords = extract_required_skills(job_description)
    if not required_keywords:
        return 0.0, [], []

    required_lookup = {item.lower(): item for item in required_keywords}
    candidate_lookup = {item.lower(): item for item in candidate_skills}
    matched = sorted(required_lookup[key] for key in required_lookup if key in candidate_lookup)
    missing = sorted(required_lookup[key] for key in required_lookup if key not in candidate_lookup)
    score = round(len(matched) / max(len(required_lookup), 1), 4)
    return score, matched, missing


def requested_experience_years(job_description: str) -> float | None:
    normalized = job_description.lower()
    matches = [
        float(match)
        for match in re.findall(
            r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years|yrs)",
            normalized,
        )
    ]
    if matches:
        return max(matches)

    for pattern, years in _EXPERIENCE_HINTS:
        if re.search(pattern, normalized):
            return years
    return None


def experience_relevance_score(
    *,
    candidate_years: float,
    requested_years: float | None,
    keyword_score_value: float,
) -> float:
    if requested_years is None or requested_years <= 0:
        return round(keyword_score_value, 4)
    years_score = clamp01(candidate_years / requested_years)
    return round(
        (
            keyword_score_value * _EXPERIENCE_RELEVANCE_WEIGHTS["keyword"]
            + years_score * _EXPERIENCE_RELEVANCE_WEIGHTS["years"]
        ),
        4,
    )


def heuristic_quality_score(
    *,
    raw_text: str,
    structured_resume: StructuredResume,
    formatting_score_value: float,
    completeness_score_value: float,
) -> tuple[float, list[str], list[str], str]:
    issues: list[str] = []
    suggestions: list[str] = []

    word_count = len(re.findall(r"\w+", raw_text))
    quantified_impact = len(re.findall(r"\b\d+(?:\.\d+)?%|\b\d+\+?\b", raw_text))
    has_links = bool(structured_resume.links)
    skills_count = len(structured_resume.skills)

    length_score = (
        1.0
        if _QUALITY_RULES["ideal_word_count_min"] <= word_count <= _QUALITY_RULES["ideal_word_count_max"]
        else _QUALITY_RULES["acceptable_length_score"]
        if _QUALITY_RULES["acceptable_word_count_min"] <= word_count <= _QUALITY_RULES["acceptable_word_count_max"]
        else _QUALITY_RULES["outside_length_score"]
    )
    impact_score = clamp01(quantified_impact / _QUALITY_RULES["impact_target_count"])
    profile_score = (
        1.0
        if skills_count >= _QUALITY_RULES["profile_target_skills"]
        else clamp01(skills_count / _QUALITY_RULES["profile_target_skills"])
    )
    link_score = 1.0 if has_links else _QUALITY_RULES["missing_links_score"]

    score = round(
        (
            formatting_score_value * _QUALITY_WEIGHTS["formatting"]
            + completeness_score_value * _QUALITY_WEIGHTS["completeness"]
            + length_score * _QUALITY_WEIGHTS["length"]
            + impact_score * _QUALITY_WEIGHTS["impact"]
            + profile_score * _QUALITY_WEIGHTS["profile"]
            + link_score * _QUALITY_WEIGHTS["links"]
        ),
        4,
    )

    if word_count < _QUALITY_RULES["ideal_word_count_min"]:
        issues.append("Resume looks too short for a strong ATS profile.")
        suggestions.append("Add more experience detail, project context, and measurable impact.")
    if quantified_impact == 0:
        issues.append("Quantified achievements are missing or very limited.")
        suggestions.append("Add metrics such as percentages, volumes, or delivery outcomes.")
    if not structured_resume.projects:
        issues.append("Projects section is missing or too thin.")
        suggestions.append("Include relevant projects that reinforce role alignment.")
    if not has_links:
        suggestions.append("Add relevant links such as LinkedIn or GitHub if available.")

    summary = (
        "Resume quality looks strong for ATS review."
        if score >= _QUALITY_SUMMARY_THRESHOLDS["strong"]
        else "Resume quality is workable but has clear ATS improvement opportunities."
        if score >= _QUALITY_SUMMARY_THRESHOLDS["workable"]
        else "Resume needs meaningful ATS-focused improvements before matching."
    )
    return score, issues, suggestions, summary


def inspect_resume_format(file_path: Path) -> tuple[float, list[str], dict[str, Any]]:
    supported_path = ensure_supported_resume_path(file_path)
    suffix = supported_path.suffix.lower()
    signals: dict[str, Any] = {
        "file_type": suffix,
        "layout_engine": "heuristic_builtin",
        "images_detected": 0,
        "tables_detected": 0,
        "possible_multi_column": False,
        "repeated_headers_or_footers": False,
    }
    issues: list[str] = []

    if suffix == ".pdf":
        _inspect_pdf(supported_path, issues, signals)
    else:
        _inspect_docx(supported_path, issues, signals)

    penalties = (
        min(signals["images_detected"], _FORMAT_RULES["max_images_penalized"]) * _FORMAT_RULES["image_penalty"]
        + min(signals["tables_detected"], _FORMAT_RULES["max_tables_penalized"]) * _FORMAT_RULES["table_penalty"]
        + (_FORMAT_RULES["multi_column_penalty"] if signals["possible_multi_column"] else 0.0)
        + (_FORMAT_RULES["repeated_banner_penalty"] if signals["repeated_headers_or_footers"] else 0.0)
    )
    return round(clamp01(1.0 - penalties), 4), issues, signals


def _inspect_pdf(file_path: Path, issues: list[str], signals: dict[str, Any]) -> None:
    with fitz.open(file_path) as document:
        repeated_top_lines: list[str] = []
        repeated_bottom_lines: list[str] = []

        for page in document:
            signals["images_detected"] += len(page.get_images(full=True))
            signals["tables_detected"] += _count_tables(page)
            text_blocks = _text_blocks(page)
            if _looks_multi_column(text_blocks, page.rect.width):
                signals["possible_multi_column"] = True

            page_text = page.get_text("text").splitlines()
            cleaned_lines = [line.strip() for line in page_text if line.strip()]
            if cleaned_lines:
                repeated_top_lines.append(cleaned_lines[0][:80])
                repeated_bottom_lines.append(cleaned_lines[-1][:80])

        if _has_repeated_banner(repeated_top_lines) or _has_repeated_banner(repeated_bottom_lines):
            signals["repeated_headers_or_footers"] = True

    if signals["images_detected"]:
        issues.append("Embedded images may reduce ATS readability.")
    if signals["tables_detected"]:
        issues.append("Table-based layout detected and may parse inconsistently.")
    if signals["possible_multi_column"]:
        issues.append("Possible multi-column layout detected.")
    if signals["repeated_headers_or_footers"]:
        issues.append("Repeated header or footer text detected across pages.")


def _inspect_docx(file_path: Path, issues: list[str], signals: dict[str, Any]) -> None:
    document = Document(file_path)
    signals["tables_detected"] = len(document.tables)
    signals["images_detected"] = len(getattr(document, "inline_shapes", []))
    if signals["tables_detected"]:
        issues.append("Table-based layout detected and may parse inconsistently.")
    if signals["images_detected"]:
        issues.append("Embedded images may reduce ATS readability.")


def _count_tables(page: fitz.Page) -> int:
    drawing_score = _table_like_drawing_score(page)
    text_score = _table_like_text_score(page)
    return 1 if drawing_score >= 4 or text_score >= 3 else 0


def _text_blocks(page: fitz.Page) -> list[tuple[float, float, float, float]]:
    blocks = []
    for item in page.get_text("blocks"):
        if len(item) >= 7 and item[6] == 0:
            blocks.append((float(item[0]), float(item[1]), float(item[2]), float(item[3])))
    return blocks


def _looks_multi_column(blocks: list[tuple[float, float, float, float]], page_width: float) -> bool:
    if not blocks:
        return False
    midline = page_width / 2
    left_blocks = [
        block
        for block in blocks
        if block[0] < midline * _FORMAT_RULES["multi_column_left_start_ratio"]
        and block[2] <= midline * _FORMAT_RULES["multi_column_left_end_ratio"]
    ]
    right_blocks = [
        block
        for block in blocks
        if block[0] >= midline * _FORMAT_RULES["multi_column_right_start_ratio"]
    ]
    return bool(left_blocks and right_blocks)


def _has_repeated_banner(lines: list[str]) -> bool:
    if len(lines) < 2:
        return False
    counts = Counter(line for line in lines if line)
    return any(count > 1 for count in counts.values())

def _table_like_drawing_score(page: fitz.Page) -> int:
    try:
        drawings = page.get_drawings()
    except Exception as exc:  # pragma: no cover - defensive runtime fallback
        logger.debug("Unable to inspect page drawings for table detection: %s", exc)
        return 0

    line_like = 0
    rectangle_like = 0
    for drawing in drawings:
        if drawing.get("type") == "s":
            line_like += 1
        if drawing.get("rect") is not None:
            rectangle_like += 1

    return min(line_like, 4) + min(rectangle_like, 2)


def _table_like_text_score(page: fitz.Page) -> int:
    try:
        words = page.get_text("words")
    except Exception as exc:  # pragma: no cover - defensive runtime fallback
        logger.debug("Unable to inspect page words for table detection: %s", exc)
        return 0

    rows: dict[int, list[tuple[float, float]]] = {}
    for word in words:
        if len(word) < 5:
            continue
        x0, y0, x1, y1 = float(word[0]), float(word[1]), float(word[2]), float(word[3])
        row_key = int(round(((y0 + y1) / 2) / 10.0))
        rows.setdefault(row_key, []).append((x0, x1))

    aligned_rows = 0
    previous_signature: tuple[int, ...] | None = None
    for entries in rows.values():
        if len(entries) < 3:
            continue

        signature = tuple(
            sorted({int(start // 72) for start, _ in entries})
        )
        if len(signature) < 3:
            continue

        if previous_signature is None or signature == previous_signature:
            aligned_rows += 1
            previous_signature = signature

    return aligned_rows

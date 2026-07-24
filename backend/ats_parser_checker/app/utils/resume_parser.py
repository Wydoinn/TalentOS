from __future__ import annotations

import math
import re
from datetime import datetime

from app.core.ats_rules import get_ats_rules
from app.models.enums import CandidateSource
from app.schemas.ingestion import (
    EducationRecord,
    ExperienceRecord,
    ProjectRecord,
    StructuredResume,
)
from app.utils.text import build_search_document, extract_skills, normalize_text, split_sections

_RULES = get_ats_rules()
_PARSER_RULES = _RULES["resume_parser"]
_PARSING_QUALITY_WEIGHTS = _PARSER_RULES["parsing_quality_weights"]
_DEGREE_PATTERN = "|".join(_PARSER_RULES["degree_patterns"])
_PROJECT_TECH_MARKER_PATTERN = "|".join(
    re.escape(marker) for marker in _PARSER_RULES["project_technology_markers"]
)

MONTH_LOOKUP = {key: int(value) for key, value in _PARSER_RULES["month_lookup"].items()}
ROLE_KEYWORDS = set(_PARSER_RULES["role_keywords"])
SECTION_TOKENS = set(_PARSER_RULES["section_tokens"])
CONTACT_MARKERS = tuple(_PARSER_RULES["contact_markers"])
LOCATION_MARKERS = tuple(_PARSER_RULES["location_markers"])
DATE_RANGE_PATTERN = re.compile(_PARSER_RULES["date_range_pattern"], re.IGNORECASE)
EXPERIENCE_ACTION_VERBS = set(_PARSER_RULES["experience_action_verbs"])
COMPANY_HINT_TOKENS = set(_PARSER_RULES["company_hint_tokens"])


def _clean_line(value: str) -> str:
    cleaned = re.sub(r"^[^\w(+]+", "", value.strip())
    cleaned = cleaned.strip(" |")
    return re.sub(r"\s+", " ", cleaned).strip()


def _normalize_display_text(value: str) -> str:
    cleaned = _clean_line(value)
    if cleaned.isupper() and re.search(r"[A-Z]", cleaned):
        return cleaned.title()
    return cleaned


def _normalized_token_set(value: str) -> set[str]:
    return set(re.findall(r"[a-z]+", value.lower()))


def _is_section_header(line: str) -> bool:
    lowered = re.sub(r"[^a-z ]", "", line.lower()).strip()
    return lowered in SECTION_TOKENS


def _is_contact_line(line: str) -> bool:
    lowered = line.lower()
    return any(marker in lowered for marker in CONTACT_MARKERS) or bool(
        re.search(r"\+?\d[\d\s().-]{8,}\d", line)
    )


def _looks_like_job_title(line: str) -> bool:
    tokens = _normalized_token_set(line)
    if not tokens or _is_section_header(line) or _is_contact_line(line):
        return False
    return bool(tokens & ROLE_KEYWORDS)


def _looks_like_person_name(line: str) -> bool:
    cleaned = _clean_line(line)
    if not cleaned or _is_section_header(cleaned) or _is_contact_line(cleaned):
        return False
    if re.search(r"\d", cleaned):
        return False

    words = re.findall(r"[A-Za-z][A-Za-z'.-]*", cleaned)
    if not (
        _PARSER_RULES["person_name_min_words"]
        <= len(words)
        <= _PARSER_RULES["person_name_max_words"]
    ):
        return False

    tokens = _normalized_token_set(cleaned)
    if tokens & ROLE_KEYWORDS:
        return False

    uppercase_ratio = sum(word[0].isupper() for word in words) / len(words)
    return uppercase_ratio >= _PARSER_RULES["person_name_uppercase_ratio"]


def _header_lines(lines: list[str]) -> list[str]:
    collected: list[str] = []
    for line in lines[: _PARSER_RULES["header_scan_limit"]]:
        if _is_section_header(line):
            break
        cleaned = _clean_line(line)
        if cleaned:
            collected.append(cleaned)
    return collected


def _extract_name(lines: list[str]) -> str:
    header_lines = _header_lines(lines)
    for line in header_lines:
        if _looks_like_person_name(line):
            return _normalize_display_text(line)

    for line in lines[: _PARSER_RULES["name_fallback_scan_limit"]]:
        candidate = _clean_line(line)
        if "@" in candidate or len(candidate.split()) < 2 or len(candidate.split()) > 5:
            continue
        if re.search(r"\d", candidate):
            continue
        if candidate.lower() in {"resume", "curriculum vitae"}:
            continue
        if _looks_like_job_title(candidate):
            continue
        return _normalize_display_text(candidate)
    return "Unknown Candidate"


def _extract_header_title(lines: list[str]) -> str | None:
    for line in _header_lines(lines):
        if _looks_like_job_title(line):
            return _normalize_display_text(line)
    return None


def _extract_email(text: str) -> str | None:
    match = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
    return match.group(0) if match else None


def _extract_phone(text: str) -> str | None:
    match = re.search(r"(\+?\d[\d\s().-]{8,}\d)", text)
    return match.group(1).strip() if match else None


def _normalize_link(value: str) -> str:
    cleaned = value.strip().rstrip(".,;|")
    if not re.match(r"^https?://", cleaned, re.IGNORECASE):
        return f"https://{cleaned}"
    return cleaned


def _extract_links(text: str) -> dict[str, str]:
    links: dict[str, str] = {}
    linkedin = re.search(
        r"((?:https?://)?(?:www\.)?linkedin\.com/[^\s|]+)",
        text,
        re.IGNORECASE,
    )
    github = re.search(
        r"((?:https?://)?(?:www\.)?github\.com/[^\s|]+)",
        text,
        re.IGNORECASE,
    )
    if linkedin:
        links["linkedin"] = _normalize_link(linkedin.group(1))
    if github:
        links["github"] = _normalize_link(github.group(1))
    return links


def _clean_location(value: str) -> str:
    cleaned = _clean_line(value)
    cleaned = re.sub(r"^(?:location|based in)\s*[:\-]\s*", "", cleaned, flags=re.IGNORECASE)
    return cleaned


def _extract_location(text: str, override: str | None) -> str | None:
    if override:
        return _clean_location(override)

    match = re.search(r"(?im)^(?:location|based in)\s*[:\-]\s*([^\n]+)$", text)
    if match:
        return _clean_location(match.group(1))

    for line in text.splitlines()[: _PARSER_RULES["location_scan_limit"]]:
        cleaned = _clean_location(line)
        lowered = cleaned.lower()
        if (
            "," in cleaned
            and len(cleaned.split()) <= _PARSER_RULES["location_comma_word_limit"]
            and not _is_contact_line(cleaned)
        ):
            return cleaned
        if any(marker in lowered for marker in LOCATION_MARKERS) and not _is_contact_line(cleaned):
            return cleaned
    return None


def _extract_chunks(section_text: str) -> list[list[str]]:
    chunks: list[list[str]] = []
    current: list[str] = []

    for line in section_text.splitlines():
        cleaned = line.strip()
        if not cleaned:
            if current:
                chunks.append(current)
                current = []
            continue
        current.append(_clean_line(cleaned.lstrip("-* ")))
    if current:
        chunks.append(current)
    return chunks


def _split_header_components(value: str) -> list[str]:
    cleaned = _clean_line(value)
    if not cleaned:
        return []
    separators = (r"\s+\|\s+", r"\s+@\s+", r"\s+at\s+")
    parts = [cleaned]
    for separator in separators:
        if len(parts) == 1:
            parts = re.split(separator, cleaned, maxsplit=1, flags=re.IGNORECASE)
    return [_normalize_display_text(part) for part in parts if part and part.strip()]


def _is_description_like_line(line: str) -> bool:
    cleaned = _clean_line(line)
    if not cleaned:
        return False
    lowered = cleaned.lower()
    words = re.findall(r"[A-Za-z0-9&.+'-]+", cleaned)
    if not words:
        return False
    if cleaned.endswith(".") or len(words) > _PARSER_RULES["description_word_threshold"]:
        return True
    if lowered.split()[0] in EXPERIENCE_ACTION_VERBS:
        return True
    if re.search(r"[,:;]", cleaned):
        return True
    if re.search(r"\b(using|with|for|through|across|into)\b", lowered) and len(words) >= _PARSER_RULES["description_preposition_word_threshold"]:
        return True
    return False


def _looks_like_company_name(line: str) -> bool:
    cleaned = _normalize_display_text(line)
    if (
        not cleaned
        or _is_section_header(cleaned)
        or _is_contact_line(cleaned)
        or DATE_RANGE_PATTERN.search(cleaned)
        or _is_description_like_line(cleaned)
    ):
        return False

    words = re.findall(r"[A-Za-z0-9&.+'-]+", cleaned)
    if not 1 <= len(words) <= _PARSER_RULES["company_word_limit"]:
        return False

    lowered_tokens = {word.lower() for word in words}
    if lowered_tokens & EXPERIENCE_ACTION_VERBS:
        return False
    if lowered_tokens & COMPANY_HINT_TOKENS:
        return True

    uppercase_ratio = sum(word[:1].isupper() or word.isupper() for word in words) / len(words)
    return uppercase_ratio >= _PARSER_RULES["company_uppercase_ratio"]


def _extract_title_company_and_dates(chunk: list[str]) -> tuple[str, str | None, str | None, str | None]:
    combined = " | ".join(chunk)
    date_match = DATE_RANGE_PATTERN.search(combined)
    start_date = None
    end_date = None
    raw_range = None
    if date_match:
        raw_range = date_match.group(1)
        parts = re.split(r"\s*-\s*", raw_range)
        if len(parts) == 2:
            start_date, end_date = parts

    header_candidates = list(chunk[: _PARSER_RULES["title_company_header_scan_limit"]])
    title: str | None = None
    company: str | None = None
    for line in header_candidates:
        cleaned_line = line.replace(raw_range or "", "").strip(" |-")
        components = _split_header_components(cleaned_line)
        if components and title is None:
            if len(components) >= 2:
                left = components[0]
                right = components[1]
                if _looks_like_job_title(left) and _looks_like_company_name(right):
                    title = left
                    company = right
                    continue
                if _looks_like_company_name(left) and _looks_like_job_title(right):
                    company = left
                    title = right
                    continue
            title = components[0]
            if len(components) > 1 and _looks_like_company_name(components[1]):
                company = components[1]
        elif line and company is None and _looks_like_company_name(line):
            company = _normalize_display_text(line)

    return (
        title or _normalize_display_text(chunk[0]),
        company,
        start_date,
        end_date,
    )


def _extract_project_chunks(projects_text: str) -> list[list[str]]:
    chunks: list[list[str]] = []
    current: list[str] = []

    for raw_line in projects_text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            if current:
                chunks.append(current)
                current = []
            continue

        cleaned = _clean_line(stripped)
        is_bullet = stripped.lstrip().startswith(("-", "*"))
        is_tech_stack_line = bool(
            re.search(rf"(?i)^(?:{_PROJECT_TECH_MARKER_PATTERN})\s*[:\-]", cleaned)
        )
        if not is_bullet and not is_tech_stack_line:
            if current:
                chunks.append(current)
            current = [cleaned]
            continue

        if not current:
            current = [cleaned]
            continue
        current.append(cleaned)

    if current:
        chunks.append(current)
    return [chunk for chunk in chunks if chunk]


def _extract_project_technologies(chunk: list[str]) -> list[str]:
    explicit_fragments: list[str] = []
    for line in chunk[1:]:
        match = re.search(
            rf"(?i)(?:{_PROJECT_TECH_MARKER_PATTERN})\s*[:\-]\s*(.+)$",
            line,
        )
        if match:
            explicit_fragments.append(match.group(1))
    combined = "\n".join(chunk + explicit_fragments)
    return extract_skills(combined)


def _parse_date_token(value: str) -> datetime | None:
    lowered = value.strip().lower()
    if lowered in set(_PARSER_RULES["present_tokens"]):
        return datetime.utcnow()

    month_match = re.match(r"([a-z]{3,9})\s+(\d{4})", lowered)
    if month_match:
        month = MONTH_LOOKUP.get(month_match.group(1)[:3])
        year = int(month_match.group(2))
        if month:
            return datetime(year, month, 1)

    year_match = re.match(r"(\d{4})", lowered)
    if year_match:
        return datetime(int(year_match.group(1)), 1, 1)
    return None


def _extract_total_experience_years(
    experience_text: str,
    entries: list[ExperienceRecord],
) -> float:
    explicit = re.search(r"(\d+(?:\.\d+)?)\+?\s+years", experience_text.lower())
    if explicit:
        return round(float(explicit.group(1)), 2)

    total_months = 0
    for entry in entries:
        if not entry.start_date:
            continue
        start = _parse_date_token(entry.start_date)
        end = _parse_date_token(entry.end_date or "present")
        if not start or not end or end < start:
            continue
        total_months += max(1, (end.year - start.year) * 12 + (end.month - start.month))

    years = total_months / 12
    return round(years, 2) if years else 0.0


def _extract_experience(experience_text: str) -> list[ExperienceRecord]:
    if not experience_text.strip():
        return []

    chunks = _extract_chunks(experience_text)
    experiences: list[ExperienceRecord] = []

    for chunk in chunks[: _PARSER_RULES["experience_entry_limit"]]:
        if not chunk or _is_section_header(chunk[0]):
            continue

        title, company, start_date, end_date = _extract_title_company_and_dates(chunk)
        summary_offset = 2 if company else 1
        summary_lines = [
            line
            for line in chunk[summary_offset:]
            if not DATE_RANGE_PATTERN.search(line)
        ]
        if not company and len(chunk) > 1 and not summary_lines:
            summary_lines = chunk[1:]

        experiences.append(
            ExperienceRecord(
                title=title,
                company=company,
                start_date=start_date,
                end_date=end_date,
                summary=" ".join(summary_lines)[: _PARSER_RULES["experience_summary_character_limit"]] or None,
            )
        )
    return experiences


def _extract_education(education_text: str) -> list[EducationRecord]:
    records: list[EducationRecord] = []
    for chunk in _extract_chunks(education_text)[: _PARSER_RULES["education_entry_limit"]]:
        if not chunk:
            continue

        first_line = _normalize_display_text(chunk[0])
        second_line = _normalize_display_text(chunk[1]) if len(chunk) > 1 else None
        first_is_degree = bool(
            re.search(
                rf"({_DEGREE_PATTERN})",
                first_line,
                re.IGNORECASE,
            )
        )
        institution = second_line if first_is_degree and second_line else first_line
        details = " ".join(chunk[2:] if first_is_degree and second_line else chunk[1:])
        year_match = re.search(r"(20\d{2}|19\d{2})", details)
        degree_match = re.search(
            rf"({_DEGREE_PATTERN})",
            first_line if first_is_degree else details,
            re.IGNORECASE,
        )
        records.append(
            EducationRecord(
                institution=institution,
                degree=degree_match.group(1) if degree_match else None,
                graduation_year=year_match.group(1) if year_match else None,
                field_of_study=details[:120] or None,
            )
        )
    return records


def _extract_projects(projects_text: str) -> list[ProjectRecord]:
    if not projects_text.strip():
        return []

    projects: list[ProjectRecord] = []
    for chunk in _extract_project_chunks(projects_text)[: _PARSER_RULES["project_entry_limit"]]:
        name = _normalize_display_text(chunk[0])
        summary_lines = [
            line
            for line in chunk[1:]
            if not re.search(rf"(?i)(?:{_PROJECT_TECH_MARKER_PATTERN})\s*[:\-]\s*", line)
        ]
        summary = (
            " ".join(summary_lines)[: _PARSER_RULES["project_summary_character_limit"]]
            if summary_lines
            else None
        )
        technologies = _extract_project_technologies(chunk)
        projects.append(
            ProjectRecord(
                name=name,
                summary=summary,
                technologies=technologies,
            )
        )
    return projects


def _parsing_quality_assessment(
    *,
    normalized_text: str,
    sections: dict[str, str],
    structured: StructuredResume,
) -> tuple[float, list[str]]:
    warnings: list[str] = []
    score = 0.0

    if structured.name and structured.name != "Unknown Candidate":
        score += _PARSING_QUALITY_WEIGHTS["name"]
    else:
        warnings.append("Candidate name could not be extracted confidently.")

    if structured.email or structured.phone:
        score += _PARSING_QUALITY_WEIGHTS["contact"]
    else:
        warnings.append("Contact details look incomplete in the parsed resume.")

    if structured.current_title:
        score += _PARSING_QUALITY_WEIGHTS["current_title"]
    else:
        warnings.append("Current role title was not parsed clearly.")

    if len(structured.skills) >= _PARSER_RULES["skills_strong_threshold"]:
        score += _PARSING_QUALITY_WEIGHTS["skills_strong"]
    elif structured.skills:
        score += _PARSING_QUALITY_WEIGHTS["skills_partial"]
        warnings.append("Only a small skill set was extracted; review the skills section.")
    else:
        warnings.append("No reliable skills were extracted from the resume.")

    if structured.experience:
        score += _PARSING_QUALITY_WEIGHTS["experience_structured"]
    elif structured.total_experience_years > 0:
        score += _PARSING_QUALITY_WEIGHTS["experience_inferred"]
        warnings.append("Experience years were inferred, but structured experience entries are thin.")
    else:
        warnings.append("Experience records were not parsed into structured entries.")

    if structured.projects:
        score += _PARSING_QUALITY_WEIGHTS["projects"]
    elif sections.get("projects"):
        warnings.append("Project section exists, but project entries were not parsed cleanly.")

    if structured.education:
        score += _PARSING_QUALITY_WEIGHTS["education"]

    if structured.links or structured.location:
        score += _PARSING_QUALITY_WEIGHTS["links_or_location"]

    if sections:
        score += _PARSING_QUALITY_WEIGHTS["sections"]
    else:
        warnings.append("Section headers were not detected, which can reduce parsing quality.")

    if normalized_text.count("\n") < _PARSER_RULES["minimum_line_breaks"]:
        warnings.append("Resume text is very compressed, which can hurt section-based parsing.")

    return round(min(score, 1.0), 4), warnings


def parse_resume_text(
    text: str,
    *,
    source: CandidateSource,
    availability: str | None = None,
    location: str | None = None,
) -> StructuredResume:
    normalized = normalize_text(text)
    lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    sections = split_sections(normalized)
    current_title = _extract_header_title(lines)

    experience = _extract_experience(sections.get("experience", ""))
    education = _extract_education(sections.get("education", ""))
    projects = _extract_projects(sections.get("projects", ""))
    skills = extract_skills(f"{normalized}\n{sections.get('skills', '')}")
    total_experience_years = _extract_total_experience_years(
        sections.get("experience", normalized),
        experience,
    )

    structured = StructuredResume(
        name=_extract_name(lines),
        email=_extract_email(normalized),
        phone=_extract_phone(normalized),
        location=_extract_location(normalized, location),
        current_title=current_title or (experience[0].title if experience else None),
        skills=skills,
        experience=experience,
        education=education,
        projects=projects,
        total_experience_years=(
            0.0 if math.isnan(total_experience_years) else total_experience_years
        ),
        links=_extract_links(normalized),
        availability=availability,
        source=source,
        parsing_quality_score=1.0,
        parsing_warnings=[],
        summary="",
    )
    parsing_quality_score, parsing_warnings = _parsing_quality_assessment(
        normalized_text=normalized,
        sections=sections,
        structured=structured,
    )
    structured.parsing_quality_score = parsing_quality_score
    structured.parsing_warnings = parsing_warnings
    structured.summary = build_search_document(structured.model_dump())
    return structured

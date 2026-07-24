from __future__ import annotations

import re
from typing import Any

from app.core.ats_rules import get_ats_rules
from app.utils.skill_catalog import SKILL_ALIASES

COMMON_TEXT_REPLACEMENTS = {
    "\x00": " ",
    "\u00a0": " ",
    "Ã¢â‚¬Â¢": " - ",
    "â€¢": " - ",
    "•": " - ",
    "Ã¢â‚¬â€œ": "-",
    "â€“": "-",
    "–": "-",
    "â€”": "-",
    "—": "-",
    "ðŸ“": " ",
    "ðŸ“ž": " ",
    "ðŸ“§": " ",
    "ðŸ”—": " ",
}

_RULES = get_ats_rules()

SECTION_HEADERS = {
    section_name: set(aliases)
    for section_name, aliases in _RULES["section_headers"].items()
}


def normalize_text(text: str) -> str:
    normalized = text
    for source, replacement in COMMON_TEXT_REPLACEMENTS.items():
        normalized = normalized.replace(source, replacement)
    normalized = re.sub(r"\r\n?", "\n", normalized)
    normalized = re.sub(r"[ \t]+", " ", normalized)
    return re.sub(r"\n{3,}", "\n\n", normalized).strip()


def split_sections(text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {key: [] for key in SECTION_HEADERS}
    current_section: str | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            if current_section and sections[current_section]:
                sections[current_section].append("")
            continue

        lowered = re.sub(r"[^a-z ]", "", line.lower()).strip()
        matched_section = None
        for section_name, aliases in SECTION_HEADERS.items():
            if lowered in aliases:
                matched_section = section_name
                break
        if matched_section:
            current_section = matched_section
            continue
        if current_section:
            sections[current_section].append(line)

    return {
        key: "\n".join(lines).strip()
        for key, lines in sections.items()
        if any(item.strip() for item in lines)
    }


def extract_skills(text: str) -> list[str]:
    haystack = normalize_text(text).lower()
    extracted: list[str] = []
    for canonical, aliases in SKILL_ALIASES.items():
        if any(_contains_alias(haystack, alias) for alias in aliases):
            extracted.append(canonical)
    return sorted(set(extracted))


def extract_required_skills(job_description: str) -> list[str]:
    sections = split_sections(job_description)
    skills_text = sections.get("skills", "")
    return extract_skills(f"{job_description}\n{skills_text}")


def build_search_document(structured_resume: dict[str, Any]) -> str:
    experience_fragments = [
        _format_experience_fragment(item)
        for item in structured_resume.get("experience", [])[:3]
    ]
    projects = [
        _format_project_fragment(project)
        for project in structured_resume.get("projects", [])[:2]
    ]
    skills = ", ".join(structured_resume.get("skills", []))
    fragments = [
        f"Candidate {structured_resume.get('name', 'Unknown')}",
        f"Current title {structured_resume.get('current_title', 'Professional')}",
        f"Experience {structured_resume.get('total_experience_years', 0)} years",
        f"Skills {skills}",
        f"Location {_clean_fragment(structured_resume.get('location', 'Unknown'))}",
    ]
    if any(experience_fragments):
        fragments.append("Experience highlights " + "; ".join(experience_fragments))
    if any(projects):
        fragments.append("Project highlights " + "; ".join(projects))
    return ". ".join(fragment for fragment in fragments if fragment).strip()


def _contains_alias(haystack: str, alias: str) -> bool:
    normalized_alias = normalize_text(alias).lower().strip()
    if not normalized_alias:
        return False
    escaped_alias = re.escape(normalized_alias).replace(r"\ ", r"\s+")
    pattern = re.compile(
        rf"(?<![a-z0-9]){escaped_alias}(?![a-z0-9])",
        re.IGNORECASE,
    )
    return bool(pattern.search(haystack))


def _clean_fragment(value: Any) -> str:
    if value is None:
        return "Unknown"
    text = str(value).strip()
    text = re.sub(r"^[^\w(+-]+", "", text)
    return re.sub(r"\s+", " ", text).strip() or "Unknown"


def _format_experience_fragment(item: dict[str, Any]) -> str:
    title = _clean_fragment(item.get("title"))
    company = _clean_fragment(item.get("company")) if item.get("company") else ""
    if company and company != "Unknown":
        return f"{title} at {company}"
    return title


def _format_project_fragment(project: dict[str, Any]) -> str:
    name = _clean_fragment(project.get("name", "Project"))
    technologies = [tech for tech in project.get("technologies", []) if tech]
    if technologies:
        return f"{name} using {', '.join(technologies)}"
    return name

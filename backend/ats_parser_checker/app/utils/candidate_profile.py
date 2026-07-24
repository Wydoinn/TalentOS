from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from app.core.ats_rules import get_ats_rules
from app.schemas.ingestion import StructuredResume
from app.utils.text import extract_skills
from app.utils.text import normalize_text

_RULES = get_ats_rules()
_ROLE_RULES = _RULES["role_matching"]
_ROLE_SCORING_WEIGHTS = _ROLE_RULES["weights"]
_ROLE_THRESHOLDS = _ROLE_RULES["thresholds"]
_ALIGNMENT_SCORES = _ROLE_RULES["alignment_scores"]

_STOPWORDS = set(_ROLE_RULES["stopwords"])
_ROLE_TOKEN_STOPWORDS = set(_ROLE_RULES["role_token_stopwords"])
_ROLE_FAMILY_DEFINITIONS: dict[str, dict[str, tuple[str, ...]]] = {
    family: {
        field_name: tuple(values)
        for field_name, values in definition.items()
    }
    for family, definition in _ROLE_RULES["families"].items()
}
_ROLE_FAMILY_SIMILARITY: dict[tuple[str, str], float] = {
    tuple(key.split("|", maxsplit=1)): float(value)
    for key, value in _ROLE_RULES["family_similarity"].items()
}
_EXPERIENCE_LEVELS = list(_ROLE_RULES["experience_levels"])


@dataclass(slots=True)
class RoleProfile:
    family_scores: dict[str, float]
    primary_families: list[str]
    secondary_families: list[str]


def normalize_skill_name(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def experience_level_name(total_experience_years: float) -> str:
    for level in _EXPERIENCE_LEVELS:
        max_years = level.get("max_years")
        if max_years is None or total_experience_years < float(max_years):
            return str(level["name"])
    return str(_EXPERIENCE_LEVELS[-1]["name"])


def experience_level_range(level_name: str) -> tuple[float, float | None]:
    normalized = level_name.strip().lower()
    for level in _EXPERIENCE_LEVELS:
        if str(level["name"]).lower() == normalized:
            max_years = level.get("max_years")
            return (float(level["min_years"]), None if max_years is None else float(max_years))
    fallback = _EXPERIENCE_LEVELS[-1]
    return (float(fallback["min_years"]), None if fallback.get("max_years") is None else float(fallback["max_years"]))


def build_project_key(candidate_id: str, project_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", project_name.strip().lower()).strip("-")
    slug = slug or "project"
    return f"{candidate_id}:{slug}"


def build_experience_key(candidate_id: str, index: int) -> str:
    return f"{candidate_id}:experience:{index}"


def education_summary(structured_resume: StructuredResume) -> str:
    fragments: list[str] = []
    for record in structured_resume.education[:3]:
        fragment = " ".join(
            part
            for part in (
                record.degree,
                record.field_of_study,
                record.institution,
                record.graduation_year,
            )
            if part
        ).strip()
        if fragment:
            fragments.append(fragment)
    return " | ".join(fragments[:2])


def build_pinecone_metadata(
    *,
    candidate_id: str,
    source: str,
    structured_resume: StructuredResume,
) -> dict[str, object]:
    return {
        "candidate_id": candidate_id,
        "source": source,
        "skills": resume_skill_inventory(structured_resume),
        "experience_years": round(float(structured_resume.total_experience_years or 0.0), 2),
        "current_role": (structured_resume.current_title or "").strip(),
        "location": (structured_resume.location or "").strip(),
        "education": education_summary(structured_resume),
        "top_keywords": extract_top_keywords(structured_resume),
    }


def build_graph_payload(
    *,
    candidate_id: str,
    full_name: str,
    source: str,
    structured_resume: StructuredResume,
) -> dict[str, object]:
    projects = [
        {
            "key": build_project_key(candidate_id, project.name),
            "name": project.name.strip(),
            "summary": (project.summary or "").strip(),
            "skills": deduplicate_skills(
                [
                    *project.technologies,
                    *extract_skills(
                        " ".join(
                            fragment
                            for fragment in (
                                project.name,
                                project.summary or "",
                                " ".join(project.technologies),
                            )
                            if fragment
                        )
                    ),
                ]
            ),
        }
        for project in structured_resume.projects
        if project.name.strip()
    ]
    experiences = [
        {
            "key": build_experience_key(candidate_id, index),
            "role": experience.title.strip(),
            "company": normalize_company_name(experience.company),
            "description": (experience.summary or "").strip(),
            "start_date": (experience.start_date or "").strip(),
            "end_date": (experience.end_date or "").strip(),
            "skills": deduplicate_skills(
                extract_skills(
                    " ".join(
                        fragment
                        for fragment in (
                            experience.title,
                            experience.company or "",
                            experience.summary or "",
                        )
                        if fragment
                    )
                )
            ),
        }
        for index, experience in enumerate(structured_resume.experience, start=1)
        if experience.title.strip()
    ]
    total_experience_years = round(float(structured_resume.total_experience_years or 0.0), 2)
    experience_level = experience_level_name(total_experience_years)
    min_years, max_years = experience_level_range(experience_level)
    return {
        "full_name": full_name,
        "source": source,
        "current_title": (structured_resume.current_title or "").strip(),
        "total_experience_years": total_experience_years,
        "skills": resume_skill_inventory(structured_resume),
        "projects": projects,
        "experiences": experiences,
        "experience_level": experience_level,
        "experience_min_years": min_years,
        "experience_max_years": max_years,
    }


def resume_skill_inventory(structured_resume: StructuredResume) -> list[str]:
    evidence_fragments = [
        structured_resume.current_title or "",
        structured_resume.summary,
    ]
    for project in structured_resume.projects:
        evidence_fragments.extend(
            [
                project.name,
                project.summary or "",
                " ".join(project.technologies),
            ]
        )
    for experience in structured_resume.experience:
        evidence_fragments.extend(
            [
                experience.title,
                experience.company or "",
                experience.summary or "",
            ]
        )

    inferred_skills = extract_skills(" ".join(fragment for fragment in evidence_fragments if fragment))
    return deduplicate_skills(
        [
            *structured_resume.skills,
            *(technology for project in structured_resume.projects for technology in project.technologies),
            *inferred_skills,
        ]
    )


def deduplicate_skills(skills: list[str]) -> list[str]:
    deduplicated = {
        normalize_skill_name(skill)
        for skill in skills
        if skill and skill.strip()
    }
    return sorted(skill for skill in deduplicated if skill)


def normalize_company_name(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = re.sub(r"\s+", " ", value.strip())
    if not normalized:
        return None
    if len(normalized) > 80 or len(normalized.split()) > 6:
        return None
    if re.search(r"[.?!]$", normalized):
        return None
    return normalized


def extract_top_keywords(
    structured_resume: StructuredResume,
    *,
    max_keywords: int = 12,
) -> list[str]:
    counter: Counter[str] = Counter()

    for skill in deduplicate_skills(structured_resume.skills):
        counter[skill] += 4

    for project in structured_resume.projects:
        for technology in deduplicate_skills(project.technologies):
            counter[technology] += 3

    title_fragments = [
        structured_resume.current_title or "",
        *(item.title for item in structured_resume.experience[:3]),
    ]
    for fragment in title_fragments:
        for token in _keyword_tokens(fragment):
            counter[token] += 2

    summary_fragments = [
        structured_resume.summary,
        *(project.summary or "" for project in structured_resume.projects[:3]),
    ]
    for fragment in summary_fragments:
        for token in _keyword_tokens(fragment):
            counter[token] += 1

    return [token for token, _ in counter.most_common(max_keywords)]


def role_keywords(title: str | None) -> list[str]:
    if not title:
        return []
    return [
        token
        for token in _keyword_tokens(title)
        if token not in _ROLE_TOKEN_STOPWORDS
    ]


def infer_role_profile(
    *,
    title: str | None,
    text: str | None = None,
    skills: list[str] | None = None,
) -> RoleProfile:
    normalized_title = normalize_text(title or "").lower()
    normalized_text = normalize_text(text or "").lower()
    normalized_skills = {normalize_skill_name(skill) for skill in skills or [] if skill and skill.strip()}

    family_scores: dict[str, float] = {}
    for family, definition in _ROLE_FAMILY_DEFINITIONS.items():
        score = 0.0
        if any(_contains_role_phrase(normalized_title, alias) for alias in definition["title_aliases"]):
            score += _ROLE_SCORING_WEIGHTS["title_match"]

        text_hits = sum(
            1 for alias in definition["text_aliases"] if _contains_role_phrase(normalized_text, alias)
        )
        score += min(
            text_hits * _ROLE_SCORING_WEIGHTS["text_hit"],
            _ROLE_SCORING_WEIGHTS["text_hit_cap"],
        )

        skill_hits = sum(
            1 for hint in definition["skill_hints"] if normalize_skill_name(hint) in normalized_skills
        )
        score += min(
            skill_hits * _ROLE_SCORING_WEIGHTS["skill_hit"],
            _ROLE_SCORING_WEIGHTS["skill_hit_cap"],
        )
        family_scores[family] = round(score, 4)

    minimum_family_score = _ROLE_THRESHOLDS["minimum_family_score"]
    if family_scores["backend"] >= minimum_family_score and family_scores["frontend"] >= minimum_family_score:
        family_scores["fullstack"] = round(
            family_scores["fullstack"] + _ROLE_SCORING_WEIGHTS["fullstack_boost"],
            4,
        )

    max_score = max(family_scores.values(), default=0.0)
    if max_score < minimum_family_score:
        return RoleProfile(family_scores=family_scores, primary_families=[], secondary_families=[])

    primary_threshold = max(
        _ROLE_THRESHOLDS["primary_floor"],
        max_score - _ROLE_THRESHOLDS["primary_gap"],
    )
    secondary_threshold = max(
        _ROLE_THRESHOLDS["secondary_floor"],
        max_score - _ROLE_THRESHOLDS["secondary_gap"],
    )
    primary_families = [
        family
        for family, score in family_scores.items()
        if score >= primary_threshold
    ]
    secondary_families = [
        family
        for family, score in family_scores.items()
        if family not in primary_families and score >= secondary_threshold
    ]
    return RoleProfile(
        family_scores=family_scores,
        primary_families=sorted(primary_families),
        secondary_families=sorted(secondary_families),
    )


def role_alignment_score(*, job_profile: RoleProfile, candidate_profile: RoleProfile) -> float:
    if not job_profile.primary_families:
        return _ALIGNMENT_SCORES["no_job_primary"]

    candidate_families = candidate_profile.primary_families or candidate_profile.secondary_families
    if not candidate_families:
        return _ALIGNMENT_SCORES["no_candidate_family"]

    overlap = set(job_profile.primary_families) & set(candidate_profile.primary_families)
    if overlap:
        return _ALIGNMENT_SCORES["primary_overlap"]

    secondary_overlap = set(job_profile.primary_families) & set(candidate_profile.secondary_families)
    if secondary_overlap:
        return _ALIGNMENT_SCORES["secondary_overlap"]

    strongest = max(
        _role_family_similarity(job_family, candidate_family)
        for job_family in job_profile.primary_families
        for candidate_family in candidate_families
    )
    if candidate_profile.primary_families:
        strongest = max(strongest - _ALIGNMENT_SCORES["primary_family_penalty"], 0.0)
    return round(max(strongest, _ALIGNMENT_SCORES["minimum_similarity"]), 4)


def role_alignment_label(role_profile: RoleProfile) -> str | None:
    families = role_profile.primary_families or role_profile.secondary_families
    if not families:
        return None
    return "/".join(families[:2])


def _keyword_tokens(text: str) -> list[str]:
    normalized = normalize_text(text).lower()
    tokens = re.findall(r"[a-z0-9+#.]{2,}", normalized)
    return [token for token in tokens if token not in _STOPWORDS]


def _contains_role_phrase(haystack: str, phrase: str) -> bool:
    normalized_phrase = normalize_text(phrase).lower().strip()
    if not normalized_phrase:
        return False
    escaped = re.escape(normalized_phrase).replace(r"\ ", r"\s+")
    return bool(re.search(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", haystack))


def _role_family_similarity(left: str, right: str) -> float:
    if left == right:
        return 1.0
    if (left, right) in _ROLE_FAMILY_SIMILARITY:
        return _ROLE_FAMILY_SIMILARITY[(left, right)]
    if (right, left) in _ROLE_FAMILY_SIMILARITY:
        return _ROLE_FAMILY_SIMILARITY[(right, left)]
    return _ALIGNMENT_SCORES["minimum_similarity"]

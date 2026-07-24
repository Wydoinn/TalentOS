from __future__ import annotations

import math
import re
from collections import Counter

from app.core.ats_rules import get_ats_rules

_RULES = get_ats_rules()
_RETRIEVAL_RULES = _RULES["retrieval"]
_BM25_RULES = _RETRIEVAL_RULES["bm25"]
_EXPERIENCE_BANDS = list(_RETRIEVAL_RULES["experience_bands"])

def tokenize_for_retrieval(text: str) -> list[str]:
    return re.findall(r"[a-z0-9+#.]{2,}", text.lower())


def build_lexical_document(
    *,
    current_title: str | None,
    summary: str,
    skills: list[str],
    experience_titles: list[str],
    project_names: list[str],
    project_summaries: list[str],
) -> str:
    fragments = [
        current_title or "",
        summary,
        " ".join(skills),
        " ".join(experience_titles),
        " ".join(project_names),
        " ".join(project_summaries),
    ]
    return " ".join(fragment for fragment in fragments if fragment).strip()


def bm25_score_documents(
    *,
    query: str,
    documents: dict[str, str],
    k1: float = _BM25_RULES["k1"],
    b: float = _BM25_RULES["b"],
) -> dict[str, float]:
    if not query.strip() or not documents:
        return {}

    tokenized_documents = {
        doc_id: tokenize_for_retrieval(content)
        for doc_id, content in documents.items()
    }
    query_terms = list(dict.fromkeys(tokenize_for_retrieval(query)))
    if not query_terms:
        return {doc_id: 0.0 for doc_id in documents}

    document_count = len(tokenized_documents)
    average_length = (
        sum(len(tokens) for tokens in tokenized_documents.values()) / document_count
        if document_count
        else 1.0
    )
    doc_frequencies: Counter[str] = Counter()
    for tokens in tokenized_documents.values():
        doc_frequencies.update(set(tokens))

    scores: dict[str, float] = {}
    for doc_id, tokens in tokenized_documents.items():
        if not tokens:
            scores[doc_id] = 0.0
            continue
        term_frequencies = Counter(tokens)
        document_length = len(tokens)
        score = 0.0
        for term in query_terms:
            frequency = term_frequencies.get(term, 0)
            if not frequency:
                continue
            idf = math.log(1 + ((document_count - doc_frequencies.get(term, 0) + 0.5) / (doc_frequencies.get(term, 0) + 0.5)))
            numerator = frequency * (k1 + 1)
            denominator = frequency + k1 * (1 - b + b * (document_length / max(average_length, 1.0)))
            score += idf * (numerator / max(denominator, 1e-9))
        scores[doc_id] = round(score, 4)
    return scores


def normalize_score_map(score_map: dict[str, float]) -> dict[str, float]:
    if not score_map:
        return {}
    maximum = max(score_map.values())
    minimum = min(score_map.values())
    if maximum <= 0 or math.isclose(maximum, minimum):
        return {key: 0.0 if maximum <= 0 else 1.0 for key in score_map}
    return {
        key: round((value - minimum) / (maximum - minimum), 4)
        for key, value in score_map.items()
    }


def phrase_overlap_score(
    *,
    phrases: list[str],
    text: str,
) -> float:
    normalized_text = text.lower()
    normalized_phrases = [phrase.strip().lower() for phrase in phrases if phrase.strip()]
    if not normalized_phrases:
        return 0.0
    matched = sum(1 for phrase in normalized_phrases if phrase in normalized_text)
    return round(matched / len(normalized_phrases), 4)


def experience_band(years: float) -> str:
    for band in _EXPERIENCE_BANDS:
        max_years = band.get("max_years")
        if max_years is None or years < float(max_years):
            return str(band["label"])
    return str(_EXPERIENCE_BANDS[-1]["label"])


def jaccard_similarity(left_items: list[str], right_items: list[str]) -> float:
    left = {item.strip().lower() for item in left_items if item and item.strip()}
    right = {item.strip().lower() for item in right_items if item and item.strip()}
    if not left or not right:
        return 0.0
    return round(len(left & right) / len(left | right), 4)

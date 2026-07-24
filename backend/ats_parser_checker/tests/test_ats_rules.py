from __future__ import annotations

from app.core.ats_rules import get_ats_rules


def test_ats_rules_expose_required_sections_and_default_weights() -> None:
    rules = get_ats_rules()

    assert "resume_parser" in rules
    assert "ats_scoring" in rules
    assert "role_matching" in rules
    assert "retrieval" in rules
    assert "analysis" in rules
    assert rules["analysis"]["ats_component_weights"]["keyword"] == 0.25
    assert rules["retrieval"]["graph_score_weights"]["skill_overlap"] == 0.4
    assert "python" in rules["skill_aliases"]

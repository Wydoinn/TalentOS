from __future__ import annotations

from app.core.ats_rules import get_ats_rules

_RULES = get_ats_rules()

SKILL_ALIASES: dict[str, tuple[str, ...]] = {
    canonical: tuple(aliases)
    for canonical, aliases in _RULES["skill_aliases"].items()
}

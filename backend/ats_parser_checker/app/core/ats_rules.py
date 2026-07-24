from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ATS_RULES_PATH = PROJECT_ROOT / "app" / "data" / "ats_rules.json"
BACKEND_ROOT = PROJECT_ROOT.parent

_REQUIRED_RULE_SECTIONS = {
    "analysis",
    "ats_scoring",
    "resume_parser",
    "retrieval",
    "role_matching",
    "section_headers",
    "skill_aliases",
}


def _strip_matching_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _read_dotenv(dotenv_path: Path) -> dict[str, str]:
    if not dotenv_path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = _strip_matching_quotes(value.strip())
        if key:
            values[key] = value
    return values


def _load_env_files() -> None:
    merged = {
        **_read_dotenv(BACKEND_ROOT / ".env"),
        **_read_dotenv(PROJECT_ROOT / ".env"),
    }
    for key, value in merged.items():
        os.environ.setdefault(key, value)


def ats_rules_path() -> Path:
    _load_env_files()
    configured = os.getenv("ATS_RULES_PATH")
    if configured:
        return Path(configured).expanduser().resolve()
    return DEFAULT_ATS_RULES_PATH


@lru_cache(maxsize=1)
def get_ats_rules() -> dict[str, Any]:
    path = ats_rules_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"ATS rules file was not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"ATS rules file is not valid JSON: {path}") from exc

    missing_sections = sorted(_REQUIRED_RULE_SECTIONS - set(payload))
    if missing_sections:
        raise RuntimeError(
            "ATS rules file is missing required sections: " + ", ".join(missing_sections)
        )
    return payload


def reload_ats_rules() -> dict[str, Any]:
    get_ats_rules.cache_clear()
    return get_ats_rules()

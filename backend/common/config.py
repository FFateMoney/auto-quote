from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "backend" / "dev" / "config.yaml"
LEGACY_CONFIG_PATH = PROJECT_ROOT / "config.yaml"


def as_bool(value: Any, *, default: bool) -> bool:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def nested(config: dict[str, Any], *keys: str, default: Any = None) -> Any:
    current: Any = config
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def resolve_path(project_root: Path, value: str | os.PathLike[str] | None, *, fallback: Path | None = None) -> Path:
    if value in (None, ""):
        if fallback is None:
            raise ValueError("missing_path_value")
        return fallback
    path = Path(value)
    if not path.is_absolute():
        path = project_root / path
    return path


@lru_cache(maxsize=1)
def load_config() -> dict[str, Any]:
    explicit = os.environ.get("AUTO_QUOTE_CONFIG_PATH")
    if explicit:
        config_path = Path(explicit)
    elif DEFAULT_CONFIG_PATH.exists():
        config_path = DEFAULT_CONFIG_PATH
    else:
        config_path = LEGACY_CONFIG_PATH
    if not config_path.exists():
        return {}
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return payload if isinstance(payload, dict) else {}

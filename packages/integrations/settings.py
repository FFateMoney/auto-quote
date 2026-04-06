from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STANDARDS_DIR = PROJECT_ROOT / "standards"
DEFAULT_STANDARD_INDEX_DIR = PROJECT_ROOT / "data" / "standard_index"
DEFAULT_AIWORD_SCRIPT = Path("/my_storage/chen/auto-quote-engine/AIWord/scripts/ai_edit.py")


def _as_bool(value: Any, *, default: bool) -> bool:
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


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


@lru_cache(maxsize=1)
def load_config() -> dict[str, Any]:
    config_path = PROJECT_ROOT / "config.yaml"
    return _load_yaml(config_path)


def _nested(config: dict[str, Any], *keys: str, default: Any = None) -> Any:
    current: Any = config
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


class Settings:
    def __init__(self) -> None:
        config = load_config()
        self.project_root = PROJECT_ROOT
        self.run_dir = self._resolve_path(
            os.environ.get("AUTO_QUOTE_RUN_DIR") or _nested(config, "runtime", "run_dir", default="runtime/runs")
        )
        self.prompts_path = self._resolve_path(
            os.environ.get("AUTO_QUOTE_PROMPTS_PATH") or _nested(config, "integrations", "prompts_path", default="prompts.json")
        )
        self.aiword_script_path = self._resolve_path(
            os.environ.get("AUTO_QUOTE_AIWORD_SCRIPT") or _nested(config, "integrations", "aiword_script_path"),
            fallback=DEFAULT_AIWORD_SCRIPT,
        )
        self.standards_dir = self._resolve_path(
            os.environ.get("AUTO_QUOTE_STANDARDS_DIR") or _nested(config, "integrations", "standards_dir"),
            fallback=DEFAULT_STANDARDS_DIR,
        )
        self.standard_index_dir = self._resolve_path(
            os.environ.get("AUTO_QUOTE_STANDARD_INDEX_DIR") or _nested(config, "integrations", "standard_index_dir"),
            fallback=DEFAULT_STANDARD_INDEX_DIR,
        )
        self.standard_index_enable = _as_bool(
            os.environ.get("AUTO_QUOTE_STANDARD_INDEX_ENABLE")
            or _nested(config, "integrations", "standard_index_enable"),
            default=True,
        )
        self.standard_index_debug = _as_bool(
            os.environ.get("AUTO_QUOTE_STANDARD_INDEX_DEBUG")
            or _nested(config, "integrations", "standard_index_debug"),
            default=True,
        )
        self.standard_retrieval_top_k = int(
            os.environ.get("AUTO_QUOTE_STANDARD_RETRIEVAL_TOP_K")
            or _nested(config, "integrations", "standard_retrieval_top_k", default=5)
        )
        self.standard_retrieval_expand_neighbors = _as_bool(
            os.environ.get("AUTO_QUOTE_STANDARD_RETRIEVAL_EXPAND_NEIGHBORS")
            or _nested(config, "integrations", "standard_retrieval_expand_neighbors"),
            default=True,
        )
        self.qwen_api_key = (
            os.environ.get("DASHSCOPE_API_KEY")
            or os.environ.get("AUTO_QUOTE_QWEN_API_KEY")
            or _nested(config, "qwen", "api_key", default="")
        )
        self.qwen_model = os.environ.get("AUTO_QUOTE_QWEN_MODEL") or _nested(config, "qwen", "model", default="qwen3-omni-flash")
        self.qwen_base_url = os.environ.get("AUTO_QUOTE_QWEN_BASE_URL") or _nested(
            config,
            "qwen",
            "base_url",
            default="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        self.database = {
            "dbname": os.environ.get("PGDATABASE") or _nested(config, "database", "dbname"),
            "user": os.environ.get("PGUSER") or _nested(config, "database", "user"),
            "password": os.environ.get("PGPASSWORD") or _nested(config, "database", "password"),
            "host": os.environ.get("PGHOST") or _nested(config, "database", "host"),
            "port": int(os.environ.get("PGPORT") or _nested(config, "database", "port", default=5432)),
        }

    def _resolve_path(self, value: str | os.PathLike[str] | None, fallback: Path | None = None) -> Path:
        if value in (None, ""):
            if fallback is None:
                raise ValueError("missing_path_value")
            return Path(fallback)
        path = Path(value)
        if not path.is_absolute():
            path = self.project_root / path
        return path


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.run_dir.mkdir(parents=True, exist_ok=True)
    settings.standard_index_dir.mkdir(parents=True, exist_ok=True)
    return settings

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from backend.common.config import PROJECT_ROOT, as_bool, load_config, nested, resolve_path


DEFAULT_RUN_DIR = PROJECT_ROOT / "runtime" / "runs"
DEFAULT_STANDARD_KB_DIR = PROJECT_ROOT / "data" / "claned_markdown"
DEFAULT_STANDARDS_SOURCE_DIR = PROJECT_ROOT / "data" / "origin"
DEFAULT_PROMPTS_PATH = PROJECT_ROOT / "backend" / "quote" / "llm" / "prompts.json"
DEFAULT_AIWORD_SCRIPT = Path("/my_storage/chen/auto-quote-engine/AIWord/scripts/ai_edit.py")


@dataclass(slots=True)
class QuoteSettings:
    host: str
    port: int
    run_dir: Path
    prompts_path: Path
    aiword_script_path: Path
    standard_kb_dir: Path
    standard_index_enable: bool
    standard_retrieval_top_k: int
    standard_retrieval_expand_neighbors: bool
    ocr_service_base_url: str
    indexing_service_base_url: str
    qwen_api_key: str
    qwen_model: str
    qwen_base_url: str
    database: dict[str, object]


@lru_cache(maxsize=1)
def get_settings() -> QuoteSettings:
    cfg = load_config()

    def _s(env_key: str, *config_keys: str, default: object = None) -> object:
        v = os.environ.get(env_key)
        if v is not None:
            return v
        return nested(cfg, "services", "quote_service", *config_keys, default=default)

    return QuoteSettings(
        host=str(_s("QUOTE_HOST", "host", default="127.0.0.1")).strip(),
        port=int(_s("QUOTE_PORT", "port", default=8000)),
        run_dir=resolve_path(PROJECT_ROOT, _s("QUOTE_RUN_DIR", "run_dir"), fallback=DEFAULT_RUN_DIR),
        prompts_path=resolve_path(PROJECT_ROOT, _s("QUOTE_PROMPTS_PATH", "prompts_path"), fallback=DEFAULT_PROMPTS_PATH),
        aiword_script_path=resolve_path(PROJECT_ROOT, _s("QUOTE_AIWORD_SCRIPT", "aiword_script_path"), fallback=DEFAULT_AIWORD_SCRIPT),
        standard_kb_dir=resolve_path(PROJECT_ROOT, _s("QUOTE_STANDARD_KB_DIR", "standard_kb_dir"), fallback=DEFAULT_STANDARD_KB_DIR),
        standard_index_enable=as_bool(_s("QUOTE_STANDARD_INDEX_ENABLE", "standard_index_enable"), default=True),
        standard_retrieval_top_k=int(_s("QUOTE_STANDARD_RETRIEVAL_TOP_K", "standard_retrieval_top_k", default=5)),
        standard_retrieval_expand_neighbors=as_bool(_s("QUOTE_STANDARD_RETRIEVAL_EXPAND_NEIGHBORS", "standard_retrieval_expand_neighbors"), default=True),
        ocr_service_base_url=str(_s("QUOTE_OCR_SERVICE_BASE_URL", "ocr_service_base_url", default="http://127.0.0.1:8001")).rstrip("/"),
        indexing_service_base_url=str(_s("QUOTE_INDEXING_SERVICE_BASE_URL", "indexing_service_base_url", default="http://127.0.0.1:8003")).rstrip("/"),
        qwen_api_key=str(_s("QWEN_API_KEY", "qwen", "api_key") or nested(cfg, "qwen", "api_key", default="")),
        qwen_model=str(_s("QWEN_MODEL", "qwen", "model") or nested(cfg, "qwen", "model", default="qwen-vl-max")),
        qwen_base_url=str(_s("QWEN_BASE_URL", "qwen", "base_url") or nested(cfg, "qwen", "base_url", default="https://dashscope.aliyuncs.com/compatible-mode/v1")),
        database=dict(nested(cfg, "database", default={}) or {}),
    )

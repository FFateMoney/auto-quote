from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from backend.common.config import PROJECT_ROOT, load_config, nested, resolve_path
from backend.common.pipeline_state import migrate_cleaned_dir


@dataclass(slots=True)
class CleaningSettings:
    host: str
    port: int
    input_dir: Path
    output_dir: Path


@lru_cache(maxsize=1)
def get_settings() -> CleaningSettings:
    cfg = load_config()

    def _s(env_key: str, *config_keys: str, default: object = None) -> object:
        v = os.environ.get(env_key)
        if v is not None:
            return v
        return nested(cfg, "services", "cleaning", *config_keys, default=default)

    output_dir = resolve_path(
        PROJECT_ROOT,
        _s("CLEANING_OUTPUT_DIR", "output_dir"),
        fallback=PROJECT_ROOT / "data" / "cleaned_markdown",
    )
    output_dir = migrate_cleaned_dir(output_dir)

    return CleaningSettings(
        host=str(_s("CLEANING_HOST", "host", default="127.0.0.1")).strip(),
        port=int(_s("CLEANING_PORT", "port", default=8002)),
        input_dir=resolve_path(
            PROJECT_ROOT, 
            _s("CLEANING_INPUT_DIR", "input_dir"), 
            fallback=PROJECT_ROOT / "data" / "ocr_markdown"
        ),
        output_dir=output_dir,
    )

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from backend.common.config import PROJECT_ROOT, load_config, nested, resolve_path
from backend.common.pipeline_state import migrate_cleaned_dir


@dataclass(slots=True)
class IndexingSettings:
    host: str
    port: int
    qdrant_url: str
    qdrant_api_key: str | None
    collection_name: str
    input_dir: Path
    embedding_model_path: str
    reranker_model_path: str
    vector_size: int = 4096


@lru_cache(maxsize=1)
def get_settings() -> IndexingSettings:
    cfg = load_config()

    def _s(env_key: str, *config_keys: str, default: object = None) -> object:
        v = os.environ.get(env_key)
        if v is not None:
            return v
        return nested(cfg, "services", "indexing", *config_keys, default=default)

    input_dir = resolve_path(
        PROJECT_ROOT,
        _s("INDEXING_INPUT_DIR", "input_dir"),
        fallback=PROJECT_ROOT / "data" / "cleaned_markdown",
    )
    input_dir = migrate_cleaned_dir(input_dir)

    return IndexingSettings(
        host=str(_s("INDEXING_HOST", "host", default="127.0.0.1")).strip(),
        port=int(_s("INDEXING_PORT", "port", default=8003)),
        qdrant_url=str(_s("QDRANT_URL", "qdrant_url", default="http://localhost:6333")).strip(),
        qdrant_api_key=_s("QDRANT_API_KEY", "qdrant_api_key", default=None),
        collection_name=str(_s("QDRANT_COLLECTION", "collection_name", default="standard_kb")).strip(),
        input_dir=input_dir,
        embedding_model_path=str(_s("EMBEDDING_MODEL_PATH", "embedding_model_path", default="/my_storage/chen/quote_models/Qwen3-embedding-8b")),
        reranker_model_path=str(_s("RERANKER_MODEL_PATH", "reranker_model_path", default="/my_storage/chen/quote_models/reranker-8b")),
    )

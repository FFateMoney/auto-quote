from __future__ import annotations

import hashlib
import json
from pathlib import Path

from backendV2.core.history.repository import HistoricalQuotationCacheReader
from backendV2.core.settings import Settings
from backendV2.core.tools.paths import resolve_run_dir


class QueryHistoricalQuotationCacheTool:
    def __init__(self, settings: Settings, repository: HistoricalQuotationCacheReader) -> None:
        self._settings = settings
        self._repository = repository

    def execute(
        self,
        run_dir: str | Path,
        standard_type: str,
        test_item: str,
        standard_code: str,
    ) -> Path:
        resolved_run_dir = resolve_run_dir(self._settings, run_dir)
        cache = self._repository.read_standard_cache(standard_type, test_item, standard_code)
        destination_dir = resolved_run_dir / "history_cache"
        destination_dir.mkdir(exist_ok=True)
        destination = destination_dir / f"{self._cache_file_id(standard_type, test_item, standard_code)}.json"
        destination.write_text(json.dumps(cache.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return destination

    @staticmethod
    def _cache_file_id(standard_type: str, test_item: str, standard_code: str) -> str:
        source = "\x1f".join((standard_type, test_item, standard_code))
        return hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]

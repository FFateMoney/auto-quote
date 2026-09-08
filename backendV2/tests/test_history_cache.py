from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backendV2.core.history.cache import (
    HistoricalQuotationCache,
    HistoricalQuotationCacheBuilder,
    HistoricalQuotationReuseField,
)
from backendV2.core.history.repository import HistoricalQuotationCacheReader
from backendV2.core.settings import Settings
from backendV2.core.tools.query_history_quotation_cache import QueryHistoricalQuotationCacheTool


class StaticHistoryCacheReader(HistoricalQuotationCacheReader):
    def __init__(self, cache: HistoricalQuotationCache) -> None:
        self.cache = cache
        self.calls: list[tuple[str, str, str]] = []

    def read_standard_cache(self, standard_type: str, test_item: str, standard_code: str) -> HistoricalQuotationCache:
        self.calls.append((standard_type, test_item, standard_code))
        return self.cache


class HistoricalQuotationCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.reuse_fields = (
            HistoricalQuotationReuseField("standard_document_section", "fixed_fields", "standard_clause", True),
            HistoricalQuotationReuseField("temperature_min_c", "special_fields", "standard_clause", False),
            HistoricalQuotationReuseField("frequency_max_hz", "special_fields", "standard_clause", False),
        )

    def test_returns_only_consistent_reusable_fields_in_each_standard_clause(self) -> None:
        cache = HistoricalQuotationCacheBuilder().build(
            "环境试验",
            "高低温",
            "GJB 150.3A-2009",
            self.reuse_fields,
            (
                self._snapshot("3.1", -40, 2000, 999),
                self._snapshot("3.1", -40, 2500, 888),
                self._snapshot("4.2", -20, 1000, 777),
            ),
        )

        self.assertEqual(
            cache.to_dict(),
            {
                "standard_type": "环境试验",
                "test_item": "高低温",
                "standard_code": "GJB 150.3A-2009",
                "items": [
                    {
                        "fixed_fields": {"standard_document_section": "3.1"},
                        "special_fields": {"temperature_min_c": -40},
                    },
                    {
                        "fixed_fields": {"standard_document_section": "4.2"},
                        "special_fields": {"temperature_min_c": -20, "frequency_max_hz": 1000},
                    },
                ],
            },
        )

    def test_writes_the_cache_file_without_exposing_cache_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            settings = Settings(
                project_root=root,
                core_runtime_root=root / "core" / "runtime",
                agent_workspace_root=root / "agent_workspace",
                agent_executable="codex",
                agent_profile="quote-agent",
                qwen_api_key="",
                database={},
            )
            run_dir = settings.agent_runs_root / "run-001"
            run_dir.mkdir(parents=True)
            cache = HistoricalQuotationCache("环境试验", "高低温", "GJB 150.3A-2009", tuple())
            reader = StaticHistoryCacheReader(cache)

            destination = QueryHistoricalQuotationCacheTool(settings, reader).execute(
                run_dir,
                "环境试验",
                "高低温",
                "GJB 150.3A-2009",
            )

            self.assertEqual(reader.calls, [("环境试验", "高低温", "GJB 150.3A-2009")])
            self.assertEqual(json.loads(destination.read_text(encoding="utf-8")), cache.to_dict())
            self.assertEqual(destination.parent.name, "history_cache")

    @staticmethod
    def _snapshot(
        section: str,
        temperature_min_c: int,
        frequency_max_hz: int,
        max_load_kg: int,
    ) -> dict[str, object]:
        return {
            "fixed_fields": {"standard_document_section": section},
            "special_fields": {
                "temperature_min_c": temperature_min_c,
                "frequency_max_hz": frequency_max_hz,
                "max_load_kg": max_load_kg,
            },
        }

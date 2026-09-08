from __future__ import annotations

import json
from pathlib import Path

from backendV2.core.catalog.repository import TestProjectAliasReader
from backendV2.core.settings import Settings
from backendV2.core.tools.paths import resolve_run_dir


class QueryTestProjectAliasesTool:
    def __init__(self, settings: Settings, repository: TestProjectAliasReader) -> None:
        self._settings = settings
        self._repository = repository

    def execute(self, run_dir: str | Path, test_project_id: int) -> Path:
        destination_dir = resolve_run_dir(self._settings, run_dir) / "aliases"
        destination_dir.mkdir(exist_ok=True)
        destination = destination_dir / f"test_project_{test_project_id}_aliases.json"
        payload = {
            "test_project_id": test_project_id,
            "aliases": list(self._repository.get_test_project_aliases(test_project_id)),
        }
        destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return destination

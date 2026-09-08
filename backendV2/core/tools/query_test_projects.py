from __future__ import annotations

import json
from pathlib import Path

from backendV2.core.catalog.repository import TestProjectReader
from backendV2.core.settings import Settings
from backendV2.core.tools.paths import resolve_run_dir


class QueryTestProjectsTool:
    def __init__(self, settings: Settings, repository: TestProjectReader) -> None:
        self._settings = settings
        self._repository = repository

    def execute(self, run_dir: str | Path) -> Path:
        destination_dir = resolve_run_dir(self._settings, run_dir)
        payload = {
            "items": [project.to_dict() for project in self._repository.list_test_projects()],
        }
        destination = destination_dir / "test_projects.json"
        destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return destination

from __future__ import annotations

import shutil
from pathlib import Path

from backendV2.core.settings import Settings
from backendV2.core.test_type_schemas.registry import TestTypeSchemaRegistry
from backendV2.core.tools.paths import resolve_run_dir


class GetTestTypeSchemaTool:
    def __init__(self, settings: Settings, schemas: TestTypeSchemaRegistry) -> None:
        self._settings = settings
        self._schemas = schemas

    def execute(self, run_dir: str | Path, test_type_id: int | None) -> Path:
        destination_dir = resolve_run_dir(self._settings, run_dir) / "schemas"
        schema = self._schemas.get(test_type_id)
        destination_dir.mkdir(exist_ok=True)
        destination = destination_dir / schema.source_path.name
        shutil.copyfile(schema.source_path, destination)
        return destination

from __future__ import annotations

import json
from pathlib import Path

from backendV2.core.catalog.special_fields import SpecialFieldDefinitionReader
from backendV2.core.catalog.repository import TestProjectQuoteTemplateReader
from backendV2.core.settings import Settings
from backendV2.core.submissions.templates import build_quote_values_template
from backendV2.core.tools.paths import resolve_run_dir


class QueryTestProjectCapabilityFieldsTool:
    def __init__(
        self,
        settings: Settings,
        repository: TestProjectQuoteTemplateReader,
        special_fields: SpecialFieldDefinitionReader,
    ) -> None:
        self._settings = settings
        self._repository = repository
        self._special_fields = special_fields

    def execute(self, run_dir: str | Path, test_project_id: int) -> Path:
        destination_dir = resolve_run_dir(self._settings, run_dir) / "schemas"
        destination_dir.mkdir(exist_ok=True)
        destination = destination_dir / f"test_project_{test_project_id}_schema.json"
        quote_template = self._repository.get_quote_template(test_project_id)
        definitions = self._special_fields.find_by_field_names(quote_template.capability_fields)
        payload = build_quote_values_template(
            quote_template.pricing_mode,
            (definition.field_name for definition in definitions),
            quote_template.max_specification,
        )
        destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return destination

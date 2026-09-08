from __future__ import annotations

import json
from pathlib import Path

from backendV2.core.settings import Settings
from backendV2.core.submissions.validator import QuoteTableValidator, ValidationResult
from backendV2.core.tools.paths import resolve_run_dir, resolve_run_file


class ValidateQuoteTableTool:
    def __init__(self, settings: Settings, validator: QuoteTableValidator) -> None:
        self._settings = settings
        self._validator = validator

    def execute(self, run_dir: str | Path, quote_table_file: str | Path) -> tuple[ValidationResult, Path]:
        resolved_run_dir = resolve_run_dir(self._settings, run_dir)
        quote_table_path = resolve_run_file(resolved_run_dir, quote_table_file)
        result = self._validator.validate_file(quote_table_path)
        destination = quote_table_path.with_name("validation_result.json")
        destination.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return result, destination

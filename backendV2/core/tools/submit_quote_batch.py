from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from backendV2.core.runs.service import RunService
from backendV2.core.settings import Settings
from backendV2.core.submissions.models import QuoteTableSubmission
from backendV2.core.submissions.validator import QuoteTableValidator
from backendV2.core.tools.paths import resolve_run_dir


@dataclass(frozen=True, slots=True)
class BatchSubmissionResult:
    accepted: bool
    message: str
    details: list[dict[str, str]]

    def to_dict(self) -> dict[str, object]:
        return {
            "accepted": self.accepted,
            "phase": "format",
            "message": self.message,
            "details": self.details,
        }


class SubmitQuoteBatchTool:
    """Collects all independent quote tables produced for one run."""

    def __init__(self, settings: Settings, validator: QuoteTableValidator, runs: RunService) -> None:
        self._settings = settings
        self._validator = validator
        self._runs = runs

    def execute(self, run_dir: str | Path) -> tuple[BatchSubmissionResult, Path]:
        resolved_run_dir = resolve_run_dir(self._settings, run_dir)
        quote_table_paths = self._quote_table_paths(resolved_run_dir)
        quote_tables: list[QuoteTableSubmission] = []
        details: list[dict[str, str]] = []

        if not quote_table_paths:
            details.append(
                {
                    "path": "quotes",
                    "rule": "missing_quote_tables",
                    "detail": "未找到可提交的报价表",
                }
            )

        for quote_table_path in quote_table_paths:
            validation = self._validator.validate_file(quote_table_path)
            relative_path = quote_table_path.relative_to(resolved_run_dir).as_posix()
            if validation.accepted and validation.quote_table is not None:
                quote_tables.append(QuoteTableSubmission(quote_table_path.parent.name, validation.quote_table))
                continue
            details.extend({"path": f"{relative_path}:{detail['path']}", "rule": detail["rule"], "detail": detail["detail"]} for detail in validation.details)

        accepted = not details
        if accepted:
            self._runs.accept_batch_submission(resolved_run_dir, quote_tables)
        result = BatchSubmissionResult(accepted, "成功" if accepted else "格式错误", details)
        destination = resolved_run_dir / "submit_result.json"
        destination.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return result, destination

    @staticmethod
    def _quote_table_paths(run_dir: Path) -> list[Path]:
        quotes_dir = run_dir / "quotes"
        if not quotes_dir.is_dir():
            return []
        return sorted(path for path in quotes_dir.glob("*/quote_table.json") if path.is_file())

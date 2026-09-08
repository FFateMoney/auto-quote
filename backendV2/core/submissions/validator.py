from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from backendV2.core.submissions.models import QuoteTable


@dataclass(frozen=True, slots=True)
class ValidationResult:
    accepted: bool
    message: str
    details: list[dict[str, str]]
    quote_table: QuoteTable | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "accepted": self.accepted,
            "phase": "format",
            "message": self.message,
            "details": self.details,
        }


class QuoteTableValidator:
    """Reads the common JSON envelope shared by Agent and Core."""

    def validate_file(self, quote_table_path: Path) -> ValidationResult:
        try:
            payload = json.loads(quote_table_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return self._error("file", "报价表文件不存在")
        except UnicodeDecodeError:
            return self._error("file", "报价表文件必须使用 UTF-8 编码")
        except json.JSONDecodeError as exc:
            return self._error("json", f"第 {exc.lineno} 行第 {exc.colno} 列不是合法 JSON")
        return self.validate_payload(payload)

    def validate_payload(self, payload: Any) -> ValidationResult:
        try:
            table = QuoteTable.model_validate(payload)
        except ValidationError as exc:
            details = [
                {
                    "path": self._format_location(error["loc"]),
                    "rule": str(error["type"]),
                    "detail": str(error["msg"]),
                }
                for error in exc.errors()
            ]
            return ValidationResult(False, "格式错误", details)
        return ValidationResult(True, "成功", [], table)

    @staticmethod
    def _error(rule: str, detail: str) -> ValidationResult:
        return ValidationResult(False, "格式错误", [{"path": "$", "rule": rule, "detail": detail}])

    @staticmethod
    def _format_location(location: tuple[object, ...]) -> str:
        parts: list[str] = []
        for value in location:
            if isinstance(value, int):
                parts[-1] = f"{parts[-1]}[{value}]" if parts else f"[{value}]"
            else:
                parts.append(str(value))
        return ".".join(parts) or "$"

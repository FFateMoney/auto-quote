from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from backendV2.core.catalog.repository import TestProjectAliasWriter, TestProjectRepository
from backendV2.core.catalog.special_fields import SpecialFieldDefinitionRepository
from backendV2.core.exports.quotation_docx import QuotationDocumentExporter
from backendV2.core.history.repository import HistoricalQuotation, HistoricalQuotationRepository, HistoricalQuotationWriter
from backendV2.core.quoting.repository import QuotationRepository
from backendV2.core.quoting.service import CoreQuotationService, QuotationProcessor
from backendV2.core.runs.agent_runner import AgentExecution, CodexAgentRunner
from backendV2.core.settings import Settings
from backendV2.core.submissions.models import QuoteTable, QuoteTableSubmission


class AgentRunner(Protocol):
    def run(self, run_dir: Path, prompt_path: Path) -> AgentExecution: ...


class QuotationDocumentWriter(Protocol):
    def export(self, output_path: Path, items: list[dict[str, object]]) -> None: ...


@dataclass(frozen=True, slots=True)
class RunInputFile:
    file_name: str
    content: bytes


@dataclass(frozen=True, slots=True)
class RunSnapshot:
    run_id: str
    status: str
    uploaded_file: str
    created_at: str
    updated_at: str
    agent_return_code: int | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class RunService:
    def __init__(
        self,
        settings: Settings,
        agent_runner: AgentRunner | None = None,
        quotation_processor: QuotationProcessor | None = None,
        document_exporter: QuotationDocumentWriter | None = None,
        alias_writer: TestProjectAliasWriter | None = None,
        history_writer: HistoricalQuotationWriter | None = None,
    ) -> None:
        self._settings = settings
        self._agent_runner = agent_runner or CodexAgentRunner(settings)
        self._quotation_processor = quotation_processor or CoreQuotationService(
            QuotationRepository(settings),
            SpecialFieldDefinitionRepository(settings),
        )
        self._document_exporter = document_exporter or QuotationDocumentExporter(
            settings.project_root / "doc" / "quote_tep.docx"
        )
        self._alias_writer = alias_writer or TestProjectRepository(settings)
        self._history_writer = history_writer or HistoricalQuotationRepository(settings)

    def create_run(
        self,
        file_name: str,
        content: bytes,
        reference_files: tuple[RunInputFile, ...] = (),
    ) -> RunSnapshot:
        if not content:
            raise ValueError("empty_file")
        run_id = self._next_run_id(file_name)
        run_dir = self._settings.agent_runs_root / run_id
        input_dir = run_dir / "input"
        input_dir.mkdir(parents=True, exist_ok=False)
        stored_name = self._store_input_file(input_dir, file_name, content)
        for reference_file in reference_files:
            if reference_file.content:
                self._store_input_file(input_dir, reference_file.file_name, reference_file.content)
        self._write_schema(run_dir)
        snapshot = self._new_snapshot(run_id, "created", stored_name)
        self._write_snapshot(snapshot)
        return snapshot

    def run_agent(self, run_id: str) -> RunSnapshot:
        snapshot = self.get_run(run_id)
        running = self._replace(snapshot, status="agent_running")
        self._write_snapshot(running)
        run_dir = self._run_dir(run_id)
        execution = self._agent_runner.run(run_dir, self._settings.agent_prompts_root / "extract_quote.md")
        submit_result = self._read_json(run_dir / "submit_result.json")
        if isinstance(submit_result, dict) and submit_result.get("accepted") is True:
            status = "submitted"
        elif execution.return_code == 0:
            status = "submission_rejected"
        else:
            status = "agent_failed"
        completed = self._replace(running, status=status, agent_return_code=execution.return_code)
        self._write_snapshot(completed)
        return completed

    def get_run(self, run_id: str) -> RunSnapshot:
        state_path = self._state_path(run_id)
        if not state_path.exists():
            raise KeyError(run_id)
        payload = json.loads(state_path.read_text(encoding="utf-8"))
        return RunSnapshot(**payload)

    def get_source_file(self, run_id: str) -> Path:
        snapshot = self.get_run(run_id)
        source_file = self._run_dir(run_id) / "input" / snapshot.uploaded_file
        if not source_file.is_file():
            raise KeyError(run_id)
        return source_file

    def list_runs(self) -> list[RunSnapshot]:
        snapshots: list[RunSnapshot] = []
        if not self._settings.core_runtime_root.exists():
            return snapshots
        for state_path in self._settings.core_runtime_root.glob("*/state.json"):
            try:
                snapshots.append(RunSnapshot(**json.loads(state_path.read_text(encoding="utf-8"))))
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                continue
        return sorted(snapshots, key=lambda snapshot: snapshot.updated_at, reverse=True)

    def get_quotation_results(self, run_id: str) -> dict[str, object]:
        """Return submitted quote tables together with their calculated prices."""
        run_dir = self._run_dir(run_id)
        calculation_payload = self._read_json(run_dir / "quotation_results.json")
        if not isinstance(calculation_payload, dict):
            return {"items": []}

        calculations = calculation_payload.get("items")
        if not isinstance(calculations, list):
            return {"items": []}

        quote_tables = self._read_quote_tables(run_dir)
        items: list[dict[str, object]] = []
        for calculation in calculations:
            if not isinstance(calculation, dict):
                continue
            quote_id = calculation.get("quote_id")
            if not isinstance(quote_id, str) or quote_id not in quote_tables:
                continue
            manual_snapshot = self._latest_manual_snapshot(run_dir, quote_id)
            if manual_snapshot is not None:
                quotation = manual_snapshot.get("quotation")
                if isinstance(quotation, dict):
                    items.append(quotation)
                    continue
            table = quote_tables[quote_id]
            if (
                "eligible_devices" not in calculation
                or "specification_options" not in calculation
                or "standard_type" not in calculation
                or "test_item" not in calculation
            ):
                calculation = self._quotation_processor.quote_values(
                    quote_id,
                    table.test_project_id,
                    table.values.fixed_fields,
                    table.values.special_fields,
                ).to_dict()
            items.append(
                self._quotation_item(
                    quote_id,
                    table.test_project_id,
                    table.values.fixed_fields,
                    table.values.special_fields,
                    calculation,
                )
            )
        return {"items": items}

    def recalculate_quotation(
        self,
        run_id: str,
        quote_id: str,
        test_project_id: int | None,
        fixed_fields: dict[str, object],
        special_fields: dict[str, object],
        selected_device_code: str | None = None,
        base_fee_override: Decimal | None = None,
    ) -> dict[str, object]:
        return self.save_quotation_snapshot(
            run_id,
            quote_id,
            test_project_id,
            fixed_fields,
            special_fields,
            selected_device_code,
            base_fee_override,
        )

    def save_quotation_snapshot(
        self,
        run_id: str,
        quote_id: str,
        test_project_id: int | None,
        fixed_fields: dict[str, object],
        special_fields: dict[str, object],
        selected_device_code: str | None = None,
        base_fee_override: Decimal | None = None,
    ) -> dict[str, object]:
        run_dir = self._run_dir(run_id)
        quote_tables = self._read_quote_tables(run_dir)
        if quote_id not in quote_tables:
            raise KeyError(quote_id)
        result = self._quotation_processor.quote_values(
            quote_id,
            test_project_id,
            fixed_fields,
            special_fields,
            selected_device_code,
        )
        calculation = result.to_dict()
        if base_fee_override is not None:
            calculation["base_fee"] = float(base_fee_override)
            calculation["amount"] = self._amount_with_base_fee_override(
                base_fee_override,
                calculation.get("unit_price"),
                fixed_fields.get("pricing_quantity"),
            )
        quotation = self._quotation_item(
            quote_id,
            test_project_id,
            fixed_fields,
            special_fields,
            calculation,
            base_fee_override,
        )
        snapshot_id = self._new_quotation_snapshot_id()
        snapshot = {
            "id": snapshot_id,
            "quote_id": quote_id,
            "created_at": datetime.now(UTC).isoformat(),
            "quotation": quotation,
        }
        snapshot_path = self._manual_snapshot_directory(run_dir, quote_id) / f"quotation_snapshot_{snapshot_id}.json"
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        return quotation

    def set_all_quotation_base_fee_overrides(
        self,
        run_id: str,
        base_fee_override: Decimal | None,
    ) -> dict[str, object]:
        result_items = self.get_quotation_results(run_id).get("items", [])
        if not isinstance(result_items, list):
            return {"items": []}
        for item in result_items:
            if not isinstance(item, dict):
                continue
            quote_id = item.get("quote_id")
            fixed_fields = item.get("fixed_fields")
            special_fields = item.get("special_fields")
            if not isinstance(quote_id, str) or not isinstance(fixed_fields, dict) or not isinstance(special_fields, dict):
                continue
            test_project_id = item.get("test_project_id")
            self.save_quotation_snapshot(
                run_id,
                quote_id,
                test_project_id if isinstance(test_project_id, int) else None,
                fixed_fields,
                special_fields,
                item.get("selected_device_code") if isinstance(item.get("selected_device_code"), str) else None,
                base_fee_override,
            )
        return self.get_quotation_results(run_id)

    def export_quotation_document(self, run_id: str, *, quote_id: str = "") -> Path:
        run_dir = self._run_dir(run_id)
        result_items = self.get_quotation_results(run_id).get("items", [])
        if not isinstance(result_items, list):
            result_items = []
        if quote_id:
            result_items = [item for item in result_items if isinstance(item, dict) and item.get("quote_id") == quote_id]
        export_items = [item for item in result_items if isinstance(item, dict) and item.get("total_price") is not None]
        if not export_items:
            raise RuntimeError("no_quoted_items_to_export")

        safe_quote_id = re.sub(r"[^0-9A-Za-z_-]+", "_", quote_id).strip("_")
        output_name = f"报价单_{run_id}_{safe_quote_id}.docx" if safe_quote_id else f"报价单_{run_id}.docx"
        output_path = run_dir / output_name
        self._document_exporter.export(output_path, export_items)
        self._write_export_snapshot(run_dir, quote_id, export_items)
        self._append_exported_raw_test_types(export_items)
        return output_path

    def save_current_quotations_to_history(self, run_id: str) -> int:
        run_snapshot = self.get_run(run_id)
        run_dir = self._run_dir(run_id)
        result_items = self.get_quotation_results(run_id).get("items", [])
        if not isinstance(result_items, list):
            return 0

        quotations: list[HistoricalQuotation] = []
        for item in result_items:
            if not isinstance(item, dict):
                continue
            quote_id = item.get("quote_id")
            if not isinstance(quote_id, str) or not quote_id:
                continue
            fixed_fields = item.get("fixed_fields")
            special_fields = item.get("special_fields")
            if not isinstance(fixed_fields, dict) or not isinstance(special_fields, dict):
                continue
            manual_snapshot = self._latest_manual_snapshot(run_dir, quote_id)
            snapshot_id = manual_snapshot.get("id") if isinstance(manual_snapshot, dict) else None
            quotations.append(
                HistoricalQuotation(
                    quotation_run_id=run_id,
                    quote_id=quote_id,
                    source_snapshot_id=snapshot_id if isinstance(snapshot_id, str) else None,
                    source_file_name=run_snapshot.uploaded_file,
                    raw_test_type=fixed_fields.get("raw_test_type"),
                    test_project_id=item.get("test_project_id") if isinstance(item.get("test_project_id"), int) else None,
                    standard_type=fixed_fields.get("standard_type"),
                    test_item=fixed_fields.get("test_item"),
                    standard_code=fixed_fields.get("standard_code"),
                    standard_document_section=fixed_fields.get("standard_document_section"),
                    pricing_mode=fixed_fields.get("pricing_mode"),
                    specification=fixed_fields.get("specification"),
                    pricing_quantity=fixed_fields.get("pricing_quantity"),
                    sample_count=fixed_fields.get("sample_count"),
                    length_mm=fixed_fields.get("length_mm"),
                    width_mm=fixed_fields.get("width_mm"),
                    height_mm=fixed_fields.get("height_mm"),
                    special_fields=special_fields,
                    base_fee=item.get("base_fee"),
                    unit_price=item.get("unit_price"),
                    total_price=item.get("total_price"),
                    selected_device_code=item.get("selected_device_code"),
                    quotation_snapshot=item,
                )
            )
        return self._history_writer.save_historical_quotations(quotations)

    def accept_batch_submission(self, run_dir: Path, quote_tables: list[QuoteTableSubmission]) -> None:
        results = self._quotation_processor.quote_batch(quote_tables)
        destination = run_dir / "quotation_results.json"
        destination.write_text(
            json.dumps({"items": [result.to_dict() for result in results]}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _quotation_item(
        quote_id: str,
        test_project_id: int | None,
        submitted_fixed_fields: dict[str, object],
        special_fields: dict[str, object],
        calculation: dict[str, object],
        base_fee_override: Decimal | None = None,
    ) -> dict[str, object]:
        fixed_fields: dict[str, object] = {}
        standard_type = calculation.get("standard_type")
        test_item = calculation.get("test_item")
        for field_name, value in submitted_fixed_fields.items():
            fixed_fields[field_name] = value
            if field_name == "raw_test_type":
                fixed_fields["standard_type"] = standard_type
                fixed_fields["test_item"] = test_item
        if "raw_test_type" not in fixed_fields:
            fixed_fields["standard_type"] = standard_type
            fixed_fields["test_item"] = test_item
        for field_name in ("pricing_mode", "specification"):
            if calculation.get(field_name) is not None:
                fixed_fields[field_name] = calculation[field_name]
        quotation = {
            "quote_id": quote_id,
            "test_project_id": test_project_id,
            "fixed_fields": fixed_fields,
            "special_fields": dict(special_fields),
            "base_fee": calculation.get("base_fee"),
            "unit_price": calculation.get("unit_price"),
            "pricing_mode": fixed_fields.get("pricing_mode"),
            "pricing_quantity": fixed_fields.get("pricing_quantity"),
            "total_price": calculation.get("amount"),
            "selected_device_code": calculation.get("selected_device_code"),
            "eligible_devices": calculation.get("eligible_devices", []),
            "specification_options": calculation.get("specification_options", []),
        }
        if base_fee_override is not None:
            quotation["base_fee_override"] = float(base_fee_override)
        return quotation

    @staticmethod
    def _amount_with_base_fee_override(
        base_fee: Decimal,
        unit_price: object | None,
        pricing_quantity: object | None,
    ) -> float | None:
        if unit_price is None or pricing_quantity is None:
            return None
        return float(base_fee + Decimal(str(unit_price)) * Decimal(str(pricing_quantity)))

    def _write_schema(self, run_dir: Path) -> None:
        schema_path = run_dir / "quote_table.schema.json"
        schema_path.write_text(json.dumps(QuoteTable.model_json_schema(), ensure_ascii=False, indent=2), encoding="utf-8")

    def _write_snapshot(self, snapshot: RunSnapshot) -> None:
        state_path = self._state_path(snapshot.run_id)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    def _state_path(self, run_id: str) -> Path:
        return self._settings.core_runtime_root / run_id / "state.json"

    def _run_dir(self, run_id: str) -> Path:
        run_dir = (self._settings.agent_runs_root / run_id).resolve()
        if not run_dir.is_dir() or not run_dir.is_relative_to(self._settings.agent_runs_root.resolve()):
            raise KeyError(run_id)
        return run_dir

    def _next_run_id(self, file_name: str) -> str:
        label = self._safe_file_name(file_name).rsplit(".", 1)[0]
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        base = f"{label}_{timestamp}"
        candidate = base
        sequence = 2
        while (self._settings.agent_runs_root / candidate).exists():
            candidate = f"{base}_{sequence:02d}"
            sequence += 1
        return candidate

    @staticmethod
    def _safe_file_name(file_name: str) -> str:
        name = Path(file_name or "upload.xlsx").name
        name = re.sub(r"[^0-9A-Za-z._\-\u4e00-\u9fff]+", "_", name).strip("._")
        return name or "upload.xlsx"

    def _store_input_file(self, input_dir: Path, file_name: str, content: bytes) -> str:
        safe_name = self._safe_file_name(file_name)
        destination = input_dir / safe_name
        sequence = 2
        while destination.exists():
            stem, suffix = Path(safe_name).stem, Path(safe_name).suffix
            destination = input_dir / f"{stem}_{sequence}{suffix}"
            sequence += 1
        destination.write_bytes(content)
        return destination.name

    @staticmethod
    def _read_quote_tables(run_dir: Path) -> dict[str, QuoteTable]:
        quote_tables: dict[str, QuoteTable] = {}
        for quote_table_path in sorted((run_dir / "quotes").glob("*/quote_table.json")):
            payload = json.loads(quote_table_path.read_text(encoding="utf-8"))
            quote_tables[quote_table_path.parent.name] = QuoteTable.model_validate(payload)
        return quote_tables

    @staticmethod
    def _manual_snapshot_directory(run_dir: Path, quote_id: str) -> Path:
        return run_dir / "quotes" / quote_id / "snapshots"

    def _latest_manual_snapshot(self, run_dir: Path, quote_id: str) -> dict[str, object] | None:
        snapshot_paths = sorted(self._manual_snapshot_directory(run_dir, quote_id).glob("quotation_snapshot_*.json"))
        for snapshot_path in reversed(snapshot_paths):
            snapshot = self._read_json(snapshot_path)
            if isinstance(snapshot, dict):
                return snapshot
        return None

    def _write_export_snapshot(self, run_dir: Path, quote_id: str, items: list[dict[str, object]]) -> None:
        snapshot = {
            "id": self._new_quotation_snapshot_id(),
            "exported_at": datetime.now(UTC).isoformat(),
            "quote_id": quote_id or None,
            "items": items,
        }
        (run_dir / "quotation_results_output.json").write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _append_exported_raw_test_types(self, items: list[dict[str, object]]) -> None:
        aliases_by_project: dict[int, list[str]] = {}
        for item in items:
            test_project_id = item.get("test_project_id")
            fixed_fields = item.get("fixed_fields")
            if not isinstance(test_project_id, int) or not isinstance(fixed_fields, dict):
                continue
            raw_test_type = fixed_fields.get("raw_test_type")
            if not isinstance(raw_test_type, str) or not raw_test_type.strip():
                continue
            aliases_by_project.setdefault(test_project_id, []).append(raw_test_type.strip())
        self._alias_writer.append_test_project_aliases(
            {project_id: tuple(aliases) for project_id, aliases in aliases_by_project.items()}
        )

    @staticmethod
    def _read_json(path: Path) -> object | None:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    @staticmethod
    def _new_snapshot(run_id: str, status: str, uploaded_file: str) -> RunSnapshot:
        now = datetime.now(UTC).isoformat()
        return RunSnapshot(run_id, status, uploaded_file, now, now)

    @staticmethod
    def _new_quotation_snapshot_id() -> str:
        return f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}_{uuid4().hex[:8]}"

    @staticmethod
    def _replace(snapshot: RunSnapshot, *, status: str, agent_return_code: int | None = None) -> RunSnapshot:
        return RunSnapshot(
            run_id=snapshot.run_id,
            status=status,
            uploaded_file=snapshot.uploaded_file,
            created_at=snapshot.created_at,
            updated_at=datetime.now(UTC).isoformat(),
            agent_return_code=agent_return_code if agent_return_code is not None else snapshot.agent_return_code,
        )

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from pathlib import Path

from packages.core.logging_utils import append_run_log
from packages.integrations.catalog import CatalogGateway
from packages.integrations.qwen_requester import QwenRequester
from packages.integrations.settings import get_settings
from packages.integrations.standard_context_judge import StandardContextJudge
from packages.integrations.standard_library import StandardLibrary
from packages.integrations.standard_retrieval_module import StandardRetrievalModule
from packages.plugins.registry import PluginRegistry

from .form_ops import apply_manual_values, merge_rows
from .kernel import LocalKernel
from .models import FormRow, FormStageSnapshot, ResumeRequest, RunArtifacts, RunState, UploadedDocument
from .quoter import Quoter
from .run_store import RunStore
from .stages import (
    DOCUMENT_EXTRACTED,
    EQUIPMENT_SELECTED,
    FINAL_QUOTED,
    STAGE_LABELS,
    STANDARD_ENRICHED,
    TEST_TYPE_MATCHED,
)


def _copy_rows(rows: list[FormRow]) -> list[FormRow]:
    return [row.model_copy(deep=True) for row in rows]


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class QuoteOrchestrator:
    registry: PluginRegistry = field(default_factory=PluginRegistry)
    store: RunStore = field(default_factory=RunStore)
    settings: object = field(default_factory=get_settings)
    catalog: CatalogGateway = field(default_factory=CatalogGateway)
    standards: StandardLibrary = field(default_factory=StandardLibrary)
    standard_module: StandardRetrievalModule = field(default_factory=StandardRetrievalModule)
    requester: QwenRequester = field(default_factory=QwenRequester)
    kernel: LocalKernel = field(init=False)
    quoter: Quoter = field(init=False)

    def __post_init__(self) -> None:
        self.standard_module.bind_judge(StandardContextJudge(requester=self.requester))
        self.kernel = LocalKernel(catalog=self.catalog, standards=self.standards, standard_module=self.standard_module)
        self.quoter = Quoter(catalog=self.catalog)

    def run(self, *, run_id: str, uploaded_documents: list[UploadedDocument]) -> RunState:
        run_dir = Path(str(self.settings.run_dir)) / run_id
        run_state_path = run_dir / "run_state.json"
        self._log(run_dir, "收到新运行请求，共 %s 个文件", len(uploaded_documents))
        state = RunState(
            run_id=run_id,
            current_stage="",
            overall_status="running",
            uploaded_documents=[doc.model_copy(deep=True) for doc in uploaded_documents],
            artifacts=RunArtifacts(
                run_state_path=str(run_state_path),
                uploaded_dir="",
                exported_files=[],
            ),
            next_action="系统正在处理文档",
        )
        self._save_state(run_state_path, state)

        try:
            self._log(run_dir, "开始文档预处理")
            documents, preprocess_notes = self._preprocess_documents(state, run_dir)
            self._log(run_dir, "文档解析完成，共 %s 份标准化文档", len(documents))
            extraction = self.requester.extract_form(documents, run_dir=run_dir)
            rows = extraction.items
            stage_notes = list(preprocess_notes)
            if extraction.summary:
                stage_notes.append(f"模型摘要：{extraction.summary}")
            self._upsert_stage(state, DOCUMENT_EXTRACTED, rows, stage_notes)
            self._log(run_dir, "文件抽取阶段完成，共 %s 行", len(rows))
            self._save_state(run_state_path, state)

            rows, notes = self.kernel.match_test_types(rows)
            self._upsert_stage(state, TEST_TYPE_MATCHED, rows, notes)
            self._log(run_dir, "实验类型匹配完成，共 %s 行", len(rows))
            self._save_state(run_state_path, state)

            rows, notes = self.quoter.select_equipment(rows)
            self._upsert_stage(state, EQUIPMENT_SELECTED, rows, notes)
            self._log(run_dir, "设备筛选完成，共 %s 行", len(rows))
            self._save_state(run_state_path, state)

            rows = self._run_standard_stage(state, rows, run_dir)
            self._log(run_dir, "标准补充阶段完成，共 %s 行", len(rows))
            self._save_state(run_state_path, state)

            rows, notes = self.quoter.select_equipment(rows)
            self._upsert_stage(state, EQUIPMENT_SELECTED, rows, ["标准补充后重新筛选设备", *notes])
            self._log(run_dir, "标准补充后设备筛选完成，共 %s 行", len(rows))
            self._save_state(run_state_path, state)

            rows, notes, overall_status = self.quoter.price(rows)
            self._upsert_stage(state, FINAL_QUOTED, rows, notes)
            state.final_form_items = _copy_rows(rows)
            state.current_stage = FINAL_QUOTED
            state.overall_status = overall_status
            state.next_action = self._next_action_for_status(overall_status)
            self._log(run_dir, "最终报价阶段完成，状态=%s，行数=%s", overall_status, len(rows))
            self._save_state(run_state_path, state)
            return state
        except Exception as exc:
            state.overall_status = "failed"
            state.errors.append(str(exc))
            state.next_action = "检查错误信息后重新上传文档"
            self._log(run_dir, "运行失败: %s", str(exc), level=logging.ERROR)
            self._save_state(run_state_path, state)
            return state

    def resume(self, *, run_id: str, request: ResumeRequest) -> RunState:
        run_dir = Path(str(self.settings.run_dir)) / run_id
        run_state_path = run_dir / "run_state.json"
        state = self.store.load(run_state_path)
        self._log(run_dir, "收到人工补录继续报价请求: row_id=%s", request.row_id)
        rows = apply_manual_values(state.final_form_items or self._stage_items(state, FINAL_QUOTED), request.row_id, request.field_values)

        try:
            rows, match_notes = self.kernel.match_test_types(rows)
            self._upsert_stage(state, TEST_TYPE_MATCHED, rows, ["用户补录后重新匹配试验类型", *match_notes])
            self._log(run_dir, "人工补录后试验类型匹配完成，共 %s 行", len(rows))

            rows, equipment_notes = self.quoter.select_equipment(rows)
            self._upsert_stage(state, EQUIPMENT_SELECTED, rows, ["用户补录后重新筛选设备", *equipment_notes])
            self._log(run_dir, "人工补录后设备筛选完成，共 %s 行", len(rows))

            rows = self._run_standard_stage(state, rows, run_dir)
            self._log(run_dir, "人工补录后标准补充完成，共 %s 行", len(rows))

            rows, equipment_notes = self.quoter.select_equipment(rows)
            self._upsert_stage(state, EQUIPMENT_SELECTED, rows, ["标准补充后重新筛选设备", *equipment_notes])
            self._log(run_dir, "人工补录后标准补充后设备筛选完成，共 %s 行", len(rows))

            rows, quote_notes, overall_status = self.quoter.price(rows)
            self._upsert_stage(state, FINAL_QUOTED, rows, ["用户补录后重新报价", *quote_notes])
            state.final_form_items = _copy_rows(rows)
            state.current_stage = FINAL_QUOTED
            state.overall_status = overall_status
            state.next_action = self._next_action_for_status(overall_status)
            self._log(run_dir, "人工补录后重新报价完成，状态=%s，行数=%s", overall_status, len(rows))
            self._save_state(run_state_path, state)
            return state
        except Exception as exc:
            state.overall_status = "failed"
            state.errors.append(str(exc))
            state.next_action = "人工补录后重新报价失败，请检查输入"
            self._log(run_dir, "人工补录后重新报价失败: %s", str(exc), level=logging.ERROR)
            self._save_state(run_state_path, state)
            return state

    def load_run(self, run_id: str) -> RunState:
        return self.store.load(Path(str(self.settings.run_dir)) / run_id / "run_state.json")

    def _preprocess_documents(self, state: RunState, run_dir: Path) -> tuple[list, list[str]]:
        documents = []
        notes: list[str] = []
        for uploaded in state.uploaded_documents:
            source_path = uploaded.local_path or uploaded.stored_path
            path = Path(source_path)
            plugin = self.registry.resolve(path)
            self._log(run_dir, "文档路由完成: %s -> %s", uploaded.file_name, plugin.plugin_id)
            normalized = plugin.preprocess(path, {"run_dir": run_dir})
            uploaded.source_kind = normalized.source_kind
            uploaded.status = "preprocessed"
            uploaded.notes = f"plugin={plugin.plugin_id}"
            documents.append(normalized)
            notes.append(f"{uploaded.file_name}: routed to {plugin.plugin_id}")
            self._log(run_dir, "文档预处理完成: %s | blocks=%s | assets=%s", uploaded.file_name, len(normalized.text_blocks), len(normalized.assets))
        return documents, notes

    def _run_standard_stage(self, state: RunState, rows: list[FormRow], run_dir: Path) -> list[FormRow]:
        target_fields_by_row = {
            row.row_id: self.quoter.standard_fillable_missing_fields(row)
            for row in rows
            if row.standard_codes and self.quoter.standard_fillable_missing_fields(row)
        }
        if not target_fields_by_row:
            notes = ["设备筛选后无可由标准补充的缺失字段，跳过标准补充"]
            self._upsert_stage(state, STANDARD_ENRICHED, rows, notes)
            self._log(run_dir, "设备筛选后无可由标准补充的缺失字段")
            return rows

        rows, attach_notes = self.kernel.attach_standard_refs(rows)
        notes: list[str] = list(attach_notes)
        rows, evidence_notes = self.kernel.resolve_standard_evidences(
            rows,
            target_fields_by_row=target_fields_by_row,
            run_dir=str(run_dir),
        )
        notes.extend(evidence_notes)
        candidate_rows = [row for row in rows if target_fields_by_row.get(row.row_id) and row.standard_evidences]
        if candidate_rows:
            rows, round_notes = self._progressive_standard_enrich(
                rows,
                target_fields_by_row=target_fields_by_row,
                run_dir=run_dir,
            )
            notes.extend(round_notes)
            self._log(run_dir, "标准证据补表完成，当前共 %s 行", len(rows))
        elif any(target_fields_by_row.values()):
            notes.append("存在标准补充目标字段，但未命中可用标准证据，按当前信息继续报价")
            self._log(run_dir, "存在标准补充目标字段，但未命中可用标准证据")
        else:
            notes.append("未命中有效标准证据，按当前信息继续报价")
            self._log(run_dir, "未命中有效标准证据，按当前信息继续报价")

        self._upsert_stage(state, STANDARD_ENRICHED, rows, notes)
        return rows

    def _progressive_standard_enrich(
        self,
        rows: list[FormRow],
        *,
        target_fields_by_row: dict[str, list[str]],
        run_dir: Path,
    ) -> tuple[list[FormRow], list[str]]:
        current_rows = [row.model_copy(deep=True) for row in rows]
        remaining_by_row = {
            row_id: list(fields)
            for row_id, fields in target_fields_by_row.items()
            if fields
        }
        notes: list[str] = []
        max_scope_count = max((len(row.standard_evidences) for row in current_rows), default=0)

        for scope_index in range(max_scope_count):
            request_rows: list[FormRow] = []
            request_targets: dict[str, list[str]] = {}
            before_by_row: dict[str, FormRow] = {}

            for row in current_rows:
                remaining = remaining_by_row.get(row.row_id) or []
                if not remaining:
                    continue
                if scope_index >= len(row.standard_evidences):
                    continue
                scoped_row = row.model_copy(deep=True)
                scoped_row.standard_evidences = [row.standard_evidences[scope_index].model_copy(deep=True)]
                request_rows.append(scoped_row)
                request_targets[row.row_id] = list(remaining)
                before_by_row[row.row_id] = row.model_copy(deep=True)

            if not request_rows:
                break

            scope_label = request_rows[0].standard_evidences[0].section_id if len(request_rows) == 1 else f"round-{scope_index + 1}"
            self._log(
                run_dir,
                "开始标准证据补表: round=%s rows=%s target_fields=%s",
                scope_label,
                len(request_rows),
                sum(len(fields) for fields in request_targets.values()),
            )
            result = self.requester.enrich_form_with_evidences(
                request_rows,
                target_fields_by_row=request_targets,
                run_dir=run_dir,
            )
            current_rows = merge_rows(current_rows, result.items)
            if result.summary:
                notes.append(f"第{scope_index + 1}轮模型摘要：{result.summary}")

            after_index = {row.row_id: row for row in current_rows}
            for row_id, remaining in list(remaining_by_row.items()):
                before_row = before_by_row.get(row_id)
                after_row = after_index.get(row_id)
                if before_row is None or after_row is None:
                    continue
                filled = self._newly_filled_fields(before_row, after_row, remaining)
                if filled:
                    remaining_by_row[row_id] = [field for field in remaining if field not in filled]
                    notes.append(f"{row_id}: 第{scope_index + 1}轮已补字段 {', '.join(filled)}")
                else:
                    notes.append(f"{row_id}: 第{scope_index + 1}轮未补出新字段")
                if not remaining_by_row.get(row_id):
                    notes.append(f"{row_id}: 标准补充目标字段已全部覆盖")

            if all(not fields for fields in remaining_by_row.values()):
                notes.append("标准补充已覆盖全部目标字段，提前结束范围扩展")
                break

        unresolved = {row_id: fields for row_id, fields in remaining_by_row.items() if fields}
        for row_id, fields in unresolved.items():
            notes.append(f"{row_id}: 范围扩展结束后仍缺字段 {', '.join(fields)}")
        return current_rows, notes

    def _stage_items(self, state: RunState, stage_id: str) -> list[FormRow]:
        for stage in state.form_stages:
            if stage.stage_id == stage_id:
                return _copy_rows(stage.items)
        return []

    def _upsert_stage(self, state: RunState, stage_id: str, rows: list[FormRow], notes: list[str]) -> None:
        snapshot = FormStageSnapshot(
            stage_id=stage_id,
            label=STAGE_LABELS[stage_id],
            items=_copy_rows(rows),
            notes=[note for note in notes if note],
        )
        for index, stage in enumerate(state.form_stages):
            if stage.stage_id == stage_id:
                state.form_stages[index] = snapshot
                state.current_stage = stage_id
                return
        state.form_stages.append(snapshot)
        state.current_stage = stage_id

    def _save_state(self, path: Path, state: RunState) -> None:
        self.store.save(path, state)

    def _log(self, run_dir: Path, message: str, *args: object, level: int = logging.INFO) -> None:
        text = message % args if args else message
        logger.log(level, "[run=%s] %s", run_dir.name, text)
        append_run_log(run_dir, text)

    def _next_action_for_status(self, status: str) -> str:
        if status == "completed":
            return "查看最终报价表或下载产物"
        if status == "waiting_manual_input":
            return "补齐表格中的缺失字段后继续报价"
        return "检查系统错误后重试"

    def _newly_filled_fields(
        self,
        before_row: FormRow,
        after_row: FormRow,
        candidate_fields: list[str],
    ) -> list[str]:
        filled: list[str] = []
        for field_name in candidate_fields:
            before_value = getattr(before_row, field_name, None)
            after_value = getattr(after_row, field_name, None)
            if self._has_value(after_value) and not self._has_value(before_value):
                filled.append(field_name)
        return filled

    def _has_value(self, value: object) -> bool:
        return value not in (None, "", [])

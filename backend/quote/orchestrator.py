from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from backend.common.logging import append_run_log
from backend.quote.catalog import CatalogGateway
from backend.quote.form_ops import apply_manual_values
from backend.quote.kernel import Kernel
from backend.quote.llm.requester import QwenRequester
from backend.quote.models import FormRow, FormStageSnapshot, ResumeRequest, RunArtifacts, RunState, UploadedDocument
from backend.quote.plugins.registry import PluginRegistry
from backend.quote.quoter import Quoter
from backend.quote.run_store import RunStore
from backend.quote.stages import (
    DOCUMENT_EXTRACTED,
    EQUIPMENT_SELECTED_ENRICHED,
    EQUIPMENT_SELECTED_INITIAL,
    FINAL_QUOTED,
    STAGE_LABELS,
    STANDARD_ENRICHED,
    TEST_TYPE_MATCHED,
)
from backend.quote.standard.judge import StandardContextJudge
from backend.quote.standard.module import StandardRetrievalModule
from backend.quote.standard_enrich import progressive_enrich


logger = logging.getLogger(__name__)


def _copy(rows: list[FormRow]) -> list[FormRow]:
    return [r.model_copy(deep=True) for r in rows]


@dataclass(slots=True)
class QuoteOrchestrator:
    registry: PluginRegistry = field(default_factory=PluginRegistry)
    store: RunStore = field(default_factory=RunStore)
    catalog: CatalogGateway = field(default_factory=CatalogGateway)
    requester: QwenRequester = field(default_factory=QwenRequester)
    kernel: Kernel = field(init=False)
    quoter: Quoter = field(init=False)

    def __post_init__(self) -> None:
        judge = StandardContextJudge(requester=self.requester)
        retrieval = StandardRetrievalModule(judge=judge)
        self.kernel = Kernel(catalog=self.catalog, retrieval=retrieval)
        self.quoter = Quoter(catalog=self.catalog)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def run(self, *, run_id: str, uploaded_documents: list[UploadedDocument]) -> RunState:
        from backend.quote.settings import get_settings
        run_dir = get_settings().run_dir / run_id
        run_state_path = run_dir / "run_state.json"
        self._log(run_dir, "收到新运行请求，共 %s 个文件", len(uploaded_documents))

        state = RunState(
            run_id=run_id,
            overall_status="running",
            uploaded_documents=[d.model_copy(deep=True) for d in uploaded_documents],
            artifacts=RunArtifacts(
                run_state_path=str(run_state_path),
                uploaded_dir=str(run_dir / "uploaded"),
            ),
            next_action="系统正在处理文档",
        )
        self._save(run_state_path, state)

        try:
            documents, preprocess_notes = self._preprocess(state, run_dir)
            self._log(run_dir, "文档解析完成，共 %s 份", len(documents))

            extraction = self.requester.extract_form(documents, run_dir=run_dir)
            rows = extraction.items
            notes = list(preprocess_notes)
            if extraction.summary:
                notes.append(f"模型摘要：{extraction.summary}")
            self._upsert(state, DOCUMENT_EXTRACTED, rows, notes)
            self._log(run_dir, "文件抽取完成，共 %s 行", len(rows))
            self._save(run_state_path, state)

            rows, notes = self.kernel.match_test_types(rows)
            self._upsert(state, TEST_TYPE_MATCHED, rows, notes)
            self._log(run_dir, "试验类型匹配完成，共 %s 行", len(rows))
            self._save(run_state_path, state)

            rows, planning_notes = self.quoter.plan_standard_fields(rows)
            rows, notes = self.quoter.select_equipment(rows)
            self._upsert(state, EQUIPMENT_SELECTED_INITIAL, rows, [*planning_notes, *notes])
            self._log(run_dir, "设备筛选完成，共 %s 行", len(rows))
            self._save(run_state_path, state)

            rows = self._standard_stage(state, rows, run_dir)
            self._log(run_dir, "标准补充完成，共 %s 行", len(rows))
            self._save(run_state_path, state)

            rows, notes = self.quoter.select_equipment(rows)
            rows, repeat_notes = self.quoter.assign_repeat_counts(rows)
            self._upsert(state, EQUIPMENT_SELECTED_ENRICHED, rows, ["标准补充后重新筛选设备", *notes, *repeat_notes])
            self._log(run_dir, "标准补充后设备筛选完成，共 %s 行", len(rows))
            self._save(run_state_path, state)

            rows, notes, status = self.quoter.price(rows)
            self._upsert(state, FINAL_QUOTED, rows, notes)
            state.final_form_items = _copy(rows)
            state.current_stage = FINAL_QUOTED
            state.overall_status = status
            state.next_action = self._next_action(status)
            self._log(run_dir, "最终报价完成，状态=%s，行数=%s", status, len(rows))
            self._save(run_state_path, state)
        except Exception as exc:
            state.overall_status = "failed"
            state.errors.append(str(exc))
            state.next_action = "检查错误信息后重新上传文档"
            self._log(run_dir, "运行失败: %s", str(exc), level=logging.ERROR)
            self._save(run_state_path, state)

        return state

    def resume(self, *, run_id: str, request: ResumeRequest) -> RunState:
        from backend.quote.settings import get_settings
        run_dir = get_settings().run_dir / run_id
        run_state_path = run_dir / "run_state.json"
        state = self.store.load(run_state_path)
        self._log(run_dir, "收到人工补录继续报价请求: row_id=%s", request.row_id)

        test_type_changed = "canonical_test_type" in request.field_values
        base_rows = state.final_form_items or self._stage_rows(state, FINAL_QUOTED)
        if not test_type_changed:
            base_rows = self._stage_rows(state, STANDARD_ENRICHED) or base_rows
        rows = apply_manual_values(base_rows, request.row_id, request.field_values)
        try:
            if test_type_changed:
                rows, notes = self.kernel.match_test_types(rows)
                self._upsert(state, TEST_TYPE_MATCHED, rows, ["用户补录后重新匹配试验类型", *notes])

                rows, planning_notes = self.quoter.plan_standard_fields(rows)
                rows, notes = self.quoter.select_equipment(rows)
                self._upsert(state, EQUIPMENT_SELECTED_INITIAL, rows, ["用户补录后重新筛选设备", *planning_notes, *notes])

                rows = self._standard_stage(state, rows, run_dir)
            else:
                rows = self._clear_equipment_state(rows)
                self._upsert(
                    state,
                    STANDARD_ENRICHED,
                    rows,
                    ["用户补录未修改标准试验类型，复用已有标准补充结果，跳过标准文档检索"],
                )

            rows, notes = self.quoter.select_equipment(rows)
            rows, repeat_notes = self.quoter.assign_repeat_counts(rows)
            self._upsert(state, EQUIPMENT_SELECTED_ENRICHED, rows, ["标准补充后重新筛选设备", *notes, *repeat_notes])

            rows, notes, status = self.quoter.price(rows)
            self._upsert(state, FINAL_QUOTED, rows, ["用户补录后重新报价", *notes])
            state.final_form_items = _copy(rows)
            state.current_stage = FINAL_QUOTED
            state.overall_status = status
            state.next_action = self._next_action(status)
            self._save(run_state_path, state)
        except Exception as exc:
            state.overall_status = "failed"
            state.errors.append(str(exc))
            state.next_action = "人工补录后重新报价失败，请检查输入"
            self._log(run_dir, "人工补录后重新报价失败: %s", str(exc), level=logging.ERROR)
            self._save(run_state_path, state)

        return state

    def load_run(self, run_id: str) -> RunState:
        from backend.quote.settings import get_settings
        return self.store.load(get_settings().run_dir / run_id / "run_state.json")

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _preprocess(self, state: RunState, run_dir: Path) -> tuple[list, list[str]]:
        documents, notes = [], []
        for uploaded in state.uploaded_documents:
            path = Path(uploaded.local_path or uploaded.stored_path)
            plugin = self.registry.resolve(path)
            self._log(run_dir, "文档路由: %s -> %s", uploaded.file_name, plugin.plugin_id)
            normalized = plugin.preprocess(path, {"run_dir": run_dir})
            uploaded.source_kind = normalized.source_kind
            uploaded.status = "preprocessed"
            uploaded.notes = f"plugin={plugin.plugin_id}"
            documents.append(normalized)
            notes.append(f"{uploaded.file_name}: routed to {plugin.plugin_id}")
        return documents, notes

    def _standard_stage(self, state: RunState, rows: list[FormRow], run_dir: Path) -> list[FormRow]:
        rows = self._clear_standard_discovery_state(rows)
        target_by_row = {
            row.row_id: list(row.planned_standard_fields)
            for row in rows
            if row.standard_codes and row.planned_standard_fields
        }
        if not target_by_row:
            rows = self._clear_equipment_state(rows)
            self._upsert(state, STANDARD_ENRICHED, rows, ["无标准补充模板字段或缺少标准号，跳过标准补充"])
            return rows

        rows, evidence_notes = self.kernel.resolve_standard_evidences(rows, target_fields_by_row=target_by_row, run_dir=run_dir)
        notes = list(evidence_notes)

        candidate_rows = [r for r in rows if target_by_row.get(r.row_id) and r.standard_evidences]
        if candidate_rows:
            discovery = self.requester.discover_standard_fields(
                candidate_rows,
                target_fields_by_row=target_by_row,
                supported_fields=self.quoter.supported_standard_fields(),
                run_dir=run_dir,
            )
            if discovery.summary:
                notes.append(f"字段发现摘要：{discovery.summary}")
            rows = self._apply_standard_discovery(rows, discovery.items)
            notes.extend(self._discovery_notes(rows, discovery.items))

            fill_targets_by_row = {
                row.row_id: [
                    field_name
                    for field_name in row.discovered_standard_fields
                    if not _has_value(getattr(row, field_name, None))
                ]
                for row in rows
                if row.row_id in target_by_row
            }
            fill_targets_by_row = {row_id: fields for row_id, fields in fill_targets_by_row.items() if fields}

            if fill_targets_by_row:
                rows, enrich_notes = progressive_enrich(
                    rows, target_fields_by_row=fill_targets_by_row, requester=self.requester, run_dir=run_dir
                )
                notes.extend(enrich_notes)
            else:
                notes.append("字段发现未产出新的待补值字段，跳过标准补值")
        elif any(target_by_row.values()):
            notes.append("存在标准补充目标字段，但未命中可用标准证据，按当前信息继续报价")
        else:
            notes.append("未命中有效标准证据，按当前信息继续报价")

        rows = self._clear_equipment_state(rows)
        self._upsert(state, STANDARD_ENRICHED, rows, notes)
        return rows

    def _apply_standard_discovery(
        self,
        rows: list[FormRow],
        items,
    ) -> list[FormRow]:
        discovery_by_row = {item.row_id: item for item in items}
        updated: list[FormRow] = []
        for row in rows:
            copy = row.model_copy(deep=True)
            copy.discovered_standard_fields = []
            copy.extra_standard_requirements = []
            result = discovery_by_row.get(row.row_id)
            if result is None:
                updated.append(copy)
                continue
            copy.discovered_standard_fields = list(result.discovered_standard_fields)
            copy.extra_standard_requirements = [item.model_copy(deep=True) for item in result.extra_standard_requirements]
            updated.append(copy)
        return updated

    def _clear_standard_discovery_state(self, rows: list[FormRow]) -> list[FormRow]:
        updated: list[FormRow] = []
        for row in rows:
            copy = row.model_copy(deep=True)
            copy.discovered_standard_fields = []
            copy.extra_standard_requirements = []
            copy.standard_evidences = []
            copy.standard_match_notes = []
            updated.append(copy)
        return updated

    def _clear_equipment_state(self, rows: list[FormRow]) -> list[FormRow]:
        updated: list[FormRow] = []
        for row in rows:
            copy = row.model_copy(deep=True)
            copy.candidate_equipment_ids = []
            copy.candidate_equipment_profiles = []
            copy.selected_equipment_id = ""
            copy.rejected_equipment = []
            copy.missing_fields = []
            copy.blocking_reason = ""
            updated.append(copy)
        return updated

    def _discovery_notes(self, rows: list[FormRow], items) -> list[str]:
        rows_by_id = {row.row_id: row for row in rows}
        notes: list[str] = []
        for item in items:
            row = rows_by_id.get(item.row_id)
            label = (row.raw_test_type or row.canonical_test_type or item.row_id) if row else item.row_id
            if item.discovered_standard_fields:
                notes.append(f"{label}: 发现标准字段 {', '.join(item.discovered_standard_fields)}")
            else:
                notes.append(f"{label}: 未发现新的系统支持字段")
            if item.extra_standard_requirements:
                notes.append(f"{label}: 记录额外标准要求 {len(item.extra_standard_requirements)} 条")
        return notes

    def _upsert(self, state: RunState, stage_id: str, rows: list[FormRow], notes: list[str]) -> None:
        snapshot = FormStageSnapshot(
            stage_id=stage_id,
            label=STAGE_LABELS[stage_id],
            items=_copy(rows),
            notes=[n for n in notes if n],
        )
        for i, stage in enumerate(state.form_stages):
            if stage.stage_id == stage_id:
                state.form_stages[i] = snapshot
                state.current_stage = stage_id
                return
        state.form_stages.append(snapshot)
        state.current_stage = stage_id

    def _stage_rows(self, state: RunState, stage_id: str) -> list[FormRow]:
        for stage in state.form_stages:
            if stage.stage_id == stage_id:
                return _copy(stage.items)
        return []

    def _save(self, path: Path, state: RunState) -> None:
        self.store.save(path, state)

    def _log(self, run_dir: Path, message: str, *args: object, level: int = logging.INFO) -> None:
        text = message % args if args else message
        logger.log(level, "[run=%s] %s", run_dir.name, text)
        append_run_log(run_dir, text)

    def _next_action(self, status: str) -> str:
        if status == "completed":
            return "查看最终报价表或下载产物"
        if status == "waiting_manual_input":
            return "补齐表格中的缺失字段后继续报价"
        return "检查系统错误后重试"


def _has_value(value: object) -> bool:
    return value not in (None, "", [])

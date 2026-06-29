from __future__ import annotations

import logging
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from docx import Document
from backend.common.config import PROJECT_ROOT
from backend.common.logging import append_run_log
from backend.common.models import NormalizedDocument
from backend.quote.batch_splitters import build_batch_splitter
from backend.quote.catalog import CatalogGateway
from backend.quote.document_enrich import (
    build_document_target_fields,
    document_enrichment_notes,
    merge_document_enrichment,
)
from backend.quote.form_ops import apply_manual_values, merge_extra_requirements
from backend.quote.kernel import Kernel
from backend.quote.llm.requester import QwenRequester
from backend.quote.models import BatchQuoteItem, FormRow, FormStageSnapshot, ResumeRequest, RunArtifacts, RunState, UploadedDocument
from backend.quote.plugins.registry import PluginRegistry
from backend.quote.quoter import Quoter
from backend.quote.row_adapters import DocumentExtractPayload, DocumentExtractRowAdapter, RowAdapterContext
from backend.quote.run_store import RunStore
from backend.quote.stages import (
    DOCUMENT_EXTRACTED,
    DOCUMENT_TARGETED_ENRICHED,
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

    def run(
        self,
        *,
        run_id: str,
        uploaded_documents: list[UploadedDocument],
        quote_mode: str = "single",
        batch_split_strategy: str = "",
    ) -> RunState:
        from backend.quote.settings import get_settings
        run_dir = get_settings().run_dir / run_id
        run_state_path = run_dir / "run_state.json"
        self._log(run_dir, "收到新运行请求，共 %s 个文件", len(uploaded_documents))

        state = RunState(
            run_id=run_id,
            quote_mode="batch" if quote_mode == "batch" else "single",
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
            if state.quote_mode == "batch":
                self._run_batch_pipeline(
                    state,
                    documents,
                    preprocess_notes,
                    run_dir,
                    run_state_path,
                    split_strategy=batch_split_strategy,
                )
            else:
                status = self._run_document_pipeline(
                    owner=state,
                    documents=documents,
                    run_dir=run_dir,
                    initial_notes=preprocess_notes,
                    save_path=run_state_path,
                    state=state,
                )
                state.overall_status = status
                state.next_action = self._next_action(status)
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

        if state.quote_mode == "batch":
            quote = self._find_batch_quote_for_row(state, request.row_id)
            if quote is None:
                raise RuntimeError(f"batch_quote_row_not_found:{request.row_id}")
            try:
                quote.status = self._resume_rows(owner=quote, run_dir=run_dir, request=request)
                quote.errors = []
                self._refresh_batch_summary(state)
                self._save(run_state_path, state)
            except Exception as exc:
                quote.status = "failed"
                quote.errors.append(str(exc))
                self._refresh_batch_summary(state)
                self._log(run_dir, "批量子报价人工补录后重新报价失败: quote_id=%s err=%s", quote.quote_id, str(exc), level=logging.ERROR)
                self._save(run_state_path, state)
            return state

        try:
            state.overall_status = self._resume_rows(owner=state, run_dir=run_dir, request=request)
            state.next_action = self._next_action(state.overall_status)
            self._save(run_state_path, state)
        except Exception as exc:
            state.overall_status = "failed"
            state.errors.append(str(exc))
            state.next_action = "人工补录后重新报价失败，请检查输入"
            self._log(run_dir, "人工补录后重新报价失败: %s", str(exc), level=logging.ERROR)
            self._save(run_state_path, state)

        return state

    def set_batch_quote_deleted(self, *, run_id: str, quote_id: str, deleted: bool) -> RunState:
        from backend.quote.settings import get_settings

        run_dir = get_settings().run_dir / run_id
        run_state_path = run_dir / "run_state.json"
        state = self.store.load(run_state_path)
        if state.quote_mode != "batch":
            raise RuntimeError("run_is_not_batch")

        quote = next((item for item in state.batch_quotes if item.quote_id == quote_id), None)
        if quote is None:
            raise KeyError("batch_quote_not_found")

        quote.is_deleted = deleted
        quote.deleted_at = datetime.now().isoformat() if deleted else ""
        self._refresh_batch_summary(state)
        self._save(run_state_path, state)
        self._log(run_dir, "批量子报价%s: quote_id=%s", "删除" if deleted else "恢复", quote_id)
        return state

    def _resume_rows(self, *, owner: RunState | BatchQuoteItem, run_dir: Path, request: ResumeRequest) -> str:
        test_type_changed = "canonical_test_type" in request.field_values
        base_rows = owner.final_form_items or self._stage_rows(owner, FINAL_QUOTED)
        if not test_type_changed:
            base_rows = self._stage_rows(owner, STANDARD_ENRICHED) or base_rows
        rows = apply_manual_values(base_rows, request.row_id, request.field_values)
        if test_type_changed:
            rows, notes = self.kernel.match_test_types(rows)
            self._upsert(owner, TEST_TYPE_MATCHED, rows, ["用户补录后重新匹配试验类型", *notes])

            rows, planning_notes = self.quoter.plan_standard_fields(rows)
            rows, notes = self.quoter.select_equipment(rows)
            self._upsert(owner, EQUIPMENT_SELECTED_INITIAL, rows, ["用户补录后重新筛选设备", *planning_notes, *notes])

            rows = self._standard_stage(owner, rows, run_dir)
        else:
            rows = self._clear_equipment_state(rows)
            self._upsert(
                owner,
                STANDARD_ENRICHED,
                rows,
                ["用户补录未修改标准试验类型，复用已有标准补充结果，跳过标准文档检索"],
            )

        rows, notes = self.quoter.select_equipment(rows)
        rows, repeat_notes = self.quoter.assign_repeat_counts(rows)
        self._upsert(owner, EQUIPMENT_SELECTED_ENRICHED, rows, ["标准补充后重新筛选设备", *notes, *repeat_notes])

        rows, notes, status = self.quoter.price(rows)
        self._upsert(owner, FINAL_QUOTED, rows, ["用户补录后重新报价", *notes])
        owner.final_form_items = _copy(rows)
        if isinstance(owner, RunState):
            owner.current_stage = FINAL_QUOTED
        return status

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

    def _run_batch_pipeline(
        self,
        state: RunState,
        documents: list,
        preprocess_notes: list[str],
        run_dir: Path,
        run_state_path: Path,
        *,
        split_strategy: str = "",
    ) -> None:
        from backend.quote.settings import get_settings

        if len(documents) != 1 or documents[0].source_kind != "excel":
            raise RuntimeError("batch_mode_requires_single_excel")
        workbook_path = Path(state.uploaded_documents[0].local_path or state.uploaded_documents[0].stored_path)
        settings = get_settings()
        strategy = split_strategy.strip() or settings.batch_split_strategy
        splitter = build_batch_splitter(strategy, requester=self.requester)
        self._log(run_dir, "批量切分策略: %s", splitter.strategy_id)
        split = splitter.split(workbook_path, run_dir=run_dir)
        if len(split.items) < 2:
            raise RuntimeError(
                "batch_excel_split_requires_multiple_chunks: 批量报价模式必须切分为多份同级报价，不能退化为单个报价或整表报价。"
            )
        notes = list(preprocess_notes)
        notes.extend(split.notes)
        if split.summary:
            notes.append(f"批量拆分摘要：{split.summary}")
        state.batch_quotes = [
            BatchQuoteItem(quote_id=item.quote_id, title=item.title, source_summary=item.source_summary)
            for item in split.items
        ]
        self._log(run_dir, "批量Excel拆分完成，共 %s 个子报价", len(state.batch_quotes))
        self._save(run_state_path, state)

        for split_item, quote in zip(split.items, state.batch_quotes, strict=False):
            quote.status = "running"
            self._save(run_state_path, state)
            try:
                row_result = split_item.row_adapter.to_rows(
                    split_item.row_payload,
                    context=RowAdapterContext(
                        requester=self.requester,
                        run_dir=run_dir,
                        test_type_options=self._test_type_options(),
                    ),
                )
                quote.status = self._run_rows_pipeline(
                    owner=quote,
                    rows=row_result.rows,
                    documents=row_result.documents,
                    run_dir=run_dir,
                    initial_notes=[*notes, *row_result.notes, f"子报价：{quote.title}", f"来源：{quote.source_summary}"],
                    quote_id=quote.quote_id,
                    quote_title=quote.title,
                    save_path=run_state_path,
                    state=state,
                )
                quote.errors = []
                self._log(run_dir, "批量子报价完成: quote_id=%s status=%s rows=%s", quote.quote_id, quote.status, len(quote.final_form_items))
            except Exception as exc:
                quote.status = "failed"
                quote.errors.append(str(exc))
                self._log(run_dir, "批量子报价失败: quote_id=%s err=%s", quote.quote_id, str(exc), level=logging.ERROR)
            self._refresh_batch_summary(state)
            self._save(run_state_path, state)

        self._refresh_batch_summary(state)
        self._save(run_state_path, state)

    def _run_document_pipeline(
        self,
        *,
        owner: RunState | BatchQuoteItem,
        documents: list,
        run_dir: Path,
        initial_notes: list[str],
        quote_id: str = "",
        quote_title: str = "",
        save_path: Path | None = None,
        state: RunState | None = None,
    ) -> str:
        row_result = DocumentExtractRowAdapter().to_rows(
            DocumentExtractPayload(documents=list(documents), notes=list(initial_notes)),
            context=RowAdapterContext(
                requester=self.requester,
                run_dir=run_dir,
                test_type_options=self._test_type_options(),
            ),
        )
        return self._run_rows_pipeline(
            owner=owner,
            rows=row_result.rows,
            documents=row_result.documents,
            run_dir=run_dir,
            initial_notes=row_result.notes,
            quote_id=quote_id,
            quote_title=quote_title,
            save_path=save_path,
            state=state,
        )

    def _run_rows_pipeline(
        self,
        *,
        owner: RunState | BatchQuoteItem,
        rows: list[FormRow],
        documents: list[NormalizedDocument],
        run_dir: Path,
        initial_notes: list[str],
        quote_id: str = "",
        quote_title: str = "",
        save_path: Path | None = None,
        state: RunState | None = None,
    ) -> str:
        from backend.quote.settings import get_settings

        settings = get_settings()
        rows = self._stamp_rows(rows, quote_id=quote_id, quote_title=quote_title)
        notes = list(initial_notes)
        self._upsert(owner, DOCUMENT_EXTRACTED, rows, notes)
        self._log(run_dir, "文件抽取完成，共 %s 行", len(rows))
        self._maybe_save(save_path, state)

        rows, notes = self.kernel.match_test_types(rows)
        rows = self._stamp_rows(rows, quote_id=quote_id, quote_title=quote_title)
        self._upsert(owner, TEST_TYPE_MATCHED, rows, notes)
        self._log(run_dir, "试验类型匹配完成，共 %s 行", len(rows))
        self._maybe_save(save_path, state)

        rows, planning_notes = self.quoter.plan_standard_fields(rows)
        if settings.document_targeted_enrich_enabled:
            rows = self._document_targeted_stage(owner, documents, rows, run_dir, planning_notes)
        else:
            self._upsert(owner, DOCUMENT_TARGETED_ENRICHED, rows, [*planning_notes, "配置已关闭：跳过文档定向补充"])
            self._log(run_dir, "文档定向补充已由配置关闭，共 %s 行", len(rows))
        rows = self._stamp_rows(rows, quote_id=quote_id, quote_title=quote_title)
        self._maybe_save(save_path, state)

        rows, notes = self.quoter.select_equipment(rows)
        rows = self._stamp_rows(rows, quote_id=quote_id, quote_title=quote_title)
        self._upsert(owner, EQUIPMENT_SELECTED_INITIAL, rows, notes)
        self._log(run_dir, "设备筛选完成，共 %s 行", len(rows))
        self._maybe_save(save_path, state)

        if settings.standard_enrich_enabled:
            rows = self._standard_stage(owner, rows, run_dir)
        else:
            self._upsert(owner, STANDARD_ENRICHED, rows, ["配置已关闭：跳过标准补充"])
            self._log(run_dir, "标准补充已由配置关闭，共 %s 行", len(rows))
        rows = self._stamp_rows(rows, quote_id=quote_id, quote_title=quote_title)
        self._log(run_dir, "标准补充完成，共 %s 行", len(rows))
        self._maybe_save(save_path, state)

        if settings.equipment_reselect_after_standard_enabled:
            rows, notes = self.quoter.select_equipment(rows)
            rows, repeat_notes = self.quoter.assign_repeat_counts(rows)
            rows = self._stamp_rows(rows, quote_id=quote_id, quote_title=quote_title)
            self._upsert(owner, EQUIPMENT_SELECTED_ENRICHED, rows, ["标准补充后重新筛选设备", *notes, *repeat_notes])
            self._log(run_dir, "标准补充后设备筛选完成，共 %s 行", len(rows))
            self._maybe_save(save_path, state)
        else:
            rows = self._stamp_rows(rows, quote_id=quote_id, quote_title=quote_title)
            self._upsert(owner, EQUIPMENT_SELECTED_ENRICHED, rows, ["配置已关闭：跳过标准补充后复筛阶段"])
            self._log(run_dir, "标准补充后复筛阶段已由配置关闭，共 %s 行", len(rows))
            self._maybe_save(save_path, state)

        rows, notes, status = self.quoter.price(rows)
        rows = self._stamp_rows(rows, quote_id=quote_id, quote_title=quote_title)
        self._upsert(owner, FINAL_QUOTED, rows, notes)
        owner.final_form_items = _copy(rows)
        if isinstance(owner, RunState):
            owner.current_stage = FINAL_QUOTED
        self._log(run_dir, "最终报价完成，状态=%s，行数=%s", status, len(rows))
        self._maybe_save(save_path, state)
        return status

    def _document_targeted_stage(
        self,
        owner: RunState | BatchQuoteItem,
        documents: list[NormalizedDocument],
        rows: list[FormRow],
        run_dir: Path,
        planning_notes: list[str],
    ) -> list[FormRow]:
        target_by_row = build_document_target_fields(rows)
        if not target_by_row:
            self._upsert(
                owner,
                DOCUMENT_TARGETED_ENRICHED,
                rows,
                [*planning_notes, "无文档定向补充目标字段，跳过文档二次抽取"],
            )
            self._log(run_dir, "文档定向补充跳过，无目标字段")
            return _copy(rows)

        result = self.requester.enrich_form_from_documents(
            documents,
            rows,
            target_fields_by_row=target_by_row,
            run_dir=run_dir,
        )
        enriched = merge_document_enrichment(rows, result.items, target_fields_by_row=target_by_row)
        notes = list(planning_notes)
        if result.summary:
            notes.append(f"模型摘要：{result.summary}")
        notes.extend(document_enrichment_notes(rows, enriched, target_fields_by_row=target_by_row))
        self._upsert(owner, DOCUMENT_TARGETED_ENRICHED, enriched, notes)
        self._log(run_dir, "文档定向补充完成，共 %s 行", len(enriched))
        return enriched

    def _test_type_options(self) -> list[str]:
        return [record.name for record in self.catalog.test_types]

    def _standard_stage(self, owner: RunState | BatchQuoteItem, rows: list[FormRow], run_dir: Path) -> list[FormRow]:
        rows = self._clear_standard_discovery_state(rows)
        target_by_row = {
            row.row_id: list(row.planned_standard_fields)
            for row in rows
            if row.standard_codes and row.planned_standard_fields
        }
        if not target_by_row:
            rows = self._clear_equipment_state(rows)
            self._upsert(owner, STANDARD_ENRICHED, rows, ["无标准补充模板字段或缺少标准号，跳过标准补充"])
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
        self._upsert(owner, STANDARD_ENRICHED, rows, notes)
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
            copy.extra_standard_requirements = merge_extra_requirements(
                copy.extra_standard_requirements,
                result.extra_standard_requirements,
            )
            updated.append(copy)
        return updated

    def _clear_standard_discovery_state(self, rows: list[FormRow]) -> list[FormRow]:
        updated: list[FormRow] = []
        for row in rows:
            copy = row.model_copy(deep=True)
            copy.discovered_standard_fields = []
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

    def _stamp_rows(self, rows: list[FormRow], *, quote_id: str, quote_title: str) -> list[FormRow]:
        if not quote_id and not quote_title:
            return _copy(rows)
        updated: list[FormRow] = []
        for row in rows:
            copy = row.model_copy(deep=True)
            copy.quote_id = quote_id
            copy.quote_title = quote_title
            updated.append(copy)
        return updated

    def _maybe_save(self, save_path: Path | None, state: RunState | None) -> None:
        if save_path is not None and state is not None:
            self._save(save_path, state)

    def _refresh_batch_summary(self, state: RunState) -> None:
        active_quotes = [quote for quote in state.batch_quotes if not quote.is_deleted]
        state.final_form_items = [row.model_copy(deep=True) for quote in active_quotes for row in quote.final_form_items]
        state.form_stages = []
        state.current_stage = FINAL_QUOTED if any(quote.form_stages for quote in active_quotes) else state.current_stage
        if not active_quotes:
            state.overall_status = "failed"
            state.next_action = "批量报价均已删除，可从回收站恢复"
            state.errors = []
            return
        statuses = [quote.status for quote in active_quotes]
        if any(status == "running" for status in statuses):
            state.overall_status = "running"
        elif all(status == "failed" for status in statuses):
            state.overall_status = "failed"
        elif any(status == "waiting_manual_input" for status in statuses):
            state.overall_status = "waiting_manual_input"
        elif self._exportable_items(state):
            state.overall_status = "completed"
        else:
            state.overall_status = "failed"
        state.errors = [f"{quote.title or quote.quote_id}: {'；'.join(quote.errors)}" for quote in active_quotes if quote.errors]
        state.next_action = self._next_action(state.overall_status)

    def _find_batch_quote_for_row(self, state: RunState, row_id: str) -> BatchQuoteItem | None:
        for quote in state.batch_quotes:
            if any(row.row_id == row_id for row in quote.final_form_items):
                return quote
            if any(row.row_id == row_id for stage in quote.form_stages for row in stage.items):
                return quote
        return None

    def _exportable_items(self, state: RunState, *, quote_id: str = "") -> list[FormRow]:
        if state.quote_mode == "batch":
            quotes = [quote for quote in state.batch_quotes if not quote.is_deleted]
            if quote_id:
                quotes = [quote for quote in quotes if quote.quote_id == quote_id]
            return [
                row.model_copy(deep=True)
                for quote in quotes
                for row in quote.final_form_items
                if row.stage_status == "quoted" and row.total_price is not None
            ]
        return [
            row.model_copy(deep=True)
            for row in state.final_form_items
            if row.stage_status == "quoted" and row.total_price is not None
        ]

    def _upsert(self, owner: RunState | BatchQuoteItem, stage_id: str, rows: list[FormRow], notes: list[str]) -> None:
        snapshot = FormStageSnapshot(
            stage_id=stage_id,
            label=STAGE_LABELS[stage_id],
            items=_copy(rows),
            notes=[n for n in notes if n],
        )
        for i, stage in enumerate(owner.form_stages):
            if stage.stage_id == stage_id:
                owner.form_stages[i] = snapshot
                if isinstance(owner, RunState):
                    owner.current_stage = stage_id
                return
        owner.form_stages.append(snapshot)
        if isinstance(owner, RunState):
            owner.current_stage = stage_id

    def _stage_rows(self, owner: RunState | BatchQuoteItem, stage_id: str) -> list[FormRow]:
        for stage in owner.form_stages:
            if stage.stage_id == stage_id:
                return _copy(stage.items)
        return []

    def export_docx(self, run_id: str, *, quote_id: str = "") -> Path:
        from backend.quote.settings import get_settings
        state = self.load_run(run_id)
        export_items = self._exportable_items(state, quote_id=quote_id)
        if not export_items:
            raise RuntimeError("no_quoted_items_to_export")
        settings = get_settings()
        template_path = PROJECT_ROOT / "doc" / "quote_tep.docx"
        if not template_path.exists():
            raise FileNotFoundError(f"Template not found: {template_path}")

        run_dir = settings.run_dir / run_id
        safe_quote_id = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in quote_id).strip("_")
        output_name = f"报价单_{run_id}_{safe_quote_id}.docx" if safe_quote_id else f"报价单_{run_id}.docx"
        output_path = run_dir / output_name

        doc = Document(template_path)

        # 1. 填充表格 (Table 1: 序号 | 测试项目 | 备注 | 基本金(元) | 单价(元) | 试验总量 | 合计（元）)
        if len(doc.tables) > 1:
            table = doc.tables[1]
            # 查找数据起始行（序号为1的行）
            start_row_idx = -1
            for i, row in enumerate(table.rows):
                if row.cells[0].text.strip() == "1":
                    start_row_idx = i
                    break
            
            if start_row_idx != -1:
                items = export_items
                
                # 识别模板中现有的数字序号行（数据行）
                data_row_indices = []
                total_row_idx = -1
                for i in range(start_row_idx, len(table.rows)):
                    cell_text = table.rows[i].cells[0].text.strip()
                    if cell_text.isdigit():
                        data_row_indices.append(i)
                    elif "总计" in cell_text:
                        total_row_idx = i
                        break
                
                # 如果实际项目数多于模板预设行数，在总计行之前插入新行
                if len(items) > len(data_row_indices):
                    template_row_idx = data_row_indices[-1] if data_row_indices else start_row_idx
                    for _ in range(len(items) - len(data_row_indices)):
                        insert_at = total_row_idx if total_row_idx != -1 else len(table.rows)
                        _insert_table_row_before(table, insert_at, template_row_idx)
                    
                    # 重新刷新行索引
                    data_row_indices = []
                    total_row_idx = -1
                    for i in range(start_row_idx, len(table.rows)):
                        cell_text = table.rows[i].cells[0].text.strip()
                        if cell_text.isdigit() or cell_text == "": # 包含新加的空行
                            data_row_indices.append(i)
                        elif "总计" in cell_text:
                            total_row_idx = i
                            break

                # 填充数据或清空多余模板行
                total_amount = 0.0
                for i, row_idx in enumerate(data_row_indices):
                    row = table.rows[row_idx]
                    if i < len(items):
                        item = items[i]
                        row.cells[0].text = str(i + 1)
                        row.cells[1].text = item.canonical_test_type or item.raw_test_type or ""
                        row.cells[2].text = "" # 备注留空
                        row.cells[3].text = f"{item.base_fee:g}" if item.base_fee is not None else "0"
                        row.cells[4].text = f"{item.unit_price:g}" if item.unit_price is not None else "0"
                        row.cells[5].text = f"{item.pricing_quantity:g}" if item.pricing_quantity is not None else "0"
                        row.cells[6].text = f"{item.total_price:g}" if item.total_price is not None else "0"
                        total_amount += (item.total_price or 0.0)
                    else:
                        # 清空多余的模板行内容
                        for cell in row.cells:
                            cell.text = ""

                # 更新总计行
                if total_row_idx != -1:
                    table.rows[total_row_idx].cells[6].text = f"{total_amount:g}"

        # 2. 替换文本占位符 (日期和注)
        now = datetime.now()
        date_str = now.strftime("%Y年%m月%d日")
        
        for para in doc.paragraphs:
            if "20xx年x月x日" in para.text:
                para.text = para.text.replace("20xx年x月x日", date_str)
        
        # 处理表格内的占位符（注：部分通常在最后一行的大单元格里）
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    if "x" in cell.text or "xxxx" in cell.text:
                        # 注1: 样品名 (留空)
                        new_text = cell.text.replace("xxxx", "")
                        # 注3: 项目数量
                        new_text = new_text.replace("x个测试项目", f"{len(items)}个测试项目")
                        cell.text = new_text

        doc.save(output_path)
        
        # 更新状态中的产物列表
        if str(output_path.name) not in state.artifacts.exported_files:
            state.artifacts.exported_files.append(output_path.name)
            self._save(run_dir / "run_state.json", state)
            
        return output_path

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


def _insert_table_row_before(table: object, row_index: int, template_row_index: int) -> None:
    rows = table.rows
    if not rows:
        return
    template_index = min(max(template_row_index, 0), len(rows) - 1)
    new_tr = deepcopy(rows[template_index]._tr)
    for tc in new_tr.tc_lst:
        for paragraph in tc.p_lst:
            for run in paragraph.r_lst:
                for text in run.t_lst:
                    text.text = ""
    if row_index < len(rows):
        rows[max(row_index, 0)]._tr.addprevious(new_tr)
    else:
        table._tbl.append(new_tr)

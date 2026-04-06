from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from packages.integrations.catalog import CatalogGateway
from packages.integrations.standard_library import StandardLibrary
from packages.integrations.standard_retrieval_module import StandardRetrievalModule

from .models import FormRow, SourceRef


@dataclass(slots=True)
class LocalKernel:
    catalog: CatalogGateway
    standards: StandardLibrary
    standard_module: StandardRetrievalModule | None = None

    def attach_standard_refs(self, rows: list[FormRow]) -> tuple[list[FormRow], list[str]]:
        updated: list[FormRow] = []
        notes: list[str] = []
        for row in rows:
            row_copy = row.model_copy(deep=True)
            refs = self.standards.find_by_codes(row_copy.standard_codes)
            for ref in refs:
                if any(existing.kind == ref.kind and existing.path == ref.path for existing in row_copy.source_refs):
                    continue
                row_copy.source_refs.append(SourceRef.model_validate(ref))
            if refs:
                labels = "、".join(ref.label or ref.path for ref in refs)
                notes.append(f"{row_copy.raw_test_type or row_copy.row_id}: 已找到标准文件 {labels}")
            updated.append(row_copy)
        if self.catalog.load_error:
            notes.append(f"数据库目录加载失败：{self.catalog.load_error}")
        return updated, notes

    def resolve_standard_evidences(
        self,
        rows: list[FormRow],
        *,
        target_fields_by_row: dict[str, list[str]] | None = None,
        run_dir: str | None = None,
    ) -> tuple[list[FormRow], list[str]]:
        if self.standard_module is None:
            return [row.model_copy(deep=True) for row in rows], []

        results_by_row = self.standard_module.resolve_for_rows(
            rows,
            target_fields_by_row=target_fields_by_row or {},
            run_dir=Path(run_dir) if run_dir else None,
        )
        updated: list[FormRow] = []
        notes: list[str] = []
        for row in rows:
            row_copy = row.model_copy(deep=True)
            result = results_by_row.get(row.row_id)
            evidences = result.evidences if result is not None else []
            row_copy.standard_evidences = [item.model_copy(deep=True) for item in evidences]
            result_notes = list(result.notes) if result is not None else []
            row_copy.standard_match_notes = result_notes + [
                f"{item.standard_code} {item.section_id or item.chunk_id} p.{item.page_start}-{item.page_end}"
                for item in evidences
            ]
            if evidences:
                notes.append(
                    f"{row_copy.raw_test_type or row_copy.row_id}: 命中标准章节 "
                    + "、".join(f"{item.section_id or item.chunk_id}" for item in evidences)
                )
            elif result_notes:
                notes.append(f"{row_copy.raw_test_type or row_copy.row_id}: {result_notes[-1]}")
            updated.append(row_copy)
        return updated, notes

    def match_test_types(self, rows: list[FormRow]) -> tuple[list[FormRow], list[str]]:
        updated: list[FormRow] = []
        notes: list[str] = []
        for row in rows:
            row_copy = row.model_copy(deep=True)
            record = self.catalog.find_test_type_by_alias(row_copy.canonical_test_type or row_copy.raw_test_type)
            if record:
                row_copy.canonical_test_type = record.name
                row_copy.matched_test_type_id = record.id
                if row_copy.base_fee is None:
                    row_copy.base_fee = record.base_fee
                if not row_copy.pricing_mode:
                    row_copy.pricing_mode = record.pricing_mode
                notes.append(f"{row_copy.raw_test_type or row_copy.row_id}: 匹配试验类型 {record.name}")
            else:
                notes.append(f"{row_copy.raw_test_type or row_copy.row_id}: 未匹配到试验类型")
            updated.append(row_copy)
        return updated, notes

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from backend.quote.models import FormRow, SourceRef

if TYPE_CHECKING:
    from backend.quote.catalog import CatalogGateway
    from backend.quote.standard.kb_reader import StandardLibrary
    from backend.quote.standard.module import StandardRetrievalModule


@dataclass(slots=True)
class Kernel:
    catalog: "CatalogGateway"
    standards: "StandardLibrary"
    retrieval: "StandardRetrievalModule"

    def match_test_types(self, rows: list[FormRow]) -> tuple[list[FormRow], list[str]]:
        updated, notes = [], []
        for row in rows:
            r = row.model_copy(deep=True)
            record = self.catalog.find_test_type_by_alias(r.canonical_test_type or r.raw_test_type)
            if record:
                r.canonical_test_type = record.name
                r.matched_test_type_id = record.id
                if r.base_fee is None:
                    r.base_fee = record.base_fee
                if not r.pricing_mode:
                    r.pricing_mode = record.pricing_mode
                notes.append(f"{r.raw_test_type or r.row_id}: 匹配试验类型 {record.name}")
            else:
                notes.append(f"{r.raw_test_type or r.row_id}: 未匹配到试验类型")
            updated.append(r)
        if self.catalog.load_error:
            notes.append(f"数据库目录加载失败：{self.catalog.load_error}")
        return updated, notes

    def attach_standard_refs(self, rows: list[FormRow]) -> tuple[list[FormRow], list[str]]:
        updated, notes = [], []
        for row in rows:
            r = row.model_copy(deep=True)
            refs = self.standards.find_by_codes(r.standard_codes)
            for ref in refs:
                if not any(x.kind == ref.kind and x.path == ref.path for x in r.source_refs):
                    r.source_refs.append(SourceRef.model_validate(ref))
            if refs:
                notes.append(f"{r.raw_test_type or r.row_id}: 已找到标准文件 {'、'.join(ref.label or ref.path for ref in refs)}")
            updated.append(r)
        return updated, notes

    def resolve_standard_evidences(
        self,
        rows: list[FormRow],
        *,
        target_fields_by_row: dict[str, list[str]] | None = None,
        run_dir: Path | None = None,
    ) -> tuple[list[FormRow], list[str]]:
        results_by_row = self.retrieval.resolve_for_rows(
            rows,
            target_fields_by_row=target_fields_by_row or {},
            run_dir=run_dir,
        )
        updated, notes = [], []
        for row in rows:
            r = row.model_copy(deep=True)
            result = results_by_row.get(row.row_id)
            evidences = result.evidences if result else []
            r.standard_evidences = [e.model_copy(deep=True) for e in evidences]
            r.standard_match_notes = (list(result.notes) if result else []) + [
                f"{e.standard_code} {e.section_id or e.chunk_id} p.{e.page_start}-{e.page_end}"
                for e in evidences
            ]
            label = r.raw_test_type or r.row_id
            if evidences:
                notes.append(f"{label}: 命中标准章节 {'、'.join(e.section_id or e.chunk_id for e in evidences)}")
            elif result and result.notes:
                notes.append(f"{label}: {result.notes[-1]}")
            updated.append(r)
        return updated, notes

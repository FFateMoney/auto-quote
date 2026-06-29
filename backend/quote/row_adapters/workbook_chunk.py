from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.common.models import NormalizedDocument
from backend.quote.adapters.excel_workbook import WorkbookExcelAdapter
from backend.quote.row_adapters.base import RowAdapterContext, RowAdapterResult
from backend.quote.row_adapters.document_extract import DocumentExtractPayload, DocumentExtractRowAdapter


@dataclass(slots=True)
class WorkbookChunkPayload:
    split_item: Any
    source_path: Path
    notes: list[str] = field(default_factory=list)


class WorkbookChunkRowAdapter:
    """Materialize an Excel chunk, then reuse the normal document extraction row adapter."""

    def __init__(self, *, workbook_adapter: WorkbookExcelAdapter | None = None) -> None:
        self.workbook_adapter = workbook_adapter or WorkbookExcelAdapter()
        self.document_adapter = DocumentExtractRowAdapter()

    def to_rows(self, payload: WorkbookChunkPayload, *, context: RowAdapterContext) -> RowAdapterResult:
        document = self._document_from_chunk(payload, run_dir=context.run_dir)
        result = self.document_adapter.to_rows(
            DocumentExtractPayload(documents=[document], notes=payload.notes),
            context=context,
        )
        return RowAdapterResult(rows=result.rows, notes=result.notes, documents=[document])

    def _document_from_chunk(self, payload: WorkbookChunkPayload, *, run_dir: Path) -> NormalizedDocument:
        split_item = payload.split_item
        chunk = getattr(split_item, "chunk")
        source_name = f"{getattr(split_item, 'title') or getattr(split_item, 'quote_id')}.xlsx"
        extracted = self.workbook_adapter.extract(
            chunk.workbook,
            source_name=source_name,
            run_dir=run_dir,
            source_stem=str(getattr(split_item, "quote_id") or "batch_quote"),
            chunk_label=chunk.label,
            main_range=chunk.main_range,
            shared_ranges=chunk.shared_ranges,
        )
        return NormalizedDocument(
            document_id=str(getattr(split_item, "quote_id")),
            source_name=source_name,
            source_kind="excel_chunk_workbook",
            original_path=str(payload.source_path),
            text_blocks=extracted.text_blocks,
            assets=extracted.assets,
            metadata={
                **extracted.metadata,
                "batch_quote_id": str(getattr(split_item, "quote_id")),
                "batch_source_summary": str(getattr(split_item, "source_summary")),
            },
        )

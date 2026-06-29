from __future__ import annotations

from pathlib import Path

from backend.quote.batch_splitters.base import BatchSplitItem, BatchSplitResult
from backend.quote.row_adapters.workbook_chunk import WorkbookChunkPayload, WorkbookChunkRowAdapter


class ProtocolWorkbookSplitter:
    strategy_id = "excel_protocol"

    def __init__(self, *, requester: object, row_adapter: WorkbookChunkRowAdapter | None = None) -> None:
        self.requester = requester
        self.row_adapter = row_adapter or WorkbookChunkRowAdapter()

    def split(self, workbook_path: Path, *, run_dir: Path) -> BatchSplitResult:
        split = self.requester.split_batch_excel_with_protocol(workbook_path, run_dir=run_dir)
        items = [
            BatchSplitItem(
                quote_id=item.quote_id,
                title=item.title,
                source_summary=item.source_summary,
                row_adapter=self.row_adapter,
                row_payload=WorkbookChunkPayload(split_item=item, source_path=workbook_path),
            )
            for item in split.items
        ]
        return BatchSplitResult(items=items, summary=split.summary, raw_response=split.raw_response)

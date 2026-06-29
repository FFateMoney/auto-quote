from __future__ import annotations

from backend.quote.batch_splitters.base import BatchSplitItem, BatchSplitResult, BatchSplitter
from backend.quote.batch_splitters.protocol_workbook import ProtocolWorkbookSplitter
from backend.quote.batch_splitters.vision_quote_list import VisionQuoteListSplitter


def build_batch_splitter(strategy: str, *, requester: object) -> BatchSplitter:
    strategy_id = (strategy or "excel_protocol").strip().lower()
    if strategy_id == "excel_protocol":
        return ProtocolWorkbookSplitter(requester=requester)
    if strategy_id == "vision_quote_list":
        return VisionQuoteListSplitter(requester=requester)
    raise ValueError(f"unsupported_batch_split_strategy:{strategy_id}")


__all__ = [
    "BatchSplitItem",
    "BatchSplitResult",
    "BatchSplitter",
    "ProtocolWorkbookSplitter",
    "VisionQuoteListSplitter",
    "build_batch_splitter",
]

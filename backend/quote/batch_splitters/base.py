from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from backend.quote.row_adapters.base import QuoteRowAdapter


@dataclass(slots=True)
class BatchSplitItem:
    quote_id: str
    title: str
    source_summary: str
    row_adapter: QuoteRowAdapter
    row_payload: Any


@dataclass(slots=True)
class BatchSplitResult:
    items: list[BatchSplitItem]
    summary: str = ""
    raw_response: str = ""
    notes: list[str] = field(default_factory=list)


class BatchSplitter(Protocol):
    strategy_id: str

    def split(self, workbook_path: Path, *, run_dir: Path) -> BatchSplitResult:
        ...

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from backend.common.models import NormalizedDocument
from backend.quote.models import FormRow


@dataclass(slots=True)
class RowAdapterContext:
    requester: Any
    run_dir: Path
    test_type_options: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RowAdapterResult:
    rows: list[FormRow]
    notes: list[str] = field(default_factory=list)
    documents: list[NormalizedDocument] = field(default_factory=list)


class QuoteRowAdapter(Protocol):
    def to_rows(self, payload: Any, *, context: RowAdapterContext) -> RowAdapterResult:
        ...

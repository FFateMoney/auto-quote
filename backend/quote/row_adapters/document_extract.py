from __future__ import annotations

from dataclasses import dataclass, field

from backend.common.models import NormalizedDocument
from backend.quote.row_adapters.base import RowAdapterContext, RowAdapterResult


@dataclass(slots=True)
class DocumentExtractPayload:
    documents: list[NormalizedDocument]
    notes: list[str] = field(default_factory=list)


class DocumentExtractRowAdapter:
    """Convert normalized documents into quote rows through the existing LLM extractor."""

    def to_rows(self, payload: DocumentExtractPayload, *, context: RowAdapterContext) -> RowAdapterResult:
        if not payload.documents:
            return RowAdapterResult(rows=[], notes=[*payload.notes, "未收到可抽取文档"])
        extraction = context.requester.extract_form(
            payload.documents,
            test_type_options=context.test_type_options,
            run_dir=context.run_dir,
        )
        notes = list(payload.notes)
        if extraction.summary:
            notes.append(f"模型摘要：{extraction.summary}")
        return RowAdapterResult(rows=extraction.items, notes=notes, documents=payload.documents)

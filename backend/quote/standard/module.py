from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from backend.quote.models import FormRow, StandardResolutionResult
from backend.quote.standard.judge import StandardContextJudge
from backend.quote.standard.resolver import StandardResolver
from backend.quote.standard.retriever import StandardRetriever


@dataclass(slots=True)
class StandardRetrievalModule:
    retriever: StandardRetriever = field(default_factory=StandardRetriever)
    judge: StandardContextJudge = field(default_factory=StandardContextJudge)
    resolver: StandardResolver = field(init=False)

    def __post_init__(self) -> None:
        self.resolver = StandardResolver(retriever=self.retriever)

    def resolve_for_row(
        self,
        row: FormRow,
        *,
        target_fields: list[str] | None = None,
        run_dir: Path | None = None,
    ) -> StandardResolutionResult:
        return self.resolver.resolve_for_row(row, target_fields=target_fields or [], run_dir=run_dir)

    def resolve_for_rows(
        self,
        rows: list[FormRow],
        *,
        target_fields_by_row: dict[str, list[str]] | None = None,
        run_dir: Path | None = None,
    ) -> dict[str, StandardResolutionResult]:
        return self.resolver.resolve_for_rows(rows, target_fields_by_row=target_fields_by_row or {}, run_dir=run_dir)

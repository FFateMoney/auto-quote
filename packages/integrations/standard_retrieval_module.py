from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from packages.core.models import FormRow, StandardResolutionResult

from .standard_indexer import IndexBuildReport, StandardIndexer
from .standard_context_judge import StandardContextJudge
from .standard_resolution import StandardResolver
from .standard_retriever import StandardRetriever


@dataclass(slots=True)
class StandardRetrievalModule:
    indexer: StandardIndexer = field(default_factory=StandardIndexer)
    retriever: StandardRetriever = field(default_factory=StandardRetriever)
    judge: StandardContextJudge | None = None
    resolver: StandardResolver = field(init=False)

    def __post_init__(self) -> None:
        self.resolver = StandardResolver(retriever=self.retriever)

    def sync_index(self, *, sync: bool = True, rebuild: bool = False) -> IndexBuildReport:
        return self.indexer.build_index(sync=sync, rebuild=rebuild)

    def bind_judge(self, judge: StandardContextJudge) -> None:
        self.judge = judge
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
        return self.resolver.resolve_for_rows(
            rows,
            target_fields_by_row=target_fields_by_row or {},
            run_dir=run_dir,
        )

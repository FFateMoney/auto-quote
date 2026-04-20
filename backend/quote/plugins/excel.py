from __future__ import annotations

from pathlib import Path

from backend.common.models import NormalizedDocument
from backend.quote.adapters.excel import ExcelAdapter
from backend.quote.plugins.base import DocumentProcessorPlugin


class ExcelProcessorPlugin(DocumentProcessorPlugin):
    plugin_id = "excel"
    supported_types = (".xlsx",)

    def __init__(self, *, adapter: ExcelAdapter | None = None) -> None:
        self.adapter = adapter or ExcelAdapter()

    def can_handle(self, input_file: Path) -> bool:
        return input_file.suffix.lower() in self.supported_types

    def preprocess(self, input_file: Path, run_context: dict[str, object]) -> NormalizedDocument:
        run_dir = Path(str(run_context["run_dir"]))
        payload = self.adapter.extract(input_file, run_dir=run_dir)
        return NormalizedDocument(
            document_id=input_file.stem,
            source_name=input_file.name,
            source_kind="excel",
            original_path=str(input_file),
            text_blocks=payload.text_blocks,
            assets=payload.assets,
            metadata={"plugin_id": self.plugin_id, **payload.metadata},
        )

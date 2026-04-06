from __future__ import annotations

from pathlib import Path

from packages.core.models import NormalizedDocument
from packages.integrations.pdf_adapter import PdfAdapter

from .base import DocumentProcessorPlugin


class PdfProcessorPlugin(DocumentProcessorPlugin):
    plugin_id = "pdf"
    supported_types = (".pdf",)

    def __init__(self, *, adapter: PdfAdapter | None = None) -> None:
        self.adapter = adapter or PdfAdapter()

    def can_handle(self, input_file: Path) -> bool:
        return input_file.suffix.lower() in self.supported_types

    def preprocess(self, input_file: Path, run_context: dict[str, object]) -> NormalizedDocument:
        run_dir = Path(str(run_context["run_dir"]))
        payload = self.adapter.extract(input_file, run_dir=run_dir)
        return NormalizedDocument(
            document_id=input_file.stem,
            source_name=input_file.name,
            source_kind="pdf",
            original_path=str(input_file),
            text_blocks=payload.text_blocks,
            assets=payload.assets,
            metadata={
                "plugin_id": self.plugin_id,
                **payload.metadata,
            },
        )

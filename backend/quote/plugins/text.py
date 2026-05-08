from __future__ import annotations

from pathlib import Path

from backend.common.models import NormalizedDocument, NormalizedTextBlock
from backend.quote.plugins.base import DocumentProcessorPlugin


class TextProcessorPlugin(DocumentProcessorPlugin):
    plugin_id = "text"
    supported_types = (".txt",)

    def can_handle(self, input_file: Path) -> bool:
        return input_file.suffix.lower() in self.supported_types

    def preprocess(self, input_file: Path, run_context: dict[str, object]) -> NormalizedDocument:
        text = input_file.read_text(encoding="utf-8").strip()
        return NormalizedDocument(
            document_id=input_file.stem,
            source_name=input_file.name,
            source_kind="text",
            original_path=str(input_file),
            text_blocks=[
                NormalizedTextBlock(
                    block_id=f"{input_file.stem}-plain-text",
                    block_type="PlainText",
                    text=text,
                    source_path="pasted_text",
                )
            ],
            assets=[],
            metadata={"plugin_id": self.plugin_id},
        )

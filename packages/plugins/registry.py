from __future__ import annotations

from pathlib import Path

from packages.core.models import NormalizedDocument

from .base import DocumentProcessorPlugin
from .excel_processor import ExcelProcessorPlugin
from .image_processor import ImageProcessorPlugin
from .pdf_processor import PdfProcessorPlugin
from .word_processor import WordProcessorPlugin


class UnsupportedPlugin(DocumentProcessorPlugin):
    plugin_id = "unsupported"
    supported_types = ()

    def can_handle(self, input_file: Path) -> bool:
        return True

    def preprocess(self, input_file: Path, run_context: dict[str, object]) -> NormalizedDocument:
        raise RuntimeError(f"unsupported_document_type:{input_file.suffix.lower() or 'unknown'}")


class PluginRegistry:
    def __init__(self) -> None:
        self._plugins: list[DocumentProcessorPlugin] = [
            WordProcessorPlugin(),
            ExcelProcessorPlugin(),
            PdfProcessorPlugin(),
            ImageProcessorPlugin(),
        ]
        self._fallback = UnsupportedPlugin()

    def resolve(self, input_file: Path) -> DocumentProcessorPlugin:
        for plugin in self._plugins:
            if plugin.can_handle(input_file):
                return plugin
        return self._fallback

    def available_plugins(self) -> list[dict[str, object]]:
        return [plugin.metadata() for plugin in self._plugins]

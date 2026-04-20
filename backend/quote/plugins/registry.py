from __future__ import annotations

from pathlib import Path

from backend.common.models import NormalizedDocument
from backend.quote.plugins.base import DocumentProcessorPlugin
from backend.quote.plugins.excel import ExcelProcessorPlugin
from backend.quote.plugins.image import ImageProcessorPlugin
from backend.quote.plugins.pdf import PdfProcessorPlugin
from backend.quote.plugins.word import WordProcessorPlugin


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

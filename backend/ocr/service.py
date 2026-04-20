from __future__ import annotations

from pathlib import Path

from backend.ocr.engine import PpStructureV3Engine
from backend.ocr.models import MarkdownResult
from backend.ocr.settings import OcrSettings, get_settings


class OcrService:
    def __init__(self, settings: OcrSettings | None = None) -> None:
        self._engine = PpStructureV3Engine(settings or get_settings())

    def process_bytes(self, payload: bytes, *, filename: str) -> MarkdownResult:
        return self._engine.run(payload, filename=filename)

    def process_path(self, path: Path) -> MarkdownResult:
        return self._engine.run(path.read_bytes(), filename=path.name)

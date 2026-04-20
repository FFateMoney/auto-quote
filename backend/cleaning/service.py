from __future__ import annotations

from pathlib import Path
from backend.cleaning.engine import MarkdownCleaner
from backend.cleaning.models import CleaningOptions, CleaningResult
from backend.cleaning.settings import CleaningSettings, get_settings


class CleaningService:
    def __init__(self, settings: CleaningSettings | None = None, options: CleaningOptions | None = None) -> None:
        self._settings = settings or get_settings()
        self._engine = MarkdownCleaner(options)

    def clean_text(self, content: str) -> CleaningResult:
        """清洗 Markdown 字符串内容"""
        return self._engine.clean(content)

    def clean_file(self, input_path: Path) -> CleaningResult:
        """读取并清洗指定路径的文件内容"""
        content = input_path.read_text(encoding="utf-8")
        return self._engine.clean(content)

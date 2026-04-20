from __future__ import annotations

import logging
import re
from pathlib import Path

from backend.quote.models import SourceRef
from backend.quote.settings import get_settings


logger = logging.getLogger(__name__)
_ALNUM = re.compile(r"[A-Za-z0-9]+")


def _normalize_key(value: str | Path) -> str:
    """规范化为仅包含小写字母和数字的形式，用于匹配标准号"""
    return "".join(p.lower() for p in _ALNUM.findall(str(value or "")))


class StandardLibrary:
    """从清洗后的 Markdown 目录读取标准文件"""

    def __init__(self) -> None:
        s = get_settings()
        # 已清洗的 markdown 文件目录
        self._kb_dir = s.standard_kb_dir
        if not self._kb_dir.exists():
            logger.warning("standard_kb_dir does not exist: %s", self._kb_dir)

    def find_by_codes(self, codes: list[str]) -> list[SourceRef]:
        """根据标准号查找对应的清洗后 Markdown 文件"""
        refs: list[SourceRef] = []
        for code in codes:
            key = _normalize_key(code)
            if not key:
                continue

            # 尝试在 _kb_dir 中找到匹配的文件
            if self._kb_dir.exists():
                for md_file in self._kb_dir.glob("*.md"):
                    file_key = _normalize_key(md_file.stem)
                    if file_key and key in file_key:
                        refs.append(SourceRef(kind="standard_file", path=str(md_file), label=code))
                        break

        return refs

from __future__ import annotations

import re
from collections import Counter


WHITESPACE_RE = re.compile(r"[ \t]+")
WATERMARK_RE = re.compile(r"^(TO|OF|BY|AT)\s*[:：]", re.IGNORECASE)
PAGE_INDEX_RE = re.compile(r"^(page\s+)?\d+\s*(/\s*\d+)?$", re.IGNORECASE)
PAGE_HEADER_RE = re.compile(r".+\bpage\s+\d+\s*$", re.IGNORECASE)
SECTION_RE = re.compile(r"^(?:\d+(?:[.\-]\d+){1,4}|[A-Z]{1,4}/\d{2})(?:\s+|$)")


def _normalize_line(line: str) -> str:
    return WHITESPACE_RE.sub(" ", str(line or "").replace("\x00", " ")).strip()


def _is_obvious_noise(line: str) -> bool:
    if not line:
        return True
    if WATERMARK_RE.match(line):
        return True
    if PAGE_INDEX_RE.match(line):
        return True
    if PAGE_HEADER_RE.match(line):
        return True
    return False


def _is_removable_repeated_line(line: str) -> bool:
    if not line or len(line) > 80:
        return False
    if SECTION_RE.match(line):
        return False
    return True


class StandardCleaner:
    def clean_page_text(self, text: str) -> str:
        seen: set[str] = set()
        cleaned_lines: list[str] = []
        for raw_line in str(text or "").splitlines():
            line = _normalize_line(raw_line)
            if _is_obvious_noise(line):
                continue
            if line in seen:
                continue
            seen.add(line)
            cleaned_lines.append(line)
        return "\n".join(cleaned_lines).strip()

    def clean_document_pages(self, pages: list[str]) -> list[str]:
        page_lines = [self._page_lines(page) for page in pages]
        counts = Counter()
        for lines in page_lines:
            counts.update(set(lines))

        threshold = max(3, int(len(page_lines) * 0.5))
        repeated = {
            line
            for line, count in counts.items()
            if count >= threshold and _is_removable_repeated_line(line)
        }

        cleaned_pages: list[str] = []
        for lines in page_lines:
            filtered = []
            for index, line in enumerate(lines):
                if line in repeated and (index < 4 or index >= max(0, len(lines) - 4)):
                    continue
                filtered.append(line)
            cleaned_pages.append("\n".join(filtered).strip())
        return cleaned_pages

    def _page_lines(self, text: str) -> list[str]:
        lines: list[str] = []
        seen: set[str] = set()
        for raw_line in str(text or "").splitlines():
            line = _normalize_line(raw_line)
            if _is_obvious_noise(line):
                continue
            if line in seen:
                continue
            seen.add(line)
            lines.append(line)
        return lines

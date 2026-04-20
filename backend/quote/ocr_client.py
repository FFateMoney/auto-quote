"""HTTP client for the backend/ocr service (PP-StructureV3).

Calls POST /api/ocr/markdown and returns the markdown text.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import requests

from backend.quote.settings import get_settings


@dataclass(slots=True)
class OcrMarkdownResult:
    markdown_text: str
    page_count: int
    elapsed_ms: float


class OcrClient:
    def __init__(self, *, base_url: str | None = None, timeout: float = 300) -> None:
        self.base_url = (base_url or get_settings().ocr_service_base_url).rstrip("/")
        self.timeout = timeout

    def extract_markdown(self, path: Path) -> OcrMarkdownResult:
        mime = _mime(path)
        with path.open("rb") as fh:
            response = requests.post(
                f"{self.base_url}/api/ocr/markdown",
                files={"file": (path.name, fh, mime)},
                timeout=self.timeout,
            )
        response.raise_for_status()
        payload = response.json()
        return OcrMarkdownResult(
            markdown_text=str(payload.get("markdown_text") or ""),
            page_count=int(payload.get("page_count") or 0),
            elapsed_ms=float((payload.get("timings") or {}).get("total_elapsed_ms") or 0),
        )


def _mime(path: Path) -> str:
    s = path.suffix.lower()
    return {".pdf": "application/pdf", ".png": "image/png",
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".bmp": "image/bmp", ".webp": "image/webp"}.get(s, "application/octet-stream")

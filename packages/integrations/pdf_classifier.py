from __future__ import annotations

import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path
import re
from typing import Any

from pypdf import PdfReader
from pypdf.errors import FileNotDecryptedError


MIN_GOOD_PAGE_CHARS = 80
MIN_MEANINGFUL_RATIO = 0.55
MAX_WEIRD_RATIO = 0.15
MIN_DIGITAL_PAGE_RATIO = 0.7
MIN_NONEMPTY_PAGE_RATIO = 0.7
SCAN_TEXT_PAGE_RATIO = 0.2
ELLIPSIS_RE = re.compile(r"[.．·•…]{5,}")


@dataclass(slots=True, frozen=True)
class PageStats:
    page_num: int
    chars: int
    meaningful_chars: int
    valid_chars: int
    weird_chars: int
    meaningful_ratio: float
    weird_ratio: float
    image_count: int
    extraction_status: str
    quality_label: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True, frozen=True)
class PdfClassificationResult:
    file_name: str
    source_path: str
    page_count: int
    nonempty_pages: int
    image_pages: int
    avg_chars_per_page: float
    avg_meaningful_ratio: float
    avg_weird_ratio: float
    digital_page_ratio: float
    nonempty_page_ratio: float
    pdf_type: str
    text_quality: str
    target_bucket: str
    reason: str
    page_stats: list[PageStats] = field(default_factory=list)

    @property
    def detected_pdf_type(self) -> str:
        return self.pdf_type

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["page_stats"] = [item.to_dict() for item in self.page_stats]
        payload["detected_pdf_type"] = self.pdf_type
        return payload


class PdfClassifier:
    def classify(self, path: str | Path) -> PdfClassificationResult:
        pdf_path = Path(path)
        try:
            reader = PdfReader(str(pdf_path))
        except Exception as exc:
            return self._build_terminal_result(
                path=pdf_path,
                page_count=0,
                pdf_type="unreadable_pdf",
                text_quality="bad",
                target_bucket="scan",
                reason=f"pdf_read_failed:{type(exc).__name__}",
            )

        if reader.is_encrypted:
            try:
                decrypt_result = reader.decrypt("")
            except Exception:
                decrypt_result = 0
            if decrypt_result == 0:
                try:
                    page_count = len(reader.pages)
                except Exception:
                    page_count = 0
                return self._build_terminal_result(
                    path=pdf_path,
                    page_count=page_count,
                    pdf_type="encrypted_pdf",
                    text_quality="bad",
                    target_bucket="scan",
                    reason="pdf_encrypted_or_protected",
                )

        page_stats = [
            self._analyze_page(page, page_num)
            for page_num, page in enumerate(reader.pages, start=1)
        ]
        return self._summarize(pdf_path, page_stats)

    def _build_terminal_result(
        self,
        *,
        path: Path,
        page_count: int,
        pdf_type: str,
        text_quality: str,
        target_bucket: str,
        reason: str,
    ) -> PdfClassificationResult:
        return PdfClassificationResult(
            file_name=path.name,
            source_path=str(path),
            page_count=page_count,
            nonempty_pages=0,
            image_pages=0,
            avg_chars_per_page=0.0,
            avg_meaningful_ratio=0.0,
            avg_weird_ratio=1.0,
            digital_page_ratio=0.0,
            nonempty_page_ratio=0.0,
            pdf_type=pdf_type,
            text_quality=text_quality,
            target_bucket=target_bucket,
            reason=reason,
            page_stats=[],
        )

    def _analyze_page(self, page: Any, page_num: int) -> PageStats:
        try:
            text = page.extract_text() or ""
            extraction_status = "ok"
        except FileNotDecryptedError:
            text = ""
            extraction_status = "decrypt_failed"
        except Exception:
            text = ""
            extraction_status = "extract_failed"

        normalized = self._normalize_text(text)
        image_count = self._image_count(page)
        meaningful_chars = 0
        valid_chars = 0
        weird_chars = 0
        visible_chars = 0
        for char in normalized:
            if char.isspace():
                continue
            visible_chars += 1
            char_kind = self._char_kind(char)
            if char_kind in {"han", "hiragana", "katakana", "latin", "digit"}:
                meaningful_chars += 1
                valid_chars += 1
            elif char_kind == "punct":
                valid_chars += 1
            else:
                weird_chars += 1

        meaningful_ratio = meaningful_chars / visible_chars if visible_chars else 0.0
        weird_ratio = weird_chars / visible_chars if visible_chars else 0.0
        chars = len(normalized)
        quality_label = self._page_quality_label(
            chars=chars,
            meaningful_ratio=meaningful_ratio,
            weird_ratio=weird_ratio,
            image_count=image_count,
        )

        return PageStats(
            page_num=page_num,
            chars=chars,
            meaningful_chars=meaningful_chars,
            valid_chars=valid_chars,
            weird_chars=weird_chars,
            meaningful_ratio=round(meaningful_ratio, 4),
            weird_ratio=round(weird_ratio, 4),
            image_count=image_count,
            extraction_status=extraction_status,
            quality_label=quality_label,
        )

    def _summarize(self, path: Path, page_stats: list[PageStats]) -> PdfClassificationResult:
        page_count = len(page_stats)
        nonempty_pages = sum(1 for item in page_stats if item.chars > 0)
        image_pages = sum(1 for item in page_stats if item.image_count > 0)
        digital_pages = sum(1 for item in page_stats if item.quality_label == "digital")
        suspicious_pages = sum(1 for item in page_stats if item.quality_label == "suspicious")
        empty_pages = sum(1 for item in page_stats if item.quality_label == "empty")

        avg_chars_per_page = self._avg(item.chars for item in page_stats)
        avg_meaningful_ratio = self._avg(item.meaningful_ratio for item in page_stats)
        avg_weird_ratio = self._avg(item.weird_ratio for item in page_stats)
        digital_page_ratio = digital_pages / page_count if page_count else 0.0
        nonempty_page_ratio = nonempty_pages / page_count if page_count else 0.0
        image_page_ratio = image_pages / page_count if page_count else 0.0

        if nonempty_page_ratio <= SCAN_TEXT_PAGE_RATIO:
            pdf_type = "scanned_pdf" if image_page_ratio > 0 else "textless_pdf"
        elif avg_weird_ratio > MAX_WEIRD_RATIO or suspicious_pages > max(2, page_count // 4):
            pdf_type = "hybrid_pdf"
        else:
            pdf_type = "digital_pdf"

        if (
            digital_page_ratio >= MIN_DIGITAL_PAGE_RATIO
            and nonempty_page_ratio >= MIN_NONEMPTY_PAGE_RATIO
            and avg_weird_ratio <= MAX_WEIRD_RATIO
        ):
            text_quality = "good"
            target_bucket = "digital"
            reason = "sufficient_text_quality"
        else:
            text_quality = "bad" if (empty_pages >= page_count * 0.5 or avg_weird_ratio > MAX_WEIRD_RATIO) else "suspect"
            target_bucket = "scan"
            reason = self._bad_reason(
                nonempty_page_ratio=nonempty_page_ratio,
                digital_page_ratio=digital_page_ratio,
                avg_weird_ratio=avg_weird_ratio,
                pdf_type=pdf_type,
            )

        return PdfClassificationResult(
            file_name=path.name,
            source_path=str(path),
            page_count=page_count,
            nonempty_pages=nonempty_pages,
            image_pages=image_pages,
            avg_chars_per_page=round(avg_chars_per_page, 2),
            avg_meaningful_ratio=round(avg_meaningful_ratio, 4),
            avg_weird_ratio=round(avg_weird_ratio, 4),
            digital_page_ratio=round(digital_page_ratio, 4),
            nonempty_page_ratio=round(nonempty_page_ratio, 4),
            pdf_type=pdf_type,
            text_quality=text_quality,
            target_bucket=target_bucket,
            reason=reason,
            page_stats=page_stats,
        )

    def _page_quality_label(
        self,
        *,
        chars: int,
        meaningful_ratio: float,
        weird_ratio: float,
        image_count: int,
    ) -> str:
        if chars == 0:
            return "empty"
        if chars >= MIN_GOOD_PAGE_CHARS and meaningful_ratio >= MIN_MEANINGFUL_RATIO and weird_ratio <= MAX_WEIRD_RATIO:
            return "digital"
        if chars < 20 and image_count > 0:
            return "empty"
        return "suspicious"

    def _bad_reason(
        self,
        *,
        nonempty_page_ratio: float,
        digital_page_ratio: float,
        avg_weird_ratio: float,
        pdf_type: str,
    ) -> str:
        if nonempty_page_ratio <= SCAN_TEXT_PAGE_RATIO:
            return "insufficient_pdf_text"
        if avg_weird_ratio > MAX_WEIRD_RATIO:
            return "suspected_encoding_issue"
        if digital_page_ratio < MIN_DIGITAL_PAGE_RATIO:
            return f"low_good_page_ratio:{pdf_type}"
        return f"low_text_quality:{pdf_type}"

    def _normalize_text(self, text: str) -> str:
        lines: list[str] = []
        seen: set[str] = set()
        for raw_line in str(text or "").splitlines():
            line = " ".join(raw_line.replace("\x00", " ").split()).strip()
            if not line:
                continue
            if ELLIPSIS_RE.fullmatch(line):
                continue
            if line in seen:
                continue
            seen.add(line)
            lines.append(line)
        return "\n".join(lines).strip()

    def _image_count(self, page: Any) -> int:
        try:
            resources = page.get("/Resources")
            if resources is None or "/XObject" not in resources:
                return 0
            xobjects = resources["/XObject"].get_object()
            count = 0
            for obj_name in xobjects:
                xobject = xobjects[obj_name]
                if xobject.get("/Subtype") == "/Image":
                    count += 1
            return count
        except Exception:
            return 0

    def _char_kind(self, char: str) -> str:
        code = ord(char)
        if char.isdigit():
            return "digit"
        if "A" <= char <= "Z" or "a" <= char <= "z":
            return "latin"
        if 0x4E00 <= code <= 0x9FFF:
            return "han"
        if 0x3040 <= code <= 0x309F:
            return "hiragana"
        if 0x30A0 <= code <= 0x30FF:
            return "katakana"
        category = unicodedata.category(char)
        if category.startswith("P") or category.startswith("S"):
            return "punct"
        return "other"

    def _avg(self, values: Any) -> float:
        collected = list(values)
        if not collected:
            return 0.0
        return sum(collected) / len(collected)

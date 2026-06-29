from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from backend.quote.models import FormRow
from backend.quote.row_adapters.base import RowAdapterContext, RowAdapterResult


_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")
_INCH_RE = re.compile(r"(?:''|\"|\bin\b|inch|英寸)", re.IGNORECASE)
_CM_RE = re.compile(r"(?:\bcm\b|厘米)", re.IGNORECASE)
_M_RE = re.compile(r"(?:\bm\b|米)", re.IGNORECASE)


@dataclass(slots=True)
class VisionQuoteListPayload:
    quote: dict[str, Any]
    notes: list[str] = field(default_factory=list)


class VisionQuoteListRowAdapter:
    """Convert one vision-split quote object into the canonical FormRow shape."""

    def to_rows(self, payload: VisionQuoteListPayload, *, context: RowAdapterContext) -> RowAdapterResult:
        del context
        quote = payload.quote
        experiment_type = _clean_text(quote.get("experiment_type"))
        standard_no = _clean_text(quote.get("standard_no"))
        sample_quantity = _float_or_none(quote.get("sample_quantity"))
        length_text = _clean_text(quote.get("length"))
        width_text = _clean_text(quote.get("width"))
        height_text = _clean_text(quote.get("height"))
        source_text = _source_text(
            experiment_type=experiment_type,
            standard_no=standard_no,
            length=length_text,
            width=width_text,
            height=height_text,
            sample_quantity=sample_quantity,
        )
        row = FormRow(
            raw_test_type=experiment_type,
            standard_codes=[standard_no] if standard_no else [],
            sample_count=sample_quantity,
            sample_length_mm=_dimension_to_mm(length_text),
            sample_width_mm=_dimension_to_mm(width_text),
            sample_height_mm=_dimension_to_mm(height_text),
            source_text=source_text,
            conditions_text=standard_no,
            sample_info_text=_sample_info_text(length_text, width_text, height_text, sample_quantity),
        )
        return RowAdapterResult(rows=[row], notes=list(payload.notes))


def _clean_text(value: Any) -> str:
    if value in (None, ""):
        return ""
    return re.sub(r"\s+", " ", str(value).strip())


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = _NUMBER_RE.search(str(value))
    return float(match.group(0)) if match else None


def _dimension_to_mm(value: str) -> float | None:
    if not value:
        return None
    match = _NUMBER_RE.search(value)
    if not match:
        return None
    number = float(match.group(0))
    if _INCH_RE.search(value):
        return round(number * 25.4, 3)
    if _CM_RE.search(value):
        return round(number * 10, 3)
    if _M_RE.search(value) and not re.search(r"\bmm\b|毫米", value, re.IGNORECASE):
        return round(number * 1000, 3)
    return number


def _sample_info_text(length: str, width: str, height: str, sample_quantity: float | None) -> str:
    parts: list[str] = []
    if length:
        parts.append(f"长 {length}")
    if width:
        parts.append(f"宽 {width}")
    if height:
        parts.append(f"高 {height}")
    if sample_quantity is not None:
        parts.append(f"样品数量 {sample_quantity:g}")
    return "，".join(parts)


def _source_text(
    *,
    experiment_type: str,
    standard_no: str,
    length: str,
    width: str,
    height: str,
    sample_quantity: float | None,
) -> str:
    parts = [part for part in (experiment_type, standard_no, _sample_info_text(length, width, height, sample_quantity)) if part]
    return "视觉批量切分：" + "；".join(parts) if parts else "视觉批量切分报价"

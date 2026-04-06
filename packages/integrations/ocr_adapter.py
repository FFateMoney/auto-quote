from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rapidocr_onnxruntime import RapidOCR

from packages.core.logging_utils import append_run_log


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class OcrLine:
    text: str
    score: float | None = None
    box: list[list[float]] | None = None


@dataclass(slots=True)
class OcrResult:
    full_text: str
    lines: list[OcrLine]
    timings: list[float]


class OcrAdapter:
    def __init__(self) -> None:
        self.engine = RapidOCR()

    def extract(self, input_path: Path, *, run_dir: Path | None = None) -> OcrResult:
        logger.info("OCR 开始: file=%s", input_path.name)
        if run_dir is not None:
            append_run_log(run_dir, f"OCR 开始: {input_path.name}")

        result, elapsed = self.engine(input_path)
        lines: list[OcrLine] = []
        for item in result or []:
            if not isinstance(item, (list, tuple)) or len(item) < 3:
                continue
            box = item[0] if isinstance(item[0], list) else None
            text = str(item[1] or "").strip()
            if not text:
                continue
            try:
                score = float(item[2]) if item[2] is not None else None
            except Exception:
                score = None
            lines.append(OcrLine(text=text, score=score, box=box))

        full_text = "\n".join(line.text for line in lines if line.text).strip()
        timings = [float(value) for value in (elapsed or [])]

        logger.info("OCR 完成: file=%s lines=%s chars=%s", input_path.name, len(lines), len(full_text))
        if run_dir is not None:
            append_run_log(run_dir, f"OCR 完成: {input_path.name} | lines={len(lines)} | chars={len(full_text)}")

        return OcrResult(full_text=full_text, lines=lines, timings=timings)

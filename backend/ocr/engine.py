from __future__ import annotations

import os
import tempfile
import time
import warnings
from pathlib import Path
from uuid import uuid4

from backend.ocr.models import MarkdownResult
from backend.ocr.settings import OcrSettings


warnings.filterwarnings("ignore", message=r".*No ccache found.*", category=UserWarning)

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp", ".gif"}


def _detect_input_kind(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        return "pdf"
    if suffix in _IMAGE_SUFFIXES:
        return "image"
    raise ValueError(f"unsupported_file_type:{suffix!r}  supported: .pdf, .png, .jpg, .jpeg, .tiff, .tif, .bmp, .webp")


class PpStructureV3Engine:
    def __init__(self, settings: OcrSettings) -> None:
        self._settings = settings
        self._pipeline = None

    def run(self, payload: bytes, *, filename: str) -> MarkdownResult:
        input_kind = _detect_input_kind(filename)
        suffix = Path(filename).suffix.lower() or ".bin"

        started = time.perf_counter()
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as fh:
            fh.write(payload)
            temp_path = Path(fh.name)
        try:
            pipeline = self._get_pipeline()
            s = self._settings
            raw = pipeline.predict(
                str(temp_path),
                use_doc_orientation_classify=s.use_doc_orientation_classify,
                use_doc_unwarping=s.use_doc_unwarping,
                use_textline_orientation=s.use_textline_orientation,
                use_seal_recognition=s.use_seal_recognition,
                use_table_recognition=s.use_table_recognition,
                use_formula_recognition=s.use_formula_recognition,
                use_chart_recognition=s.use_chart_recognition,
                use_region_detection=s.use_region_detection,
                use_table_orientation_classify=s.use_table_orientation_classify,
                format_block_content=s.format_block_content,
                markdown_ignore_labels=s.markdown_ignore_labels,
            )
            items = raw if isinstance(raw, list) else list(raw) if hasattr(raw, "__iter__") else [raw]
            markdown_pages: list[dict[str, object]] = []
            fallback_pages: list[str] = []
            for item in items:
                markdown_pages.append(self._coerce_markdown_dict(item))
                fallback_pages.append(self._fallback_text(item))
            markdown_text = self._concatenate(pipeline, markdown_pages).strip()
            if not markdown_text:
                markdown_text = "\n\n".join(p for p in fallback_pages if p).strip()
            page_count = len(items)
        finally:
            temp_path.unlink(missing_ok=True)

        elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
        return MarkdownResult(
            request_id=uuid4().hex,
            engine="pp_structurev3",
            markdown_text=markdown_text,
            page_count=page_count,
            timings={"total_elapsed_ms": elapsed_ms},
            metadata={"input_kind": input_kind, "device": s.device},
        )

    def _get_pipeline(self):
        if self._pipeline is not None:
            return self._pipeline
        os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
        try:
            from paddleocr import PPStructureV3
        except Exception as exc:
            raise RuntimeError("pp_structurev3_not_installed: pip install 'paddleocr[doc-parser]'") from exc
        s = self._settings
        self._pipeline = PPStructureV3(
            text_detection_model_name=s.text_detection_model,
            text_recognition_model_name=s.text_recognition_model,
            use_region_detection=s.use_region_detection,
            use_table_recognition=s.use_table_recognition,
            format_block_content=s.format_block_content,
            markdown_ignore_labels=s.markdown_ignore_labels,
            use_doc_orientation_classify=s.use_doc_orientation_classify,
            use_doc_unwarping=s.use_doc_unwarping,
            use_textline_orientation=s.use_textline_orientation,
            use_seal_recognition=s.use_seal_recognition,
            use_formula_recognition=s.use_formula_recognition,
            use_chart_recognition=s.use_chart_recognition,
            device=s.device,
        )
        return self._pipeline

    def _coerce_markdown_dict(self, item: object) -> dict[str, object]:
        markdown = getattr(item, "markdown", None)
        if callable(markdown):
            markdown = markdown()
        return markdown if isinstance(markdown, dict) else {}

    def _concatenate(self, pipeline: object, pages: list[dict[str, object]]) -> str:
        if not pages:
            return ""
        combined = pipeline.concatenate_markdown_pages(pages)
        if isinstance(combined, str):
            return combined
        if isinstance(combined, dict):
            return str(combined.get("markdown_texts") or combined.get("text") or "").strip()
        if isinstance(combined, (list, tuple)) and combined:
            first = combined[0]
            if isinstance(first, str):
                return first
            if isinstance(first, dict):
                return str(first.get("markdown_texts") or first.get("text") or "").strip()
        return str(combined or "").strip()

    def _fallback_text(self, item: object) -> str:
        json_payload = getattr(item, "json", None)
        if callable(json_payload):
            json_payload = json_payload()
        if not isinstance(json_payload, dict):
            return ""
        payload = json_payload.get("res") if isinstance(json_payload.get("res"), dict) else json_payload
        if not isinstance(payload, dict):
            return ""
        texts: list[str] = []
        for block in payload.get("parsing_res_list") or []:
            if isinstance(block, dict):
                text = str(block.get("block_content") or block.get("content") or "").strip()
            else:
                text = str(getattr(block, "block_content", None) or getattr(block, "content", None) or "").strip()
            if text:
                texts.append(text)
        return "\n".join(texts).strip()

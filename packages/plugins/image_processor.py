from __future__ import annotations

import base64
import logging
from pathlib import Path

from PIL import Image

from packages.core.models import DocumentAsset, NormalizedDocument, NormalizedTextBlock
from packages.integrations.ocr_adapter import OcrAdapter

from .base import DocumentProcessorPlugin


logger = logging.getLogger(__name__)
SUPPORTED_IMAGE_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".bmp": "image/bmp",
    ".webp": "image/webp",
}
MAX_IMAGE_BYTES = 10 * 1024 * 1024


class ImageProcessorPlugin(DocumentProcessorPlugin):
    plugin_id = "image"
    supported_types = tuple(SUPPORTED_IMAGE_TYPES.keys())

    def __init__(self, ocr_adapter: OcrAdapter | None = None) -> None:
        self.ocr_adapter = ocr_adapter or OcrAdapter()

    def can_handle(self, input_file: Path) -> bool:
        return input_file.suffix.lower() in self.supported_types

    def preprocess(self, input_file: Path, run_context: dict[str, object]) -> NormalizedDocument:
        run_dir = Path(str(run_context["run_dir"]))
        logger.info("图片预处理开始: file=%s", input_file.name)
        asset = _build_image_asset(input_file)
        ocr = self.ocr_adapter.extract(input_file, run_dir=run_dir)

        blocks: list[NormalizedTextBlock] = []
        if ocr.full_text:
            blocks.append(
                NormalizedTextBlock(
                    block_id=f"{input_file.stem}-ocr",
                    block_type="OCRText",
                    text=ocr.full_text,
                    source_path="ocr",
                )
            )
        else:
            blocks.append(
                NormalizedTextBlock(
                    block_id=f"{input_file.stem}-ocr-empty",
                    block_type="OCRText",
                    text="(OCR 未识别到文字)",
                    source_path="ocr",
                )
            )

        line_text = "\n".join(
            f"- {line.text}" + (f" (score={line.score:.3f})" if line.score is not None else "")
            for line in ocr.lines
        ).strip()
        if line_text:
            blocks.append(
                NormalizedTextBlock(
                    block_id=f"{input_file.stem}-ocr-lines",
                    block_type="OCRLines",
                    text=line_text,
                    source_path="ocr.lines",
                )
            )

        return NormalizedDocument(
            document_id=input_file.stem,
            source_name=input_file.name,
            source_kind="image",
            original_path=str(input_file),
            text_blocks=blocks,
            assets=[asset],
            metadata={
                "plugin_id": self.plugin_id,
                "ocr_line_count": len(ocr.lines),
                "ocr_timings": ocr.timings,
            },
        )


def _build_image_asset(input_path: Path) -> DocumentAsset:
    mime_type = SUPPORTED_IMAGE_TYPES.get(input_path.suffix.lower())
    if not mime_type:
        raise RuntimeError(f"unsupported_image_type:{input_path.suffix.lower()}")

    raw_bytes = input_path.read_bytes()
    if len(raw_bytes) > MAX_IMAGE_BYTES:
        raise RuntimeError(f"image_size_exceeded:{input_path.name}")

    with Image.open(input_path) as image:
        width, height = image.size
    if width <= 10 or height <= 10:
        raise RuntimeError(f"image_too_small:{input_path.name}")

    data = base64.b64encode(raw_bytes).decode("utf-8")
    return DocumentAsset(
        asset_id="IMAGE_1",
        mime_type=mime_type,
        data_url=f"data:{mime_type};base64,{data}",
        position=input_path.name,
        context_text="上传的原始图片",
    )

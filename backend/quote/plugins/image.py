from __future__ import annotations

import base64
import logging
from pathlib import Path

from PIL import Image

from backend.common.models import DocumentAsset, NormalizedDocument, NormalizedTextBlock
from backend.quote.ocr_client import OcrClient
from backend.quote.plugins.base import DocumentProcessorPlugin


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

    def __init__(self, *, ocr_client: OcrClient | None = None) -> None:
        self.ocr_client = ocr_client or OcrClient()

    def can_handle(self, input_file: Path) -> bool:
        return input_file.suffix.lower() in self.supported_types

    def preprocess(self, input_file: Path, run_context: dict[str, object]) -> NormalizedDocument:
        logger.info("图片预处理开始: file=%s", input_file.name)
        asset = _build_image_asset(input_file)
        result = self.ocr_client.extract_markdown(input_file)

        markdown_text = result.markdown_text.strip() or "(OCR 未识别到文字)"
        blocks = [
            NormalizedTextBlock(
                block_id=f"{input_file.stem}-ocr-markdown",
                block_type="Markdown",
                text=markdown_text,
                source_path="ocr",
            )
        ]

        return NormalizedDocument(
            document_id=input_file.stem,
            source_name=input_file.name,
            source_kind="image",
            original_path=str(input_file),
            text_blocks=blocks,
            assets=[asset],
            metadata={
                "plugin_id": self.plugin_id,
                "ocr_page_count": result.page_count,
                "ocr_elapsed_ms": result.elapsed_ms,
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

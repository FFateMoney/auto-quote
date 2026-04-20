from __future__ import annotations

import base64
import io
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image
import pypdfium2 as pdfium

from backend.common.logging import append_run_log
from backend.common.models import DocumentAsset, NormalizedTextBlock


logger = logging.getLogger(__name__)
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_PDF_PAGES = 250
PDF_RENDER_SCALE = 2.0
PDF_RENDER_FORMAT = "PNG"
PDF_RENDER_MIME = "image/png"


@dataclass(slots=True)
class PdfNormalizedPayload:
    text_blocks: list[NormalizedTextBlock]
    assets: list[DocumentAsset]
    metadata: dict[str, Any]


class PdfAdapter:
    def extract(self, input_path: Path, *, run_dir: Path) -> PdfNormalizedPayload:
        logger.info("PDF 预处理开始: file=%s", input_path.name)
        append_run_log(run_dir, f"PDF 预处理开始: {input_path.name}")

        try:
            document = pdfium.PdfDocument(str(input_path))
        except Exception as exc:
            raise RuntimeError(f"pdf_read_failed:{input_path.name}:{str(exc)}") from exc

        try:
            page_count = len(document)
            if page_count <= 0:
                raise RuntimeError("pdf_has_no_pages")
            if page_count > MAX_PDF_PAGES:
                raise RuntimeError("pdf_page_count_exceeded")
            assets = self._render_page_assets(document)
        finally:
            document.close()

        text_blocks = [
            NormalizedTextBlock(
                block_id=f"{input_path.stem}-pages-as-images",
                block_type="PdfRenderNotice",
                text="该 PDF 已按页转换为图片输入，请结合各页图片理解内容。",
                source_path="pdf.pages",
            )
        ]
        metadata: dict[str, Any] = {
            "page_count": page_count,
            "text_block_count": len(text_blocks),
            "image_count": len(assets),
            "pdf_input_mode": "pages_as_images",
        }
        append_run_log(run_dir, f"PDF 预处理完成: {input_path.name} | pages={page_count} | images={len(assets)}")
        return PdfNormalizedPayload(text_blocks=text_blocks, assets=assets, metadata=metadata)

    def _render_page_assets(self, document: pdfium.PdfDocument) -> list[DocumentAsset]:
        assets: list[DocumentAsset] = []
        for page_index in range(len(document)):
            page = document[page_index]
            bitmap = None
            try:
                bitmap = page.render(scale=PDF_RENDER_SCALE)
                image = bitmap.to_pil().convert("RGB")
                assets.append(self._build_asset(image=image, page_num=page_index + 1))
            except Exception as exc:
                raise RuntimeError(f"pdf_page_render_failed:page_{page_index + 1}:{str(exc)}") from exc
            finally:
                if bitmap is not None:
                    bitmap.close()
                page.close()
        return assets

    def _build_asset(self, *, image: Image.Image, page_num: int) -> DocumentAsset:
        width, height = image.size
        if width <= 10 or height <= 10:
            raise RuntimeError(f"pdf_page_too_small:page_{page_num}")
        buffer = io.BytesIO()
        image.save(buffer, format=PDF_RENDER_FORMAT, optimize=True)
        raw_bytes = buffer.getvalue()
        if len(raw_bytes) > MAX_IMAGE_BYTES:
            raise RuntimeError(f"pdf_page_image_size_exceeded:page_{page_num}")
        data = base64.b64encode(raw_bytes).decode("utf-8")
        return DocumentAsset(
            asset_id=f"IMAGE_{page_num}",
            mime_type=PDF_RENDER_MIME,
            data_url=f"data:{PDF_RENDER_MIME};base64,{data}",
            position=f"page={page_num}",
            context_text=f"PDF 第 {page_num} 页",
        )

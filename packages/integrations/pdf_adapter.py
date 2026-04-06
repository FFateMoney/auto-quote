from __future__ import annotations

import base64
import io
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image
from pypdf import PdfReader

from packages.core.logging_utils import append_run_log
from packages.core.models import DocumentAsset, NormalizedTextBlock

from .ocr_adapter import OcrAdapter


logger = logging.getLogger(__name__)
MAX_IMAGE_BYTES = 10 * 1024 * 1024
SUPPORTED_IMAGE_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "bmp": "image/bmp",
    "gif": "image/gif",
    "webp": "image/webp",
    "tiff": "image/tiff",
}
IMAGE_PLACEHOLDER_RE = re.compile(r"\[(IMAGE_\d+)\]")


@dataclass(slots=True)
class PdfNormalizedPayload:
    text_blocks: list[NormalizedTextBlock]
    assets: list[DocumentAsset]
    metadata: dict[str, Any]


class PdfAdapter:
    def __init__(self, *, ocr_adapter: OcrAdapter | None = None, enable_ocr: bool = True) -> None:
        self.ocr_adapter = ocr_adapter or OcrAdapter()
        self.enable_ocr = enable_ocr

    def extract(self, input_path: Path, *, run_dir: Path) -> PdfNormalizedPayload:
        logger.info("PDF 预处理开始: file=%s", input_path.name)
        append_run_log(run_dir, f"PDF 预处理开始: {input_path.name}")

        try:
            reader = PdfReader(str(input_path))
        except Exception as exc:
            raise RuntimeError(f"pdf_read_failed:{input_path.name}:{str(exc)}") from exc

        text_blocks: list[NormalizedTextBlock] = []
        assets: list[DocumentAsset] = []
        metadata: dict[str, Any] = {
            "page_count": len(reader.pages),
            "text_block_count": 0,
            "image_count": 0,
        }

        extracted_dir = run_dir / "pdf_images" / input_path.stem
        extracted_dir.mkdir(parents=True, exist_ok=True)

        for page_num, page in enumerate(reader.pages, start=1):
            page_blocks, page_assets = self._extract_page(
                page=page,
                page_num=page_num,
                extracted_dir=extracted_dir,
                asset_offset=len(assets),
                run_dir=run_dir,
            )
            text_blocks.extend(page_blocks)
            assets.extend(page_assets)
            metadata["text_block_count"] += len(page_blocks)
            metadata["image_count"] += len(page_assets)

        if metadata["image_count"] > 250:
            raise RuntimeError("pdf_image_count_exceeded")

        append_run_log(
            run_dir,
            f"PDF 预处理完成: {input_path.name} | pages={metadata['page_count']} | blocks={metadata['text_block_count']} | images={metadata['image_count']}",
        )
        return PdfNormalizedPayload(text_blocks=text_blocks, assets=assets, metadata=metadata)

    def _extract_page(
        self,
        *,
        page: Any,
        page_num: int,
        extracted_dir: Path,
        asset_offset: int,
        run_dir: Path,
    ) -> tuple[list[NormalizedTextBlock], list[DocumentAsset]]:
        blocks: list[NormalizedTextBlock] = []
        assets: list[DocumentAsset] = []

        # Extract text from page
        text = page.extract_text() or ""
        text = text.strip()

        # Extract images from page if OCR is enabled
        page_images: list[DocumentAsset] = []
        if self.enable_ocr:
            page_images = self._extract_page_images(
                page=page,
                page_num=page_num,
                extracted_dir=extracted_dir,
                asset_offset=asset_offset + len(assets),
                run_dir=run_dir,
            )
            assets.extend(page_images)

        # Build text block with both text and image references
        fragments: list[str] = [f"[PAGE] {page_num}"]

        if text:
            fragments.append(text)

        if page_images:
            for img_asset in page_images:
                fragments.append(f"图片引用=[{img_asset.asset_id}]")

        block_text = "\n".join(fragment for fragment in fragments if fragment).strip()

        if block_text and block_text != f"[PAGE] {page_num}":
            context_text = self._context_text(block_text)
            for img_asset in page_images:
                img_asset.context_text = context_text

            blocks.append(
                NormalizedTextBlock(
                    block_id=f"page-{page_num}",
                    block_type="PdfPage",
                    text=block_text,
                    source_path=f"page_{page_num}",
                )
            )

        return blocks, assets

    def _extract_page_images(
        self,
        *,
        page: Any,
        page_num: int,
        extracted_dir: Path,
        asset_offset: int,
        run_dir: Path,
    ) -> list[DocumentAsset]:
        assets: list[DocumentAsset] = []

        try:
            # Extract images from page resources
            if "/XObject" not in page["/Resources"]:
                return assets

            xobjects = page["/Resources"]["/XObject"].get_object()
            if not xobjects:
                return assets

            image_index = 0
            for obj_name in xobjects:
                xobject = xobjects[obj_name]
                if xobject["/Subtype"] != "/Image":
                    continue

                image_index += 1
                try:
                    raw_bytes = xobject.get_data()
                    if not raw_bytes:
                        continue

                    # Build asset
                    asset_seq = asset_offset + len(assets) + 1
                    asset = self._build_asset(
                        raw_bytes=raw_bytes,
                        seq=asset_seq,
                        page_num=page_num,
                        image_index=image_index,
                    )

                    # Save image to file for OCR
                    temp_path = extracted_dir / f"{asset.asset_id}.png"
                    temp_path.write_bytes(raw_bytes)

                    # Run OCR if enabled
                    ocr = self.ocr_adapter.extract(temp_path, run_dir=run_dir)
                    ocr_text = self._ocr_text(ocr.full_text) if ocr.full_text else ""

                    # Store OCR result in metadata if available
                    if ocr_text:
                        if not hasattr(asset, '_ocr_text'):
                            asset._ocr_text = ocr_text

                    assets.append(asset)
                except Exception as exc:
                    logger.warning(
                        "PDF 页面图片处理失败: page=%s image=%s error=%s",
                        page_num,
                        image_index,
                        str(exc),
                    )
                    continue

        except Exception as exc:
            logger.warning(
                "PDF 页面图片提取失败: page=%s error=%s",
                page_num,
                str(exc),
            )

        return assets

    def _build_asset(
        self,
        *,
        raw_bytes: bytes,
        seq: int,
        page_num: int,
        image_index: int,
    ) -> DocumentAsset:
        if len(raw_bytes) > MAX_IMAGE_BYTES:
            raise RuntimeError(f"pdf_image_size_exceeded:page_{page_num}:image_{image_index}")

        # Determine mime type by checking image format
        try:
            with Image.open(io.BytesIO(raw_bytes)) as pil_image:
                width, height = pil_image.size
                # Get format and convert to supported type
                fmt = pil_image.format or "PNG"
                mime_type = SUPPORTED_IMAGE_TYPES.get(fmt.lower(), "image/png")
        except Exception as exc:
            raise RuntimeError(f"pdf_image_invalid:page_{page_num}:image_{image_index}:{str(exc)}")

        if width <= 10 or height <= 10:
            raise RuntimeError(f"pdf_image_too_small:page_{page_num}:image_{image_index}")

        data = base64.b64encode(raw_bytes).decode("utf-8")
        return DocumentAsset(
            asset_id=f"IMAGE_{seq}",
            mime_type=mime_type,
            data_url=f"data:{mime_type};base64,{data}",
            position=f"page={page_num},image={image_index}",
            context_text="",
        )

    def _ocr_text(self, value: str) -> str:
        return re.sub(r"\s+", " ", str(value or "")).strip()

    def _context_text(self, value: str) -> str:
        lines: list[str] = []
        for line in str(value or "").splitlines():
            clean = IMAGE_PLACEHOLDER_RE.sub("", line).strip()
            if not clean:
                continue
            if clean.endswith("="):
                continue
            lines.append(clean)
        return re.sub(r"\s+", " ", "\n".join(lines)).strip()

from __future__ import annotations

import base64
import io
import re
from pathlib import Path

from PIL import Image

from packages.core.models import DocumentAsset, NormalizedDocument, NormalizedTextBlock
from packages.integrations.aiword_adapter import export_content_view

from .base import DocumentProcessorPlugin


IMAGE_PLACEHOLDER_RE = re.compile(r"\[(IMAGE_\d+)\]")
MAX_IMAGE_BYTES = 10 * 1024 * 1024
SUPPORTED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/bmp", "image/gif", "image/webp", "image/tiff"}


class WordProcessorPlugin(DocumentProcessorPlugin):
    plugin_id = "word"
    supported_types = (".docx",)

    def can_handle(self, input_file: Path) -> bool:
        return input_file.suffix.lower() in self.supported_types

    def preprocess(self, input_file: Path, run_context: dict[str, object]) -> NormalizedDocument:
        output_dir = Path(str(run_context["run_dir"])) / "preprocessed" / input_file.stem
        view = export_content_view(input_file, output_dir)
        blocks, assets = _normalize_content_view(view)
        return NormalizedDocument(
            document_id=input_file.stem,
            source_name=input_file.name,
            source_kind="word",
            original_path=str(input_file),
            text_blocks=blocks,
            assets=assets,
            metadata={"plugin_id": self.plugin_id},
        )


def _normalize_content_view(content_view: dict) -> tuple[list[NormalizedTextBlock], list[DocumentAsset]]:
    document = content_view.get("document")
    if not isinstance(document, dict):
        raise RuntimeError("word_content_view_missing_document")
    body = document.get("body")
    if not isinstance(body, list):
        raise RuntimeError("word_content_view_missing_body")

    blocks: list[NormalizedTextBlock] = []
    assets: list[DocumentAsset] = []
    for index, block in enumerate(body):
        block_text = _render_block(block, assets, source_path=f"body[{index}]").strip()
        if not block_text:
            continue
        blocks.append(
            NormalizedTextBlock(
                block_id=str(block.get("id") or f"block-{index}"),
                block_type=str(block.get("type") or "Unknown"),
                text=block_text,
                source_path=f"body[{index}]",
            )
        )
    if len(assets) > 250:
        raise RuntimeError("word_image_count_exceeded")
    return blocks, assets


def _render_block(block: dict, assets: list[DocumentAsset], *, source_path: str) -> str:
    block_type = str(block.get("type") or "")
    if block_type in {"Paragraph", "Heading"}:
        text = _render_inline_items(block.get("content") or [], assets, source_path=f"{source_path}.content")
        text = text.strip()
        if block_type == "Heading":
            level = block.get("level")
            prefix = f"[HEADING {level}] " if level else "[HEADING] "
            return (prefix + text).strip()
        return text
    if block_type == "Table":
        rows = block.get("rows") or []
        rendered_rows: list[str] = []
        for row_index, row in enumerate(rows):
            cells = row.get("cells") or []
            rendered_cells: list[str] = []
            for cell_index, cell in enumerate(cells):
                fragments = []
                for content_index, child in enumerate(cell.get("content") or []):
                    child_text = _render_block(
                        child,
                        assets,
                        source_path=f"{source_path}.rows[{row_index}].cells[{cell_index}].content[{content_index}]",
                    ).strip()
                    if child_text:
                        fragments.append(child_text)
                rendered_cells.append("\n".join(fragments).strip())
            if any(cell for cell in rendered_cells):
                rendered_rows.append(" | ".join(rendered_cells))
        if rendered_rows:
            return "[TABLE]\n" + "\n".join(rendered_rows)
        return ""
    return str(block.get("text") or "").strip()


def _render_inline_items(items: list[dict], assets: list[DocumentAsset], *, source_path: str) -> str:
    rendered: list[str] = []
    new_assets: list[DocumentAsset] = []
    for index, item in enumerate(items):
        item_type = str(item.get("type") or "")
        current_path = f"{source_path}[{index}]"
        if item_type == "Text":
            rendered.append(str(item.get("text") or ""))
            continue
        if item_type == "InlineImage":
            asset = _build_asset(item, len(assets) + 1, current_path)
            assets.append(asset)
            new_assets.append(asset)
            rendered.append(f"[{asset.asset_id}]")
            continue
        if item_type == "Hyperlink":
            rendered.append(_render_inline_items(item.get("content") or [], assets, source_path=f"{current_path}.content"))
            continue
        rendered.append(str(item.get("text") or ""))

    text = "".join(rendered)
    context = IMAGE_PLACEHOLDER_RE.sub("", text)
    context = re.sub(r"\s+", " ", context).strip()
    if context:
        for asset in new_assets:
            if asset.context_text:
                continue
            asset.context_text = context  # type: ignore[misc]
    return text


def _build_asset(item: dict, seq: int, source_path: str) -> DocumentAsset:
    data = str(item.get("data") or "").strip()
    mime_type = str(item.get("content_type") or "").strip().lower()
    if not data:
        raise RuntimeError(f"word_image_missing_data:{source_path}")
    if mime_type not in SUPPORTED_IMAGE_TYPES:
        raise RuntimeError(f"word_image_unsupported_type:{mime_type}")
    raw_bytes = base64.b64decode(data, validate=True)
    if len(raw_bytes) > MAX_IMAGE_BYTES:
        raise RuntimeError(f"word_image_size_exceeded:{source_path}")
    with Image.open(io.BytesIO(raw_bytes)) as image:
        width, height = image.size
    if width <= 10 or height <= 10:
        raise RuntimeError(f"word_image_too_small:{source_path}")
    ratio = max(width / height, height / width)
    if ratio > 200:
        raise RuntimeError(f"word_image_aspect_invalid:{source_path}")
    return DocumentAsset(
        asset_id=f"IMAGE_{seq}",
        mime_type=mime_type,
        data_url=f"data:{mime_type};base64,{data}",
        position=source_path,
        context_text="",
    )

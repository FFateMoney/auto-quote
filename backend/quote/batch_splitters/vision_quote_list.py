from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from backend.common.logging import append_run_log
from backend.quote.batch_splitters.base import BatchSplitItem, BatchSplitResult
from backend.quote.batch_splitters.rendering import ExcelPageRenderer
from backend.quote.row_adapters.vision_quote_list import VisionQuoteListPayload, VisionQuoteListRowAdapter


class VisionQuoteListSplitter:
    strategy_id = "vision_quote_list"

    def __init__(
        self,
        *,
        requester: object,
        renderer: ExcelPageRenderer | None = None,
        row_adapter: VisionQuoteListRowAdapter | None = None,
    ) -> None:
        self.requester = requester
        self.renderer = renderer or ExcelPageRenderer()
        self.row_adapter = row_adapter or VisionQuoteListRowAdapter()

    def split(self, workbook_path: Path, *, run_dir: Path) -> BatchSplitResult:
        output_dir = run_dir / "batch_vision"
        append_run_log(run_dir, f"批量视觉切分开始: {workbook_path.name}")
        image_paths = self.renderer.render(workbook_path, output_dir=output_dir)
        append_run_log(run_dir, f"批量视觉切分页面渲染完成: pages={len(image_paths)}")
        result = self.requester.split_batch_excel_with_vision_quote_list(image_paths, run_dir=run_dir)
        items: list[BatchSplitItem] = []
        used_ids: set[str] = set()
        for index, quote in enumerate(result.items, start=1):
            quote_id = _quote_id(index, quote, used_ids=used_ids)
            used_ids.add(quote_id)
            items.append(
                BatchSplitItem(
                    quote_id=quote_id,
                    title=_title(index, quote),
                    source_summary=f"vision_quote_index={index} pages={len(image_paths)}",
                    row_adapter=self.row_adapter,
                    row_payload=VisionQuoteListPayload(quote=quote, notes=[f"视觉报价列表第 {index} 条"]),
                )
            )
        append_run_log(run_dir, f"批量视觉切分完成: quotes={len(items)}")
        return BatchSplitResult(
            items=items,
            summary=f"视觉识别生成 {len(items)} 个子报价",
            raw_response=result.raw_response,
            notes=[f"视觉页面数：{len(image_paths)}"],
        )


def _title(index: int, quote: dict[str, Any]) -> str:
    experiment = str(quote.get("experiment_type") or "").strip() or f"报价需求{index}"
    dims = "x".join(str(quote.get(key) or "").strip() for key in ("length", "width", "height") if quote.get(key))
    return f"{experiment} {dims}".strip()


def _quote_id(index: int, quote: dict[str, Any], *, used_ids: set[str]) -> str:
    base = "_".join(
        part
        for part in (
            str(quote.get("experiment_type") or ""),
            str(quote.get("standard_no") or ""),
            str(index),
        )
        if part
    )
    candidate = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "_", base).strip("_") or f"quote_{index}"
    while candidate in used_ids:
        candidate = f"{candidate}_{index}"
    return candidate

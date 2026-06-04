from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from backend.common.logging import append_run_log
from backend.quote.adapters.excel import ExcelAdapter, ExcelNormalizedPayload


logger = logging.getLogger(__name__)


EXCEL_CHUNK_EXTRACTION_HINTS: tuple[str, ...] = (
    "当前文档是从批量 Excel 中切分出的一个独立报价需求。",
    "该切分产物保留了原 Excel 坐标，空白区域或未包含区域不代表没有报价需求。",
    "shared_ranges 是该报价需求的共享上下文，main_range 是该报价需求的核心区域。",
    "对于表格型内容，请逐行判断是否包含可报价的测试、试验、检验或服务项目；每个明确项目通常应抽取为一条报价行。",
    "表格中的明细行可能通过编号、项目名、测试描述、测试条件、标准、样品数量或周期等字段表达测试项目，不要求固定列名。",
    "请优先依据测试项目、测试条件、样品信息、数量、周期、标准等内容抽取报价行。",
    "如果文档中存在报价、单价、总价等空列，不要仅因此判断没有报价需求。",
)


class WorkbookExcelAdapter(ExcelAdapter):
    """Excel adapter for an already materialized openpyxl Workbook.

    This adapter intentionally lives beside `ExcelAdapter` instead of adding a
    second input mode to it. It reuses the existing sheet, row, and image
    extraction behavior so an in-memory Workbook is normalized the same way as
    an uploaded .xlsx file.
    """

    def extract(
        self,
        workbook: Any,
        *,
        source_name: str,
        run_dir: Path,
        source_stem: str | None = None,
        chunk_label: str | None = None,
        main_range: str | None = None,
        shared_ranges: list[str] | None = None,
    ) -> ExcelNormalizedPayload:
        display_name = str(source_name or "workbook").strip() or "workbook"
        safe_stem = Path(source_stem or Path(display_name).stem or "workbook").name
        normalized_shared_ranges = list(shared_ranges or [])

        logger.info("Workbook Excel 预处理开始: source=%s", display_name)
        append_run_log(run_dir, f"Workbook Excel 预处理开始: {display_name}")

        extracted_dir = run_dir / "excel_images" / safe_stem
        extracted_dir.mkdir(parents=True, exist_ok=True)

        text_blocks = []
        assets = []
        metadata: dict[str, Any] = {
            "sheet_count": len(workbook.worksheets),
            "row_count": 0,
            "image_count": 0,
            "source_name": display_name,
            "source_kind": "excel_chunk_workbook",
            "chunk_label": chunk_label,
            "main_range": main_range,
            "shared_ranges": normalized_shared_ranges,
            "extraction_hints": list(EXCEL_CHUNK_EXTRACTION_HINTS),
        }

        for sheet in workbook.worksheets:
            sheet_blocks, sheet_assets, sheet_row_count = self._extract_sheet(
                sheet=sheet,
                extracted_dir=extracted_dir,
                asset_offset=len(assets),
                run_dir=run_dir,
            )
            text_blocks.extend(sheet_blocks)
            assets.extend(sheet_assets)
            metadata["row_count"] += sheet_row_count
            metadata["image_count"] += len(sheet_assets)

        if metadata["image_count"] > 250:
            raise RuntimeError("excel_image_count_exceeded")

        append_run_log(
            run_dir,
            f"Workbook Excel 预处理完成: {display_name} | rows={metadata['row_count']} | images={metadata['image_count']}",
        )
        return ExcelNormalizedPayload(text_blocks=text_blocks, assets=assets, metadata=metadata)

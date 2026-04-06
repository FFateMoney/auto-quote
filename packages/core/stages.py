DOCUMENT_EXTRACTED = "document_extracted"
TEST_TYPE_MATCHED = "test_type_matched"
EQUIPMENT_SELECTED = "equipment_selected"
STANDARD_ENRICHED = "standard_enriched"
FINAL_QUOTED = "final_quoted"

STAGE_LABELS: dict[str, str] = {
    DOCUMENT_EXTRACTED: "文件抽取",
    STANDARD_ENRICHED: "标准补充",
    TEST_TYPE_MATCHED: "实验类型匹配",
    EQUIPMENT_SELECTED: "设备筛选",
    FINAL_QUOTED: "最终报价",
}

ORDERED_STAGES: tuple[str, ...] = (
    DOCUMENT_EXTRACTED,
    TEST_TYPE_MATCHED,
    EQUIPMENT_SELECTED,
    STANDARD_ENRICHED,
    FINAL_QUOTED,
)

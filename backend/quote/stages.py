DOCUMENT_EXTRACTED = "document_extracted"
TEST_TYPE_MATCHED = "test_type_matched"
EQUIPMENT_SELECTED_INITIAL = "equipment_selected_initial"
STANDARD_ENRICHED = "standard_enriched"
EQUIPMENT_SELECTED_ENRICHED = "equipment_selected_enriched"
FINAL_QUOTED = "final_quoted"

STAGE_LABELS: dict[str, str] = {
    DOCUMENT_EXTRACTED: "文件抽取",
    TEST_TYPE_MATCHED: "实验类型匹配",
    EQUIPMENT_SELECTED_INITIAL: "设备初筛",
    STANDARD_ENRICHED: "标准补充",
    EQUIPMENT_SELECTED_ENRICHED: "标准补充后复筛",
    FINAL_QUOTED: "最终报价",
}

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


class SourceRef(BaseModel):
    kind: str
    path: str
    label: str = ""


class DocumentAsset(BaseModel):
    asset_id: str
    asset_type: Literal["image"] = "image"
    mime_type: str
    data_url: str
    position: str = ""
    context_text: str = ""


class NormalizedTextBlock(BaseModel):
    block_id: str
    block_type: str
    text: str
    source_path: str = ""


class NormalizedDocument(BaseModel):
    document_id: str
    source_name: str
    source_kind: str
    original_path: str
    text_blocks: list[NormalizedTextBlock] = Field(default_factory=list)
    assets: list[DocumentAsset] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class UploadedDocument(BaseModel):
    document_id: str
    file_name: str
    media_type: str = ""
    stored_path: str
    local_path: str = Field(default="", exclude=True)
    source_kind: str = ""
    status: str = "uploaded"
    notes: str = ""


class ManualOverride(BaseModel):
    field_name: str
    value: Any
    updated_at: str = Field(default_factory=_now_iso)


class EquipmentRejection(BaseModel):
    equipment_id: str
    equipment_label: str = ""
    reasons: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)


class EquipmentProfile(BaseModel):
    equipment_id: str
    equipment_label: str = ""
    attributes: dict[str, Any] = Field(default_factory=dict)


class StandardDocumentRecord(BaseModel):
    doc_id: str
    standard_key: str = ""
    standard_code: str = ""
    title: str = ""
    path: str
    category: str = ""
    language: str = ""
    page_count: int = 0
    file_hash: str = ""
    indexed_at: str = Field(default_factory=_now_iso)
    chunk_count: int = 0


class StandardChunk(BaseModel):
    chunk_id: str
    doc_id: str
    standard_code: str = ""
    path: str
    page_start: int = 0
    page_end: int = 0
    section_id: str = ""
    section_title: str = ""
    parent_section_id: str = ""
    chunk_type: Literal["section", "subsection", "table_row", "page_fallback"] = "section"
    text: str = ""
    normalized_text: str = ""
    keywords: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    vector_row: int | None = None


class StandardEvidence(BaseModel):
    chunk_id: str
    standard_code: str = ""
    doc_title: str = ""
    path: str = ""
    page_start: int = 0
    page_end: int = 0
    section_id: str = ""
    section_title: str = ""
    score: float = 0.0
    match_reasons: list[str] = Field(default_factory=list)
    text: str = ""


class StandardContextDecision(BaseModel):
    decision: Literal["sufficient", "need_parent", "not_standard_match"] = "not_standard_match"
    reason: str = ""
    missing: list[str] = Field(default_factory=list)


class StandardResolutionResult(BaseModel):
    row_id: str = ""
    status: Literal["resolved", "missing"] = "missing"
    evidences: list[StandardEvidence] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class StandardIndexManifest(BaseModel):
    version: int = 1
    updated_at: str = Field(default_factory=_now_iso)
    documents: list[StandardDocumentRecord] = Field(default_factory=list)


class FormRow(BaseModel):
    row_id: str = Field(default_factory=lambda: uuid4().hex)
    raw_test_type: str = ""
    canonical_test_type: str = ""
    standard_codes: list[str] = Field(default_factory=list)
    pricing_mode: str = ""
    pricing_quantity: float | None = None
    repeat_count: float | None = None
    sample_length_mm: float | None = None
    sample_width_mm: float | None = None
    sample_height_mm: float | None = None
    sample_weight_kg: float | None = None
    required_temp_min: float | None = None
    required_temp_max: float | None = None
    required_humidity_min: float | None = None
    required_humidity_max: float | None = None
    required_temp_change_rate: float | None = None
    required_freq_min: float | None = None
    required_freq_max: float | None = None
    required_accel_min: float | None = None
    required_accel_max: float | None = None
    required_displacement_min: float | None = None
    required_displacement_max: float | None = None
    required_irradiance_min: float | None = None
    required_irradiance_max: float | None = None
    required_water_temp_min: float | None = None
    required_water_temp_max: float | None = None
    required_water_flow_min: float | None = None
    required_water_flow_max: float | None = None
    source_text: str = ""
    conditions_text: str = ""
    sample_info_text: str = ""

    source_refs: list[SourceRef] = Field(default_factory=list)
    stage_status: str = ""
    missing_fields: list[str] = Field(default_factory=list)
    blocking_reason: str = ""
    matched_test_type_id: int | None = None
    candidate_equipment_ids: list[str] = Field(default_factory=list)
    candidate_equipment_profiles: list[EquipmentProfile] = Field(default_factory=list)
    selected_equipment_id: str = ""
    rejected_equipment: list[EquipmentRejection] = Field(default_factory=list)
    base_fee: float | None = None
    unit_price: float | None = None
    total_price: float | None = None
    formula: str = ""
    price_unit: str = ""
    manual_overrides: dict[str, ManualOverride] = Field(default_factory=dict)
    standard_evidences: list[StandardEvidence] = Field(default_factory=list)
    standard_match_notes: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def ensure_row_id(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        if str(data.get("row_id") or "").strip():
            return data
        copied = dict(data)
        copied["row_id"] = uuid4().hex
        return copied

    @classmethod
    def schema_example(cls) -> dict[str, Any]:
        return cls(
            raw_test_type="高温试验",
            canonical_test_type="高温",
            standard_codes=["GB/T 2423.1"],
            pricing_mode="小时",
            pricing_quantity=24,
            repeat_count=1,
            sample_length_mm=100,
            sample_width_mm=80,
            sample_height_mm=50,
            required_temp_max=85,
            source_text="样品进行高温 85C 24h 试验",
            conditions_text="85C 24h",
            sample_info_text="样品尺寸 100x80x50mm",
        ).model_dump()


class FormStageSnapshot(BaseModel):
    stage_id: str
    label: str
    items: list[FormRow] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=_now_iso)


class RunArtifacts(BaseModel):
    run_state_path: str = ""
    uploaded_dir: str = ""
    exported_files: list[str] = Field(default_factory=list)


class RunState(BaseModel):
    run_id: str
    current_stage: str = ""
    overall_status: Literal["running", "waiting_manual_input", "completed", "failed"] = "running"
    uploaded_documents: list[UploadedDocument] = Field(default_factory=list)
    form_stages: list[FormStageSnapshot] = Field(default_factory=list)
    final_form_items: list[FormRow] = Field(default_factory=list)
    next_action: str = ""
    artifacts: RunArtifacts = Field(default_factory=RunArtifacts)
    errors: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)

    def touch(self) -> None:
        self.updated_at = _now_iso()


class ResumeRequest(BaseModel):
    row_id: str
    field_values: dict[str, Any]

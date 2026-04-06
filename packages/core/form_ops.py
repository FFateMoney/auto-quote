from __future__ import annotations

import re
from typing import Any

from .models import FormRow, ManualOverride, SourceRef


LIST_MERGE_FIELDS = {
    "standard_codes",
    "candidate_equipment_ids",
    "missing_fields",
}

SCALAR_FIELDS = {
    "raw_test_type",
    "canonical_test_type",
    "pricing_mode",
    "pricing_quantity",
    "repeat_count",
    "sample_length_mm",
    "sample_width_mm",
    "sample_height_mm",
    "sample_weight_kg",
    "required_temp_min",
    "required_temp_max",
    "required_humidity_min",
    "required_humidity_max",
    "required_temp_change_rate",
    "required_freq_min",
    "required_freq_max",
    "required_accel_min",
    "required_accel_max",
    "required_displacement_min",
    "required_displacement_max",
    "required_irradiance_min",
    "required_irradiance_max",
    "required_water_temp_min",
    "required_water_temp_max",
    "required_water_flow_min",
    "required_water_flow_max",
    "source_text",
    "conditions_text",
    "sample_info_text",
    "stage_status",
    "blocking_reason",
    "matched_test_type_id",
    "selected_equipment_id",
    "base_fee",
    "unit_price",
    "total_price",
    "formula",
    "price_unit",
}

NUMERIC_FIELDS = {
    "pricing_quantity",
    "repeat_count",
    "sample_length_mm",
    "sample_width_mm",
    "sample_height_mm",
    "sample_weight_kg",
    "required_temp_min",
    "required_temp_max",
    "required_humidity_min",
    "required_humidity_max",
    "required_temp_change_rate",
    "required_freq_min",
    "required_freq_max",
    "required_accel_min",
    "required_accel_max",
    "required_displacement_min",
    "required_displacement_max",
    "required_irradiance_min",
    "required_irradiance_max",
    "required_water_temp_min",
    "required_water_temp_max",
    "required_water_flow_min",
    "required_water_flow_max",
    "base_fee",
    "unit_price",
    "total_price",
}

RANGE_INPUT_FIELDS: dict[str, tuple[str, str]] = {
    "required_temp_range": ("required_temp_min", "required_temp_max"),
    "required_humidity_range": ("required_humidity_min", "required_humidity_max"),
    "required_freq_range": ("required_freq_min", "required_freq_max"),
    "required_accel_range": ("required_accel_min", "required_accel_max"),
    "required_displacement_range": ("required_displacement_min", "required_displacement_max"),
    "required_irradiance_range": ("required_irradiance_min", "required_irradiance_max"),
    "required_water_temp_range": ("required_water_temp_min", "required_water_temp_max"),
    "required_water_flow_range": ("required_water_flow_min", "required_water_flow_max"),
}


def build_row_key(item: FormRow) -> str:
    canonical = item.canonical_test_type.strip().lower()
    raw = item.raw_test_type.strip().lower()
    standards = "|".join(sorted(code.strip().lower() for code in item.standard_codes if code.strip()))
    if not canonical and not raw and not standards:
        return item.row_id
    return f"{canonical}::{raw}::{standards}"


def merge_rows(current: list[FormRow], incoming: list[FormRow]) -> list[FormRow]:
    merged: list[FormRow] = [row.model_copy(deep=True) for row in current]
    index_by_key = {build_row_key(row): idx for idx, row in enumerate(merged)}

    for row in incoming:
        row_copy = row.model_copy(deep=True)
        key = build_row_key(row_copy)
        if key not in index_by_key:
            merged.append(row_copy)
            index_by_key[key] = len(merged) - 1
            continue
        existing = merged[index_by_key[key]]
        merged[index_by_key[key]] = merge_row(existing, row_copy)
    return merged


def merge_row(existing: FormRow, incoming: FormRow) -> FormRow:
    data = existing.model_dump()
    incoming_data = incoming.model_dump()

    for field_name in LIST_MERGE_FIELDS:
        values = list(data.get(field_name) or []) + list(incoming_data.get(field_name) or [])
        deduped: list[Any] = []
        seen: set[str] = set()
        for value in values:
            key = str(value).strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(value)
        data[field_name] = deduped

    for field_name in SCALAR_FIELDS:
        current_value = data.get(field_name)
        incoming_value = incoming_data.get(field_name)
        if current_value in (None, "", []):
            data[field_name] = incoming_value
            continue
        if field_name in {"source_text", "conditions_text", "sample_info_text"}:
            current_text = str(current_value or "").strip()
            incoming_text = str(incoming_value or "").strip()
            if incoming_text and incoming_text != current_text:
                data[field_name] = f"{current_text}\n{incoming_text}".strip()

    source_refs = [SourceRef.model_validate(item) for item in data.get("source_refs") or []]
    for item in incoming.source_refs:
        if any(ref.kind == item.kind and ref.path == item.path for ref in source_refs):
            continue
        source_refs.append(item)
    data["source_refs"] = [item.model_dump() for item in source_refs]

    manual_overrides = {
        key: ManualOverride.model_validate(value)
        for key, value in (data.get("manual_overrides") or {}).items()
    }
    for key, value in incoming.manual_overrides.items():
        manual_overrides[key] = value
    data["manual_overrides"] = {key: value.model_dump() for key, value in manual_overrides.items()}
    data["row_id"] = existing.row_id
    return FormRow.model_validate(data)


def _normalize_manual_value(field_name: str, value: Any) -> Any:
    if value in (None, ""):
        return None if field_name in NUMERIC_FIELDS else value
    if field_name in {"sample_length_mm", "sample_width_mm", "sample_height_mm"}:
        dims = re.findall(r"-?\d+(?:\.\d+)?", str(value))
        if not dims:
            return None
        return float(dims[0])
    if field_name == "standard_codes":
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        parts = re.split(r"[,，;\n]+", str(value))
        return [part.strip() for part in parts if part.strip()]
    if field_name in NUMERIC_FIELDS:
        return float(value)
    return value


def _parse_range_value(value: Any) -> tuple[float | None, float | None]:
    numbers = [float(item) for item in re.findall(r"-?\d+(?:\.\d+)?", str(value or ""))]
    if not numbers:
        return None, None
    if len(numbers) == 1:
        return numbers[0], numbers[0]
    first, second = numbers[0], numbers[1]
    return (first, second) if first <= second else (second, first)


def apply_manual_values(rows: list[FormRow], row_id: str, field_values: dict[str, Any]) -> list[FormRow]:
    updated: list[FormRow] = []
    for row in rows:
        if row.row_id != row_id:
            updated.append(row.model_copy(deep=True))
            continue
        data = row.model_dump()
        overrides = {
            key: ManualOverride.model_validate(value)
            for key, value in (data.get("manual_overrides") or {}).items()
        }
        for field_name, value in field_values.items():
            if field_name in RANGE_INPUT_FIELDS:
                min_field, max_field = RANGE_INPUT_FIELDS[field_name]
                min_value, max_value = _parse_range_value(value)
                data[min_field] = min_value
                data[max_field] = max_value
                overrides[min_field] = ManualOverride(field_name=min_field, value=min_value)
                overrides[max_field] = ManualOverride(field_name=max_field, value=max_value)
                continue
            normalized_value = _normalize_manual_value(field_name, value)
            data[field_name] = normalized_value
            overrides[field_name] = ManualOverride(field_name=field_name, value=normalized_value)
        data["manual_overrides"] = {key: value.model_dump() for key, value in overrides.items()}
        data["blocking_reason"] = ""
        data["missing_fields"] = []
        updated.append(FormRow.model_validate(data))
    return updated

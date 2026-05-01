from __future__ import annotations

import re
from typing import Any

from backend.quote.models import ExtraStandardRequirement, FormRow, ManualOverride


LIST_MERGE_FIELDS = {
    "standard_codes",
    "candidate_equipment_ids",
    "missing_fields",
    "planned_standard_fields",
    "discovered_standard_fields",
}

SCALAR_FIELDS = {
    "raw_test_type", "canonical_test_type", "pricing_mode", "pricing_quantity",
    "sample_count", "repeat_count", "sample_length_mm", "sample_width_mm", "sample_height_mm",
    "sample_weight_kg", "required_temp_min", "required_temp_max",
    "required_humidity_min", "required_humidity_max", "required_temp_change_rate",
    "required_freq_min", "required_freq_max", "required_accel_min", "required_accel_max",
    "required_displacement_min", "required_displacement_max",
    "required_irradiance_min", "required_irradiance_max",
    "required_water_temp_min", "required_water_temp_max",
    "required_water_flow_min", "required_water_flow_max",
    "source_text", "conditions_text", "sample_info_text",
    "stage_status", "blocking_reason", "matched_test_type_id",
    "selected_equipment_id", "base_fee", "unit_price", "total_price", "formula", "price_unit",
}

NUMERIC_FIELDS = {
    "pricing_quantity", "sample_count", "repeat_count",
    "sample_length_mm", "sample_width_mm", "sample_height_mm", "sample_weight_kg",
    "required_temp_min", "required_temp_max", "required_humidity_min", "required_humidity_max",
    "required_temp_change_rate", "required_freq_min", "required_freq_max",
    "required_accel_min", "required_accel_max", "required_displacement_min", "required_displacement_max",
    "required_irradiance_min", "required_irradiance_max",
    "required_water_temp_min", "required_water_temp_max",
    "required_water_flow_min", "required_water_flow_max",
    "base_fee", "unit_price", "total_price",
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


def build_row_key(row: FormRow) -> str:
    canonical = row.canonical_test_type.strip().lower()
    raw = row.raw_test_type.strip().lower()
    standards = "|".join(sorted(c.strip().lower() for c in row.standard_codes if c.strip()))
    if not canonical and not raw and not standards:
        return row.row_id
    return f"{canonical}::{raw}::{standards}"


def merge_rows(current: list[FormRow], incoming: list[FormRow]) -> list[FormRow]:
    merged = [row.model_copy(deep=True) for row in current]
    index_by_key = {build_row_key(row): idx for idx, row in enumerate(merged)}
    for row in incoming:
        row_copy = row.model_copy(deep=True)
        key = build_row_key(row_copy)
        if key not in index_by_key:
            merged.append(row_copy)
            index_by_key[key] = len(merged) - 1
        else:
            merged[index_by_key[key]] = _merge_row(merged[index_by_key[key]], row_copy)
    return merged


def _merge_row(existing: FormRow, incoming: FormRow) -> FormRow:
    data = existing.model_dump()
    inc = incoming.model_dump()

    for field in LIST_MERGE_FIELDS:
        values = list(data.get(field) or []) + list(inc.get(field) or [])
        seen: set[str] = set()
        deduped: list[Any] = []
        for v in values:
            k = str(v).strip().lower()
            if k and k not in seen:
                seen.add(k)
                deduped.append(v)
        data[field] = deduped

    for field in SCALAR_FIELDS:
        cur, nxt = data.get(field), inc.get(field)
        if cur in (None, "", []):
            data[field] = nxt
        elif field in {"source_text", "conditions_text", "sample_info_text"}:
            cur_s, nxt_s = str(cur or "").strip(), str(nxt or "").strip()
            if nxt_s and nxt_s != cur_s:
                data[field] = f"{cur_s}\n{nxt_s}".strip()

    extra_requirements = [
        ExtraStandardRequirement.model_validate(item)
        for item in data.get("extra_standard_requirements") or []
    ]
    for item in incoming.extra_standard_requirements:
        if not any(
            existing.requirement_name == item.requirement_name
            and existing.requirement_text == item.requirement_text
            and existing.source_section == item.source_section
            for existing in extra_requirements
        ):
            extra_requirements.append(item)
    data["extra_standard_requirements"] = [item.model_dump() for item in extra_requirements]

    overrides = {k: ManualOverride.model_validate(v) for k, v in (data.get("manual_overrides") or {}).items()}
    overrides.update(incoming.manual_overrides)
    data["manual_overrides"] = {k: v.model_dump() for k, v in overrides.items()}
    data["row_id"] = existing.row_id
    return FormRow.model_validate(data)


def apply_manual_values(rows: list[FormRow], row_id: str, field_values: dict[str, Any]) -> list[FormRow]:
    updated: list[FormRow] = []
    for row in rows:
        if row.row_id != row_id:
            updated.append(row.model_copy(deep=True))
            continue
        data = row.model_dump()
        overrides = {k: ManualOverride.model_validate(v) for k, v in (data.get("manual_overrides") or {}).items()}
        for field, value in field_values.items():
            if field in RANGE_INPUT_FIELDS:
                min_f, max_f = RANGE_INPUT_FIELDS[field]
                lo, hi = _parse_range(value)
                data[min_f], data[max_f] = lo, hi
                overrides[min_f] = ManualOverride(field_name=min_f, value=lo)
                overrides[max_f] = ManualOverride(field_name=max_f, value=hi)
            else:
                norm = _normalize_value(field, value)
                data[field] = norm
                overrides[field] = ManualOverride(field_name=field, value=norm)
        data["manual_overrides"] = {k: v.model_dump() for k, v in overrides.items()}
        data["blocking_reason"] = ""
        data["missing_fields"] = []
        updated.append(FormRow.model_validate(data))
    return updated


def _normalize_value(field: str, value: Any) -> Any:
    if value in (None, ""):
        return None if field in NUMERIC_FIELDS else value
    if field in {"sample_length_mm", "sample_width_mm", "sample_height_mm"}:
        nums = re.findall(r"-?\d+(?:\.\d+)?", str(value))
        return float(nums[0]) if nums else None
    if field == "standard_codes":
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        return [p.strip() for p in re.split(r"[,，;\n]+", str(value)) if p.strip()]
    if field in NUMERIC_FIELDS:
        return float(value)
    return value


def _parse_range(value: Any) -> tuple[float | None, float | None]:
    text = str(value or "").strip()
    if "～" in text:
        left, right = text.split("～", 1)
        nums = [_parse_number(left), _parse_number(right)]
        nums = [n for n in nums if n is not None]
    else:
        parsed = _parse_number(text)
        nums = [] if parsed is None else [parsed]
    if not nums:
        return None, None
    if len(nums) == 1:
        return nums[0], nums[0]
    a, b = nums[0], nums[1]
    return (a, b) if a <= b else (b, a)


def _parse_number(value: Any) -> float | None:
    match = re.search(r"-?\d+(?:\.\d+)?", str(value or ""))
    return float(match.group(0)) if match else None

from __future__ import annotations

from backend.quote.form_ops import build_row_key, merge_extra_requirements
from backend.quote.models import FormRow


BASE_DOCUMENT_TARGET_FIELDS: tuple[str, ...] = (
    "pricing_mode",
    "pricing_quantity",
    "sample_count",
    "sample_length_mm",
    "sample_width_mm",
    "sample_height_mm",
    "sample_weight_kg",
)


def build_document_target_fields(rows: list[FormRow]) -> dict[str, list[str]]:
    """Return fields worth re-reading from the original document.

    `planned_standard_fields` comes from equipment capabilities after test type
    matching. The base fields are not equipment-specific, but they are frequent
    sources of pricing errors and benefit from a focused second pass.
    """
    targets: dict[str, list[str]] = {}
    for row in rows:
        fields = _dedupe([*BASE_DOCUMENT_TARGET_FIELDS, *row.planned_standard_fields])
        manual_fields = set(row.manual_overrides)
        fields = [field for field in fields if field not in manual_fields]
        if fields:
            targets[row.row_id] = fields
    return targets


def merge_document_enrichment(
    current: list[FormRow],
    incoming: list[FormRow],
    *,
    target_fields_by_row: dict[str, list[str]],
) -> list[FormRow]:
    """Merge a targeted document pass into existing rows.

    Unlike the generic form merge, targeted enrichment may revise fields that
    were already filled by the first broad extraction pass. The caller controls
    the exact allow-list per row via `target_fields_by_row`.
    """
    incoming_by_id = {row.row_id: row for row in incoming if row.row_id}
    incoming_by_key = {build_row_key(row): row for row in incoming}
    updated: list[FormRow] = []
    for row in current:
        candidate = incoming_by_id.get(row.row_id) or incoming_by_key.get(build_row_key(row))
        if candidate is None:
            updated.append(row.model_copy(deep=True))
            continue

        data = row.model_dump()
        for field in target_fields_by_row.get(row.row_id, []):
            value = getattr(candidate, field, None)
            if _has_value(value):
                data[field] = value
        data["extra_standard_requirements"] = [
            item.model_dump()
            for item in merge_extra_requirements(row.extra_standard_requirements, candidate.extra_standard_requirements)
        ]
        for field in ("source_text", "conditions_text", "sample_info_text"):
            data[field] = _merge_text(data.get(field), getattr(candidate, field, ""))
        updated.append(FormRow.model_validate(data))
    return updated


def document_enrichment_notes(
    before: list[FormRow],
    after: list[FormRow],
    *,
    target_fields_by_row: dict[str, list[str]],
) -> list[str]:
    before_by_id = {row.row_id: row for row in before}
    notes: list[str] = []
    for row in after:
        before_row = before_by_id.get(row.row_id)
        if before_row is None:
            continue
        changed = [
            field
            for field in target_fields_by_row.get(row.row_id, [])
            if getattr(before_row, field, None) != getattr(row, field, None)
        ]
        label = row.canonical_test_type or row.raw_test_type or row.row_id
        if changed:
            notes.append(f"{label}: 文档定向补充更新字段 {', '.join(changed)}")
        else:
            notes.append(f"{label}: 文档定向补充未更新目标字段")
    return notes


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = str(value or "").strip()
        if key and key not in seen:
            seen.add(key)
            result.append(key)
    return result


def _has_value(value: object) -> bool:
    return value not in (None, "", [])


def _merge_text(current: object, incoming: object) -> str:
    cur = str(current or "").strip()
    nxt = str(incoming or "").strip()
    if not nxt:
        return cur
    if not cur or nxt == cur:
        return nxt
    return f"{cur}\n{nxt}"


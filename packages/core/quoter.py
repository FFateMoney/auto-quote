from __future__ import annotations

import re
from dataclasses import dataclass

from packages.integrations.catalog import CatalogGateway, EquipmentPricingRecord, EquipmentRecord, normalize_pricing_mode

from .models import EquipmentProfile, EquipmentRejection, FormRow


def _effective_volume_m3(equipment: EquipmentRecord) -> float | None:
    if equipment.volume_m3 is not None:
        return equipment.volume_m3
    if None in (equipment.length_mm, equipment.width_mm, equipment.height_mm):
        return None
    return float(equipment.length_mm * equipment.width_mm * equipment.height_mm) / 1_000_000_000


def _extract_number(text: str) -> float | None:
    match = re.search(r"(-?\d+(?:\.\d+)?)", text or "")
    if not match:
        return None
    return float(match.group(1))


DIRECT_EQUIPMENT_CONSTRAINTS: tuple[tuple[str, str, str], ...] = (
    ("sample_weight_kg", "max_load_kg", "max"),
    ("required_temp_min", "temp_min", "min"),
    ("required_temp_max", "temp_max", "max"),
    ("required_humidity_min", "humidity_min", "min"),
    ("required_humidity_max", "humidity_max", "max"),
)

CAPABILITY_CONSTRAINTS: tuple[tuple[str, str, str], ...] = (
    ("required_freq_min", "freq_min", "min"),
    ("required_freq_max", "freq_max", "max"),
    ("required_accel_min", "accel_min", "min"),
    ("required_accel_max", "accel_max", "max"),
    ("required_displacement_min", "displacement_min", "min"),
    ("required_displacement_max", "displacement_max", "max"),
    ("required_irradiance_min", "irradiance_min", "min"),
    ("required_irradiance_max", "irradiance_max", "max"),
    ("required_water_temp_min", "water_temp_min", "min"),
    ("required_water_temp_max", "water_temp_max", "max"),
    ("required_water_flow_min", "water_flow_min", "min"),
    ("required_water_flow_max", "water_flow_max", "max"),
)

FIELD_LABELS: dict[str, str] = {
    "repeat_count": "重复次数",
    "sample_length_mm": "长度",
    "sample_width_mm": "宽度",
    "sample_height_mm": "高度",
    "sample_weight_kg": "样品重量",
    "required_temp_min": "最低温度",
    "required_temp_max": "最高温度",
    "required_humidity_min": "最低湿度",
    "required_humidity_max": "最高湿度",
    "required_temp_change_rate": "温变速率",
    "required_freq_min": "最低频率",
    "required_freq_max": "最高频率",
    "required_accel_min": "最低加速度",
    "required_accel_max": "最高加速度",
    "required_displacement_min": "最小位移",
    "required_displacement_max": "最大位移",
    "required_irradiance_min": "最低辐照",
    "required_irradiance_max": "最高辐照",
    "required_water_temp_min": "最低水温",
    "required_water_temp_max": "最高水温",
    "required_water_flow_min": "最小流量",
    "required_water_flow_max": "最大流量",
    "max_load_kg": "载荷上限",
    "temp_min": "设备最低温度",
    "temp_max": "设备最高温度",
    "humidity_min": "设备最低湿度",
    "humidity_max": "设备最高湿度",
    "temp_change_rate_min": "设备最小温变速率",
    "temp_change_rate_max": "设备最大温变速率",
    "freq_min": "设备最低频率",
    "freq_max": "设备最高频率",
    "accel_min": "设备最低加速度",
    "accel_max": "设备最高加速度",
    "displacement_min": "设备最小位移",
    "displacement_max": "设备最大位移",
    "irradiance_min": "设备最低辐照",
    "irradiance_max": "设备最高辐照",
    "water_temp_min": "设备最低水温",
    "water_temp_max": "设备最高水温",
    "water_flow_min": "设备最小流量",
    "water_flow_max": "设备最大流量",
}

STANDARD_FILLABLE_FIELDS: tuple[str, ...] = (
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
)


@dataclass(slots=True)
class Quoter:
    catalog: CatalogGateway

    def select_equipment(self, rows: list[FormRow]) -> tuple[list[FormRow], list[str]]:
        updated: list[FormRow] = []
        notes: list[str] = []
        for row in rows:
            row_copy = row.model_copy(deep=True)
            candidates = self._collect_candidate_equipment(row_copy)
            compatible, rejected = self._filter_compatible_equipment(row_copy, candidates)
            compatible.sort(key=lambda item: (item.power_kwh is None, item.power_kwh or 0, item.id))
            row_copy.candidate_equipment_ids = [item.id for item in compatible]
            row_copy.candidate_equipment_profiles = [self._build_equipment_profile(item) for item in compatible]
            row_copy.selected_equipment_id = compatible[0].id if compatible else ""
            row_copy.rejected_equipment = rejected
            row_copy.missing_fields = self._infer_missing_fields_from_rejections(rejected)
            notes.append(
                f"{row_copy.canonical_test_type or row_copy.raw_test_type}: 候选设备 {', '.join(row_copy.candidate_equipment_ids) or '无'}"
            )
            if rejected:
                notes.append(
                    f"{row_copy.canonical_test_type or row_copy.raw_test_type}: 剔除设备 "
                    + "；".join(f"{item.equipment_label or item.equipment_id}({'; '.join(item.reasons)})" for item in rejected)
                )
            updated.append(row_copy)
        return updated, notes

    def price(self, rows: list[FormRow]) -> tuple[list[FormRow], list[str], str]:
        updated: list[FormRow] = []
        notes: list[str] = []
        overall_status = "completed"

        for row in rows:
            row_copy = row.model_copy(deep=True)
            row_copy.stage_status = "quoted"
            supplemental_missing_fields = self._infer_missing_fields_from_rejections(row_copy.rejected_equipment)

            if not row_copy.selected_equipment_id:
                row_copy.stage_status = "waiting_manual_input"
                row_copy.missing_fields = supplemental_missing_fields
                row_copy.blocking_reason = (
                    "所有候选设备均被筛除" if row_copy.rejected_equipment else "未找到满足条件的设备"
                )
                if not row_copy.canonical_test_type:
                    row_copy.missing_fields = self._merge_missing_fields(row_copy.missing_fields, ["canonical_test_type"])
                    row_copy.blocking_reason = "未匹配到试验类型，无法筛选设备"
                overall_status = "waiting_manual_input"
                notes.append(f"{row_copy.canonical_test_type or row_copy.raw_test_type}: {row_copy.blocking_reason}")
                if row_copy.missing_fields:
                    row_copy.blocking_reason += "；待补字段：" + "、".join(self._format_missing_field_labels(row_copy.missing_fields))
                updated.append(row_copy)
                continue

            if row_copy.pricing_quantity is None:
                row_copy.stage_status = "waiting_manual_input"
                row_copy.missing_fields = self._merge_missing_fields(supplemental_missing_fields, ["pricing_quantity"])
                row_copy.blocking_reason = "缺少计价数量，无法计算报价"
                overall_status = "waiting_manual_input"
                notes.append(f"{row_copy.canonical_test_type or row_copy.raw_test_type}: {row_copy.blocking_reason}")
                updated.append(row_copy)
                continue

            pricing_rows = self.catalog.get_pricing_rows(row_copy.canonical_test_type)
            selected_row, reason = self._select_pricing_row(row_copy.selected_equipment_id, pricing_rows)
            if not selected_row:
                row_copy.stage_status = "waiting_manual_input"
                row_copy.blocking_reason = reason or "未找到价格规则"
                row_copy.missing_fields = []
                overall_status = "waiting_manual_input"
                notes.append(f"{row_copy.canonical_test_type}: {row_copy.blocking_reason}")
                updated.append(row_copy)
                continue

            test_type_record = self.catalog.get_test_type(row_copy.canonical_test_type)
            base_fee = float(test_type_record.base_fee if test_type_record else row_copy.base_fee or 0)
            unit_price = float(selected_row.price)
            quantity = float(row_copy.pricing_quantity or 0)
            repeat_count = float(row_copy.repeat_count or 1)
            row_copy.base_fee = base_fee
            row_copy.pricing_mode = normalize_pricing_mode(test_type_record.pricing_mode if test_type_record else row_copy.pricing_mode)
            row_copy.unit_price = unit_price
            row_copy.price_unit = selected_row.price_unit
            row_copy.total_price = round((base_fee + quantity * unit_price) * repeat_count, 2)
            row_copy.formula = f"({base_fee:g} + {quantity:g} * {unit_price:g}) * {repeat_count:g}"
            row_copy.missing_fields = supplemental_missing_fields
            if supplemental_missing_fields:
                row_copy.blocking_reason = "部分设备因字段缺失被筛除，可补充后重新尝试报价"
                notes.append(
                    f"{row_copy.canonical_test_type}: 自动报价成功；仍可补充字段 "
                    + "、".join(self._format_missing_field_labels(supplemental_missing_fields))
                    + " 后重试设备筛选"
                )
            else:
                row_copy.blocking_reason = ""
                notes.append(f"{row_copy.canonical_test_type}: 自动报价成功")
            updated.append(row_copy)
        return updated, notes, overall_status

    def needs_standard_enrichment(self, rows: list[FormRow]) -> bool:
        return any(self.standard_fillable_missing_fields(row) for row in rows if row.standard_codes)

    def standard_fillable_missing_fields(self, row: FormRow) -> list[str]:
        return [field for field in row.missing_fields if field in STANDARD_FILLABLE_FIELDS]

    def _collect_candidate_equipment(self, row: FormRow) -> list[EquipmentRecord]:
        return self.catalog.get_equipment_for_test_type(row.canonical_test_type)

    def _filter_compatible_equipment(
        self,
        row: FormRow,
        candidates: list[EquipmentRecord],
    ) -> tuple[list[EquipmentRecord], list[EquipmentRejection]]:
        compatible: list[EquipmentRecord] = []
        rejected: list[EquipmentRejection] = []
        for equipment in candidates:
            reasons, missing_fields = self._compatibility_rejection_details(row, equipment)
            if reasons:
                rejected.append(
                    EquipmentRejection(
                        equipment_id=equipment.id,
                        equipment_label=equipment.id,
                        reasons=reasons,
                        missing_fields=missing_fields,
                    )
                )
                continue
            compatible.append(equipment)
        return compatible, rejected

    def _build_equipment_profile(self, equipment: EquipmentRecord) -> EquipmentProfile:
        attributes: dict[str, object] = {}
        scalar_fields = (
            "volume_m3",
            "length_mm",
            "width_mm",
            "height_mm",
            "power_kwh",
            "max_load_kg",
            "temp_min",
            "temp_max",
            "humidity_min",
            "humidity_max",
            "temp_change_rate_min",
            "temp_change_rate_max",
            "constraints_info",
            "status",
        )
        for field_name in scalar_fields:
            value = getattr(equipment, field_name)
            if value in (None, "", []):
                continue
            attributes[field_name] = value
        for key, value in sorted((equipment.capabilities or {}).items()):
            if value in (None, "", []):
                continue
            attributes[key] = value
        return EquipmentProfile(
            equipment_id=equipment.id,
            equipment_label=equipment.id,
            attributes=attributes,
        )

    def _compatibility_rejection_details(self, row: FormRow, equipment: EquipmentRecord) -> tuple[list[str], list[str]]:
        reasons: list[str] = []
        missing_fields: list[str] = []
        if equipment.status != "active":
            return ["设备未启用"], []
        dimension_pairs = (
            ("sample_length_mm", row.sample_length_mm, equipment.length_mm),
            ("sample_width_mm", row.sample_width_mm, equipment.width_mm),
            ("sample_height_mm", row.sample_height_mm, equipment.height_mm),
        )
        for field_name, sample_value, equipment_limit in dimension_pairs:
            if equipment_limit in (None, ""):
                continue
            if sample_value is None:
                reasons.append(f"{FIELD_LABELS[field_name]}/缺失")
                missing_fields.append(field_name)
                continue
            if float(sample_value) > float(equipment_limit):
                reasons.append(f"{FIELD_LABELS[field_name]}/>{float(equipment_limit):g}")

        for row_field, equipment_field, direction in DIRECT_EQUIPMENT_CONSTRAINTS:
            reason, missing_field = self._compare_constraint(
                required_value=getattr(row, row_field),
                limit_value=getattr(equipment, equipment_field),
                direction=direction,
                required_label=FIELD_LABELS.get(row_field, row_field),
                limit_label=FIELD_LABELS.get(equipment_field, equipment_field),
                missing_field=row_field,
            )
            if reason:
                reasons.append(reason)
            if missing_field:
                missing_fields.append(missing_field)

        temp_change_rate_min = equipment.temp_change_rate_min
        temp_change_rate_max = equipment.temp_change_rate_max
        has_temp_change_rate_constraint = (
            temp_change_rate_max not in (None, "")
            or (temp_change_rate_min not in (None, "") and float(temp_change_rate_min) != 0)
        )
        if has_temp_change_rate_constraint:
            if row.required_temp_change_rate is None:
                reasons.append(f"{FIELD_LABELS['required_temp_change_rate']}/缺失")
                missing_fields.append("required_temp_change_rate")
            else:
                for equipment_field, direction in (("temp_change_rate_min", "min"), ("temp_change_rate_max", "max")):
                    reason, missing_field = self._compare_constraint(
                        required_value=row.required_temp_change_rate,
                        limit_value=getattr(equipment, equipment_field),
                        direction=direction,
                        required_label=FIELD_LABELS.get("required_temp_change_rate", "required_temp_change_rate"),
                        limit_label=FIELD_LABELS.get(equipment_field, equipment_field),
                        missing_field="required_temp_change_rate",
                    )
                    if reason:
                        reasons.append(reason)
                    if missing_field:
                        missing_fields.append(missing_field)

        capabilities = equipment.capabilities or {}
        for row_field, capability_key, direction in CAPABILITY_CONSTRAINTS:
            reason, missing_field = self._compare_constraint(
                required_value=getattr(row, row_field),
                limit_value=capabilities.get(capability_key),
                direction=direction,
                required_label=FIELD_LABELS.get(row_field, row_field),
                limit_label=FIELD_LABELS.get(capability_key, capability_key),
                missing_field=row_field,
            )
            if reason:
                reasons.append(reason)
            if missing_field:
                missing_fields.append(missing_field)

        return reasons, self._merge_missing_fields([], missing_fields)

    def _compare_constraint(
        self,
        *,
        required_value: float | int | None,
        limit_value: float | int | str | None,
        direction: str,
        required_label: str,
        limit_label: str,
        missing_field: str,
    ) -> tuple[str, str]:
        if limit_value in (None, ""):
            return "", ""
        if required_value is None:
            return f"{required_label}/缺失", missing_field
        limit_float = float(limit_value)
        required_float = float(required_value)
        if direction == "min" and required_float < limit_float:
            return f"{required_label}/<{limit_float:g}", ""
        if direction == "max" and required_float > limit_float:
            return f"{required_label}/>{limit_float:g}", ""
        return "", ""

    def _infer_missing_fields_from_rejections(self, rejected: list[EquipmentRejection]) -> list[str]:
        merged: list[str] = []
        for item in rejected:
            merged = self._merge_missing_fields(merged, item.missing_fields)
        return merged

    def _merge_missing_fields(self, current: list[str], incoming: list[str]) -> list[str]:
        merged = list(current)
        seen = {item for item in merged if item}
        for item in incoming:
            if not item or item in seen:
                continue
            seen.add(item)
            merged.append(item)
        return merged

    def _format_missing_field_labels(self, fields: list[str]) -> list[str]:
        return [FIELD_LABELS.get(field, field) for field in fields]

    def _select_pricing_row(
        self,
        selected_equipment_id: str,
        pricing_rows: list[EquipmentPricingRecord],
    ) -> tuple[EquipmentPricingRecord | None, str]:
        specific_rows = [row for row in pricing_rows if row.equipment_ids and selected_equipment_id in row.equipment_ids]
        if len(specific_rows) == 1:
            return specific_rows[0], ""
        if len(specific_rows) > 1:
            return None, "设备专属价格规则不唯一"

        generic_rows = [row for row in pricing_rows if not row.equipment_ids]
        if not generic_rows:
            return None, "未找到价格规则"
        if len(generic_rows) == 1 and not generic_rows[0].volume_tier:
            return generic_rows[0], ""

        equipment = self.catalog.equipment_by_id.get(selected_equipment_id)
        if not equipment:
            return None, "未找到设备信息"
        volume = _effective_volume_m3(equipment)
        if volume is None:
            return None, "设备体积未知，无法命中价格分档"
        scored_rows: list[tuple[float, EquipmentPricingRecord]] = []
        for row in generic_rows:
            threshold = _extract_number(row.volume_tier)
            if threshold is None:
                return None, "体积分档规则无法解析"
            scored_rows.append((threshold, row))
        scored_rows.sort(key=lambda item: item[0])
        for threshold, row in scored_rows:
            if volume <= threshold:
                return row, ""
        return scored_rows[-1][1], ""

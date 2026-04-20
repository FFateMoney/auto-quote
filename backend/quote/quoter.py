from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from backend.quote.models import EquipmentProfile, EquipmentRejection, FormRow

if TYPE_CHECKING:
    from backend.quote.catalog import CatalogGateway, EquipmentPricingRecord, EquipmentRecord


def _effective_volume_m3(equipment: "EquipmentRecord") -> float | None:
    if equipment.volume_m3 is not None:
        return equipment.volume_m3
    if None in (equipment.length_mm, equipment.width_mm, equipment.height_mm):
        return None
    return float(equipment.length_mm * equipment.width_mm * equipment.height_mm) / 1_000_000_000


def _extract_number(text: str) -> float | None:
    match = re.search(r"(-?\d+(?:\.\d+)?)", text or "")
    return float(match.group(1)) if match else None


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
    "sample_length_mm": "长度", "sample_width_mm": "宽度", "sample_height_mm": "高度",
    "sample_weight_kg": "样品重量",
    "required_temp_min": "最低温度", "required_temp_max": "最高温度",
    "required_humidity_min": "最低湿度", "required_humidity_max": "最高湿度",
    "required_temp_change_rate": "温变速率",
    "required_freq_min": "最低频率", "required_freq_max": "最高频率",
    "required_accel_min": "最低加速度", "required_accel_max": "最高加速度",
    "required_displacement_min": "最小位移", "required_displacement_max": "最大位移",
    "required_irradiance_min": "最低辐照", "required_irradiance_max": "最高辐照",
    "required_water_temp_min": "最低水温", "required_water_temp_max": "最高水温",
    "required_water_flow_min": "最小流量", "required_water_flow_max": "最大流量",
    "max_load_kg": "载荷上限",
    "temp_min": "设备最低温度", "temp_max": "设备最高温度",
    "humidity_min": "设备最低湿度", "humidity_max": "设备最高湿度",
    "temp_change_rate_min": "设备最小温变速率", "temp_change_rate_max": "设备最大温变速率",
    "freq_min": "设备最低频率", "freq_max": "设备最高频率",
    "accel_min": "设备最低加速度", "accel_max": "设备最高加速度",
    "displacement_min": "设备最小位移", "displacement_max": "设备最大位移",
    "irradiance_min": "设备最低辐照", "irradiance_max": "设备最高辐照",
    "water_temp_min": "设备最低水温", "water_temp_max": "设备最高水温",
    "water_flow_min": "设备最小流量", "water_flow_max": "设备最大流量",
}

STANDARD_FILLABLE_FIELDS: tuple[str, ...] = (
    "required_temp_min", "required_temp_max",
    "required_humidity_min", "required_humidity_max",
    "required_temp_change_rate",
    "required_freq_min", "required_freq_max",
    "required_accel_min", "required_accel_max",
    "required_displacement_min", "required_displacement_max",
    "required_irradiance_min", "required_irradiance_max",
    "required_water_temp_min", "required_water_temp_max",
    "required_water_flow_min", "required_water_flow_max",
)


@dataclass(slots=True)
class Quoter:
    catalog: "CatalogGateway"

    def select_equipment(self, rows: list[FormRow]) -> tuple[list[FormRow], list[str]]:
        updated, notes = [], []
        for row in rows:
            r = row.model_copy(deep=True)
            candidates = self.catalog.get_equipment_for_test_type(r.canonical_test_type)
            compatible, rejected = self._filter_compatible(r, candidates)
            compatible.sort(key=lambda e: (e.power_kwh is None, e.power_kwh or 0, e.id))
            r.candidate_equipment_ids = [e.id for e in compatible]
            r.candidate_equipment_profiles = [self._profile(e) for e in compatible]
            r.selected_equipment_id = compatible[0].id if compatible else ""
            r.rejected_equipment = rejected
            r.missing_fields = self._missing_from_rejections(rejected)
            notes.append(f"{r.canonical_test_type or r.raw_test_type}: 候选设备 {', '.join(r.candidate_equipment_ids) or '无'}")
            if rejected:
                notes.append(
                    f"{r.canonical_test_type or r.raw_test_type}: 剔除设备 "
                    + "；".join(f"{e.equipment_label or e.equipment_id}({'; '.join(e.reasons)})" for e in rejected)
                )
            updated.append(r)
        return updated, notes

    def price(self, rows: list[FormRow]) -> tuple[list[FormRow], list[str], str]:
        updated, notes = [], []
        overall = "completed"
        for row in rows:
            r = row.model_copy(deep=True)
            r.stage_status = "quoted"
            supplemental = self._missing_from_rejections(r.rejected_equipment)

            if not r.selected_equipment_id:
                r.stage_status = "waiting_manual_input"
                r.missing_fields = supplemental
                r.blocking_reason = "所有候选设备均被筛除" if r.rejected_equipment else "未找到满足条件的设备"
                if not r.canonical_test_type:
                    r.missing_fields = _merge_fields(r.missing_fields, ["canonical_test_type"])
                    r.blocking_reason = "未匹配到试验类型，无法筛选设备"
                overall = "waiting_manual_input"
                notes.append(f"{r.canonical_test_type or r.raw_test_type}: {r.blocking_reason}")
                if r.missing_fields:
                    r.blocking_reason += "；待补字段：" + "、".join(FIELD_LABELS.get(f, f) for f in r.missing_fields)
                updated.append(r)
                continue

            if r.pricing_quantity is None:
                r.stage_status = "waiting_manual_input"
                r.missing_fields = _merge_fields(supplemental, ["pricing_quantity"])
                r.blocking_reason = "缺少计价数量，无法计算报价"
                overall = "waiting_manual_input"
                notes.append(f"{r.canonical_test_type or r.raw_test_type}: {r.blocking_reason}")
                updated.append(r)
                continue

            pricing_rows = self.catalog.get_pricing_rows(r.canonical_test_type)
            selected_row, reason = self._select_pricing_row(r.selected_equipment_id, pricing_rows)
            if not selected_row:
                r.stage_status = "waiting_manual_input"
                r.blocking_reason = reason or "未找到价格规则"
                overall = "waiting_manual_input"
                notes.append(f"{r.canonical_test_type}: {r.blocking_reason}")
                updated.append(r)
                continue

            test_type = self.catalog.get_test_type(r.canonical_test_type)
            base_fee = float(test_type.base_fee if test_type else r.base_fee or 0)
            unit_price = float(selected_row.price)
            quantity = float(r.pricing_quantity or 0)
            repeat = float(r.repeat_count or 1)
            r.base_fee = base_fee
            r.pricing_mode = _normalize_pricing_mode(test_type.pricing_mode if test_type else r.pricing_mode)
            r.unit_price = unit_price
            r.price_unit = selected_row.price_unit
            r.total_price = round((base_fee + quantity * unit_price) * repeat, 2)
            r.formula = f"({base_fee:g} + {quantity:g} * {unit_price:g}) * {repeat:g}"
            r.missing_fields = supplemental
            if supplemental:
                r.blocking_reason = "部分设备因字段缺失被筛除，可补充后重新尝试报价"
                notes.append(f"{r.canonical_test_type}: 自动报价成功；仍可补充字段 {'、'.join(FIELD_LABELS.get(f, f) for f in supplemental)} 后重试")
            else:
                r.blocking_reason = ""
                notes.append(f"{r.canonical_test_type}: 自动报价成功")
            updated.append(r)
        return updated, notes, overall

    def standard_fillable_missing_fields(self, row: FormRow) -> list[str]:
        return [f for f in row.missing_fields if f in STANDARD_FILLABLE_FIELDS]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _filter_compatible(
        self, row: FormRow, candidates: list["EquipmentRecord"]
    ) -> tuple[list["EquipmentRecord"], list[EquipmentRejection]]:
        compatible, rejected = [], []
        for eq in candidates:
            reasons, missing = self._rejection_details(row, eq)
            if reasons:
                rejected.append(EquipmentRejection(equipment_id=eq.id, equipment_label=eq.id, reasons=reasons, missing_fields=missing))
            else:
                compatible.append(eq)
        return compatible, rejected

    def _profile(self, eq: "EquipmentRecord") -> EquipmentProfile:
        attrs: dict[str, object] = {}
        for f in ("volume_m3", "length_mm", "width_mm", "height_mm", "power_kwh", "max_load_kg",
                   "temp_min", "temp_max", "humidity_min", "humidity_max",
                   "temp_change_rate_min", "temp_change_rate_max", "constraints_info", "status"):
            v = getattr(eq, f)
            if v not in (None, "", []):
                attrs[f] = v
        for k, v in sorted((eq.capabilities or {}).items()):
            if v not in (None, "", []):
                attrs[k] = v
        return EquipmentProfile(equipment_id=eq.id, equipment_label=eq.id, attributes=attrs)

    def _rejection_details(self, row: FormRow, eq: "EquipmentRecord") -> tuple[list[str], list[str]]:
        reasons, missing = [], []
        if eq.status != "active":
            return ["设备未启用"], []
        for fname, sample_val, eq_limit in (
            ("sample_length_mm", row.sample_length_mm, eq.length_mm),
            ("sample_width_mm", row.sample_width_mm, eq.width_mm),
            ("sample_height_mm", row.sample_height_mm, eq.height_mm),
        ):
            if sample_val is None:
                continue
            if eq_limit in (None, ""):
                reasons.append(f"{FIELD_LABELS[fname]}/缺失")
                missing.append(fname)
            elif float(sample_val) > float(eq_limit):
                reasons.append(f"{FIELD_LABELS[fname]}/>{float(eq_limit):g}")

        for row_f, eq_f, direction in DIRECT_EQUIPMENT_CONSTRAINTS:
            r, m = self._compare(getattr(row, row_f), getattr(eq, eq_f), direction,
                                 FIELD_LABELS.get(row_f, row_f), FIELD_LABELS.get(eq_f, eq_f), row_f)
            if r: reasons.append(r)
            if m: missing.append(m)

        if row.required_temp_change_rate is not None:
            tcr_min, tcr_max = eq.temp_change_rate_min, eq.temp_change_rate_max
            if tcr_max in (None, "") and tcr_min in (None, ""):
                reasons.append(f"{FIELD_LABELS['required_temp_change_rate']}/缺失")
                missing.append("required_temp_change_rate")
            else:
                for eq_f, direction in (("temp_change_rate_min", "min"), ("temp_change_rate_max", "max")):
                    r, m = self._compare(row.required_temp_change_rate, getattr(eq, eq_f), direction,
                                         FIELD_LABELS["required_temp_change_rate"], FIELD_LABELS.get(eq_f, eq_f),
                                         "required_temp_change_rate")
                    if r: reasons.append(r)
                    if m: missing.append(m)

        caps = eq.capabilities or {}
        for row_f, cap_key, direction in CAPABILITY_CONSTRAINTS:
            r, m = self._compare(getattr(row, row_f), caps.get(cap_key), direction,
                                 FIELD_LABELS.get(row_f, row_f), FIELD_LABELS.get(cap_key, cap_key), row_f)
            if r: reasons.append(r)
            if m: missing.append(m)

        return reasons, _merge_fields([], missing)

    def _compare(self, req: float | None, limit: object, direction: str,
                 req_label: str, lim_label: str, missing_field: str) -> tuple[str, str]:
        if req is None:
            return "", ""
        if limit in (None, ""):
            return f"{req_label}/缺失", missing_field
        lf = float(limit)
        rf = float(req)
        if direction == "min" and rf < lf:
            return f"{req_label}/<{lf:g}", ""
        if direction == "max" and rf > lf:
            return f"{req_label}/>{lf:g}", ""
        return "", ""

    def _missing_from_rejections(self, rejected: list[EquipmentRejection]) -> list[str]:
        result: list[str] = []
        for item in rejected:
            result = _merge_fields(result, item.missing_fields)
        return result

    def _select_pricing_row(
        self, equipment_id: str, pricing_rows: list["EquipmentPricingRecord"]
    ) -> tuple["EquipmentPricingRecord | None", str]:
        specific = [r for r in pricing_rows if r.equipment_ids and equipment_id in r.equipment_ids]
        if len(specific) == 1:
            return specific[0], ""
        if len(specific) > 1:
            return None, "设备专属价格规则不唯一"
        generic = [r for r in pricing_rows if not r.equipment_ids]
        if not generic:
            return None, "未找到价格规则"
        if len(generic) == 1 and not generic[0].volume_tier:
            return generic[0], ""
        equipment = self.catalog.equipment_by_id.get(equipment_id)
        if not equipment:
            return None, "未找到设备信息"
        volume = _effective_volume_m3(equipment)
        if volume is None:
            return None, "设备体积未知，无法命中价格分档"
        scored = sorted((_extract_number(r.volume_tier), r) for r in generic)
        if any(threshold is None for threshold, _ in scored):
            return None, "体积分档规则无法解析"
        for threshold, r in scored:
            if volume <= threshold:
                return r, ""
        return scored[-1][1], ""


def _merge_fields(current: list[str], incoming: list[str]) -> list[str]:
    seen = {f for f in current if f}
    result = list(current)
    for f in incoming:
        if f and f not in seen:
            seen.add(f)
            result.append(f)
    return result


def _normalize_pricing_mode(value: object) -> str:
    mapping = {"hourly": "小时", "batch": "批次", "per_count": "次数",
               "小时": "小时", "批次": "批次", "次数": "次数"}
    return mapping.get(str(value or "").strip(), str(value or "").strip())

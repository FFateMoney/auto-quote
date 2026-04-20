from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg.rows import dict_row

from backend.quote.settings import get_settings


def normalize_pricing_mode(value: Any) -> str:
    mapping = {"hourly": "小时", "batch": "批次", "per_count": "次数",
               "小时": "小时", "批次": "批次", "次数": "次数"}
    return mapping.get(str(value or "").strip(), str(value or "").strip())


@dataclass(frozen=True)
class TestTypeRecord:
    id: int
    name: str
    aliases: tuple[str, ...]
    base_fee: float
    pricing_mode: str
    notes: str


@dataclass(frozen=True)
class EquipmentRecord:
    id: str
    volume_m3: float | None
    length_mm: int | None
    width_mm: int | None
    height_mm: int | None
    power_kwh: float | None
    max_load_kg: float | None
    temp_min: float | None
    temp_max: float | None
    humidity_min: float | None
    humidity_max: float | None
    temp_change_rate_min: float | None
    temp_change_rate_max: float | None
    capabilities: dict[str, Any]
    constraints_info: str
    status: str


@dataclass(frozen=True)
class EquipmentPricingRecord:
    id: int
    test_type_id: int
    equipment_ids: tuple[str, ...]
    volume_tier: str
    price: float
    price_unit: str


def _to_float(v: Any) -> float | None:
    return None if v in (None, "") else float(v)


def _to_int(v: Any) -> int | None:
    return None if v in (None, "") else int(v)


class CatalogGateway:
    def __init__(self) -> None:
        self.test_types: list[TestTypeRecord] = []
        self.test_types_by_id: dict[int, TestTypeRecord] = {}
        self.test_types_by_name: dict[str, TestTypeRecord] = {}
        self.equipment_by_id: dict[str, EquipmentRecord] = {}
        self.pricing_by_test_type_id: dict[int, list[EquipmentPricingRecord]] = defaultdict(list)
        self.equipment_ids_by_test_type_id: dict[int, set[str]] = defaultdict(set)
        self.load_error = ""
        self._load()

    def get_test_type(self, name: str) -> TestTypeRecord | None:
        return self.test_types_by_name.get(name)

    def find_test_type_by_alias(self, raw_name: str) -> TestTypeRecord | None:
        text = str(raw_name or "").strip().lower()
        if not text:
            return None
        for name, record in self.test_types_by_name.items():
            if name.lower() == text:
                return record
        for record in self.test_types:
            for alias in [record.name, *record.aliases]:
                a = alias.strip().lower()
                if a and (a == text or a in text or text in a):
                    return record
        return None

    def get_equipment_for_test_type(self, test_type_name: str) -> list[EquipmentRecord]:
        record = self.get_test_type(test_type_name)
        if not record:
            return []
        ids = sorted(self.equipment_ids_by_test_type_id.get(record.id, ()))
        return [self.equipment_by_id[eid] for eid in ids if eid in self.equipment_by_id]

    def get_pricing_rows(self, test_type_name: str) -> list[EquipmentPricingRecord]:
        record = self.get_test_type(test_type_name)
        return list(self.pricing_by_test_type_id.get(record.id, ())) if record else []

    def _connect(self):
        kwargs = {k: v for k, v in get_settings().database.items() if v not in (None, "", [])}
        return psycopg.connect(row_factory=dict_row, **kwargs)

    def _load(self) -> None:
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "select id, name, aliases, base_fee, pricing_mode, coalesce(notes,'') as notes "
                        "from public.test_types order by id"
                    )
                    for row in cur.fetchall():
                        r = TestTypeRecord(
                            id=int(row["id"]), name=str(row["name"]),
                            aliases=tuple(str(x).strip() for x in (row["aliases"] or []) if str(x).strip()),
                            base_fee=float(row["base_fee"] or 0),
                            pricing_mode=normalize_pricing_mode(row["pricing_mode"]),
                            notes=str(row["notes"] or ""),
                        )
                        self.test_types.append(r)
                        self.test_types_by_id[r.id] = r
                        self.test_types_by_name[r.name] = r

                    cur.execute(
                        "select id, volume_m3, length_mm, width_mm, height_mm, power_kwh, max_load_kg, "
                        "temp_min, temp_max, humidity_min, humidity_max, temp_change_rate_min, temp_change_rate_max, "
                        "capabilities, coalesce(constraints_info,'') as constraints_info, status "
                        "from public.equipment order by id"
                    )
                    for row in cur.fetchall():
                        r = EquipmentRecord(
                            id=str(row["id"]), volume_m3=_to_float(row["volume_m3"]),
                            length_mm=_to_int(row["length_mm"]), width_mm=_to_int(row["width_mm"]),
                            height_mm=_to_int(row["height_mm"]), power_kwh=_to_float(row["power_kwh"]),
                            max_load_kg=_to_float(row["max_load_kg"]),
                            temp_min=_to_float(row["temp_min"]), temp_max=_to_float(row["temp_max"]),
                            humidity_min=_to_float(row["humidity_min"]), humidity_max=_to_float(row["humidity_max"]),
                            temp_change_rate_min=_to_float(row["temp_change_rate_min"]),
                            temp_change_rate_max=_to_float(row["temp_change_rate_max"]),
                            capabilities=dict(row["capabilities"] or {}),
                            constraints_info=str(row["constraints_info"] or ""),
                            status=str(row["status"] or "active"),
                        )
                        self.equipment_by_id[r.id] = r

                    cur.execute("select test_type_id, equipment_id from public.test_type_equipment")
                    for row in cur.fetchall():
                        self.equipment_ids_by_test_type_id[int(row["test_type_id"])].add(str(row["equipment_id"]))

                    cur.execute(
                        "select id, test_type_id, equipment_ids, coalesce(volume_tier,'') as volume_tier, price, price_unit "
                        "from public.equipment_pricing order by id"
                    )
                    for row in cur.fetchall():
                        r = EquipmentPricingRecord(
                            id=int(row["id"]), test_type_id=int(row["test_type_id"]),
                            equipment_ids=tuple(str(x).strip() for x in (row["equipment_ids"] or []) if str(x).strip()),
                            volume_tier=str(row["volume_tier"] or ""),
                            price=float(row["price"] or 0), price_unit=str(row["price_unit"] or ""),
                        )
                        self.pricing_by_test_type_id[r.test_type_id].append(r)
                        if r.equipment_ids:
                            self.equipment_ids_by_test_type_id[r.test_type_id].update(r.equipment_ids)
        except Exception as exc:
            self.load_error = str(exc)

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol, Sequence

import psycopg
from psycopg.rows import dict_row

from backendV2.core.settings import Settings


@dataclass(frozen=True, slots=True)
class QuotationProject:
    id: int
    base_fee: Decimal
    unit_price: Decimal
    applicable_device_codes: tuple[str, ...]
    standard_type: str = ""
    test_item: str = ""
    max_specification: str = ""
    pricing_mode: str = ""


@dataclass(frozen=True, slots=True)
class DeviceCandidate:
    device_code: str
    power_kwh: Decimal | None
    capabilities: dict[str, Any]

    def to_dict(self) -> dict[str, object]:
        return {
            "device_code": self.device_code,
            "power_kwh": float(self.power_kwh) if self.power_kwh is not None else None,
            "capabilities": {
                field_name: float(value) if isinstance(value, Decimal) else value
                for field_name, value in self.capabilities.items()
            },
        }


@dataclass(frozen=True, slots=True)
class SpecificationOption:
    test_project_id: int
    specification: str
    pricing_mode: str

    def to_dict(self) -> dict[str, object]:
        return {
            "test_project_id": self.test_project_id,
            "specification": self.specification,
            "pricing_mode": self.pricing_mode,
        }


class QuotationProjectReader(Protocol):
    def get_quotation_project(self, test_project_id: int) -> QuotationProject: ...

    def list_device_candidates(self, device_codes: Sequence[str]) -> list[DeviceCandidate]: ...

    def list_specification_options(self, test_project_id: int) -> list[SpecificationOption]: ...


class QuotationRepository:
    """Reads prices and device capabilities used after Agent submission."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def get_quotation_project(self, test_project_id: int) -> QuotationProject:
        connection_args = {key: value for key, value in self._settings.database.items() if value not in (None, "")}
        with psycopg.connect(row_factory=dict_row, **connection_args) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        id,
                        standard_type,
                        test_item,
                        max_specification,
                        pricing_mode,
                        base_fee,
                        unit_price,
                        applicable_device_codes
                    FROM public.test_projects
                    WHERE id = %s
                    """,
                    (test_project_id,),
                )
                row = cursor.fetchone()
                if row is None:
                    raise KeyError(test_project_id)
                return QuotationProject(
                    id=int(row["id"]),
                    base_fee=Decimal(row["base_fee"]),
                    unit_price=Decimal(row["unit_price"]),
                    applicable_device_codes=tuple(str(code) for code in row["applicable_device_codes"]),
                    standard_type=str(row["standard_type"]).strip(),
                    test_item=str(row["test_item"]).strip(),
                    max_specification=str(row["max_specification"]).strip(),
                    pricing_mode=str(row["pricing_mode"]).strip(),
                )

    def list_specification_options(self, test_project_id: int) -> list[SpecificationOption]:
        connection_args = {key: value for key, value in self._settings.database.items() if value not in (None, "")}
        with psycopg.connect(row_factory=dict_row, **connection_args) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT sibling.id, sibling.max_specification, sibling.pricing_mode
                    FROM public.test_projects AS selected
                    INNER JOIN public.test_projects AS sibling
                        ON sibling.standard_type = selected.standard_type
                        AND sibling.test_item = selected.test_item
                    WHERE selected.id = %s AND sibling.is_deleted = FALSE
                    ORDER BY sibling.id
                    """,
                    (test_project_id,),
                )
                return [
                    SpecificationOption(
                        test_project_id=int(row["id"]),
                        specification=str(row["max_specification"]).strip(),
                        pricing_mode=str(row["pricing_mode"]).strip(),
                    )
                    for row in cursor.fetchall()
                ]

    def list_device_candidates(self, device_codes: Sequence[str]) -> list[DeviceCandidate]:
        if not device_codes:
            return []
        connection_args = {key: value for key, value in self._settings.database.items() if value not in (None, "")}
        with psycopg.connect(row_factory=dict_row, **connection_args) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT device_code, power_kwh, to_jsonb(device_capabilities) AS capabilities
                    FROM public.device_capabilities
                    WHERE device_code = ANY(%s) AND is_deleted = FALSE
                    """,
                    (list(device_codes),),
                )
                return [
                    DeviceCandidate(
                        device_code=str(row["device_code"]),
                        power_kwh=Decimal(row["power_kwh"]) if row["power_kwh"] is not None else None,
                        capabilities=dict(row["capabilities"]),
                    )
                    for row in cursor.fetchall()
                ]

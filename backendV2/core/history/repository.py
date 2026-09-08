from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

import psycopg
from psycopg.types.json import Jsonb

from backendV2.core.history.cache import (
    HistoricalQuotationCache,
    HistoricalQuotationCacheBuilder,
    HistoricalQuotationReuseField,
)
from backendV2.core.settings import Settings


@dataclass(frozen=True, slots=True)
class HistoricalQuotation:
    quotation_run_id: str
    quote_id: str
    source_snapshot_id: str | None
    source_file_name: str
    raw_test_type: object | None
    test_project_id: int | None
    standard_type: object | None
    test_item: object | None
    standard_code: object | None
    standard_document_section: object | None
    pricing_mode: object | None
    specification: object | None
    pricing_quantity: object | None
    sample_count: object | None
    length_mm: object | None
    width_mm: object | None
    height_mm: object | None
    special_fields: dict[str, object]
    base_fee: object | None
    unit_price: object | None
    total_price: object | None
    selected_device_code: object | None
    quotation_snapshot: dict[str, object]

    def database_values(self) -> dict[str, object]:
        return {
            "quotation_run_id": self.quotation_run_id,
            "quote_id": self.quote_id,
            "source_snapshot_id": self.source_snapshot_id,
            "source_file_name": self.source_file_name,
            "raw_test_type": self.raw_test_type,
            "test_project_id": self.test_project_id,
            "standard_type": self.standard_type,
            "test_item": self.test_item,
            "standard_code": self.standard_code,
            "standard_document_section": self.standard_document_section,
            "pricing_mode": self.pricing_mode,
            "specification": self.specification,
            "pricing_quantity": self.pricing_quantity,
            "sample_count": self.sample_count,
            "length_mm": self.length_mm,
            "width_mm": self.width_mm,
            "height_mm": self.height_mm,
            "special_fields": Jsonb(self.special_fields),
            "base_fee": self.base_fee,
            "unit_price": self.unit_price,
            "total_price": self.total_price,
            "selected_device_code": self.selected_device_code,
            "quotation_snapshot": Jsonb(self.quotation_snapshot),
        }


class HistoricalQuotationWriter(Protocol):
    def save_historical_quotations(self, quotations: Sequence[HistoricalQuotation]) -> int: ...


class HistoricalQuotationCacheReader(Protocol):
    def read_standard_cache(self, standard_type: str, test_item: str, standard_code: str) -> HistoricalQuotationCache: ...


class HistoricalQuotationRepository:
    """Stores user-approved quotations and exposes their reusable standard conditions."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def save_historical_quotations(self, quotations: Sequence[HistoricalQuotation]) -> int:
        if not quotations:
            return 0
        connection_args = {key: value for key, value in self._settings.database.items() if value not in (None, "")}
        with psycopg.connect(**connection_args) as connection:
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO public.historical_quotations (
                        quotation_run_id, quote_id, source_snapshot_id, source_file_name,
                        raw_test_type, test_project_id, standard_type, test_item,
                        standard_code, standard_document_section, pricing_mode, specification,
                        pricing_quantity, sample_count, length_mm, width_mm, height_mm,
                        special_fields, base_fee, unit_price, total_price, selected_device_code,
                        quotation_snapshot
                    ) VALUES (
                        %(quotation_run_id)s, %(quote_id)s, %(source_snapshot_id)s, %(source_file_name)s,
                        %(raw_test_type)s, %(test_project_id)s, %(standard_type)s, %(test_item)s,
                        %(standard_code)s, %(standard_document_section)s, %(pricing_mode)s, %(specification)s,
                        %(pricing_quantity)s, %(sample_count)s, %(length_mm)s, %(width_mm)s, %(height_mm)s,
                        %(special_fields)s, %(base_fee)s, %(unit_price)s, %(total_price)s, %(selected_device_code)s,
                        %(quotation_snapshot)s
                    )
                    ON CONFLICT (quotation_run_id, quote_id) DO UPDATE SET
                        source_snapshot_id = EXCLUDED.source_snapshot_id,
                        source_file_name = EXCLUDED.source_file_name,
                        raw_test_type = EXCLUDED.raw_test_type,
                        test_project_id = EXCLUDED.test_project_id,
                        standard_type = EXCLUDED.standard_type,
                        test_item = EXCLUDED.test_item,
                        standard_code = EXCLUDED.standard_code,
                        standard_document_section = EXCLUDED.standard_document_section,
                        pricing_mode = EXCLUDED.pricing_mode,
                        specification = EXCLUDED.specification,
                        pricing_quantity = EXCLUDED.pricing_quantity,
                        sample_count = EXCLUDED.sample_count,
                        length_mm = EXCLUDED.length_mm,
                        width_mm = EXCLUDED.width_mm,
                        height_mm = EXCLUDED.height_mm,
                        special_fields = EXCLUDED.special_fields,
                        base_fee = EXCLUDED.base_fee,
                        unit_price = EXCLUDED.unit_price,
                        total_price = EXCLUDED.total_price,
                        selected_device_code = EXCLUDED.selected_device_code,
                        quotation_snapshot = EXCLUDED.quotation_snapshot,
                        saved_at = CURRENT_TIMESTAMP
                    """,
                    [quotation.database_values() for quotation in quotations],
                )
        return len(quotations)

    def read_standard_cache(self, standard_type: str, test_item: str, standard_code: str) -> HistoricalQuotationCache:
        normalized_standard_type = standard_type.strip()
        normalized_test_item = test_item.strip()
        normalized_standard_code = standard_code.strip()
        connection_args = {key: value for key, value in self._settings.database.items() if value not in (None, "")}
        with psycopg.connect(**connection_args) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT field_name, field_section, cache_scope, is_grouping_key
                    FROM public.historical_quotation_reuse_fields
                    ORDER BY id
                    """
                )
                reuse_fields = [HistoricalQuotationReuseField(*row) for row in cursor.fetchall()]
                cursor.execute(
                    """
                    SELECT quotation_snapshot
                    FROM public.historical_quotations
                    WHERE standard_type = %s
                      AND test_item = %s
                      AND standard_code = %s
                    ORDER BY saved_at DESC, id DESC
                    """,
                    (normalized_standard_type, normalized_test_item, normalized_standard_code),
                )
                quotation_snapshots = [row[0] for row in cursor.fetchall() if isinstance(row[0], dict)]
        return HistoricalQuotationCacheBuilder().build(
            normalized_standard_type,
            normalized_test_item,
            normalized_standard_code,
            reuse_fields,
            quotation_snapshots,
        )

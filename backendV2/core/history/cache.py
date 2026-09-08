from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class HistoricalQuotationReuseField:
    field_name: str
    field_section: str
    cache_scope: str
    is_grouping_key: bool


@dataclass(frozen=True, slots=True)
class HistoricalQuotationCache:
    standard_type: str
    test_item: str
    standard_code: str
    items: tuple[dict[str, dict[str, object]], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "standard_type": self.standard_type,
            "test_item": self.test_item,
            "standard_code": self.standard_code,
            "items": list(self.items),
        }


class HistoricalQuotationCacheBuilder:
    """Builds standard-condition cache entries from saved quotation snapshots."""

    def build(
        self,
        standard_type: str,
        test_item: str,
        standard_code: str,
        reuse_fields: Iterable[HistoricalQuotationReuseField],
        quotation_snapshots: Iterable[Mapping[str, object]],
    ) -> HistoricalQuotationCache:
        fields_by_scope: dict[str, list[HistoricalQuotationReuseField]] = defaultdict(list)
        for field in reuse_fields:
            fields_by_scope[field.cache_scope].append(field)

        items: list[dict[str, dict[str, object]]] = []
        snapshots = tuple(quotation_snapshots)
        for scope_fields in fields_by_scope.values():
            grouping_fields = tuple(field for field in scope_fields if field.is_grouping_key)
            if not grouping_fields:
                continue
            items.extend(self._build_scope_items(scope_fields, grouping_fields, snapshots))

        return HistoricalQuotationCache(
            standard_type=standard_type,
            test_item=test_item,
            standard_code=standard_code,
            items=tuple(items),
        )

    def _build_scope_items(
        self,
        scope_fields: list[HistoricalQuotationReuseField],
        grouping_fields: tuple[HistoricalQuotationReuseField, ...],
        quotation_snapshots: tuple[Mapping[str, object], ...],
    ) -> list[dict[str, dict[str, object]]]:
        grouped_snapshots: dict[tuple[str, ...], list[Mapping[str, object]]] = defaultdict(list)
        for snapshot in quotation_snapshots:
            grouping_values = tuple(self._field_value(snapshot, field) for field in grouping_fields)
            if any(value is None for value in grouping_values):
                continue
            grouped_snapshots[tuple(self._stable_value(value) for value in grouping_values)].append(snapshot)

        items: list[dict[str, dict[str, object]]] = []
        for group_key in sorted(grouped_snapshots):
            fields_by_section: dict[str, dict[str, object]] = defaultdict(dict)
            for field in scope_fields:
                values = [
                    value
                    for snapshot in grouped_snapshots[group_key]
                    if (value := self._field_value(snapshot, field)) is not None
                ]
                if values and self._all_equal(values):
                    fields_by_section[field.field_section][field.field_name] = values[0]
            if fields_by_section:
                items.append(dict(fields_by_section))
        return items

    @staticmethod
    def _field_value(snapshot: Mapping[str, object], field: HistoricalQuotationReuseField) -> object | None:
        section = snapshot.get(field.field_section)
        return section.get(field.field_name) if isinstance(section, Mapping) else None

    @classmethod
    def _all_equal(cls, values: list[object]) -> bool:
        expected = cls._stable_value(values[0])
        return all(cls._stable_value(value) == expected for value in values[1:])

    @staticmethod
    def _stable_value(value: object) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)

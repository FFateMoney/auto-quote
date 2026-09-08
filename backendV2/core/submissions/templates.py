from __future__ import annotations

from typing import Iterable


FIXED_QUOTE_VALUES = {
    "raw_test_type": None,
    "standard_code": None,
    "standard_document_section": None,
    "pricing_mode": None,
    "specification": None,
    "pricing_quantity": None,
    "sample_count": None,
    "length_mm": None,
    "width_mm": None,
    "height_mm": None,
}


def build_quote_values_template(
    pricing_mode: str,
    special_field_names: Iterable[str],
    specification: str | None = None,
) -> dict[str, dict[str, object | None]]:
    fixed_fields = dict(FIXED_QUOTE_VALUES)
    fixed_fields["pricing_mode"] = pricing_mode
    fixed_fields["specification"] = specification
    return {
        "固定字段": fixed_fields,
        "专有字段": {field_name: None for field_name in special_field_names},
    }

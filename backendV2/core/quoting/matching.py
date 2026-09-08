from __future__ import annotations

from typing import Any


def matches(device_value: Any, requirement_value: Any, comparison_type_id: int) -> bool:
    """Returns whether one device value satisfies one quoted special field."""

    match comparison_type_id:
        case 0:
            return bool(device_value <= requirement_value)
        case 1:
            return bool(device_value >= requirement_value)
        case 2:
            return bool(device_value == requirement_value)
        case 3:
            return bool(requirement_value in device_value)
    raise ValueError(f"unknown comparison_type_id: {comparison_type_id}")

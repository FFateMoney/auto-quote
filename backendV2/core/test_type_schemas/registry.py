from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from backendV2.core.settings import Settings


FieldValueType = Literal["number", "string", "string_array"]


@dataclass(frozen=True, slots=True)
class SchemaField:
    name: str
    label: str
    value_type: FieldValueType
    unit: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SchemaField":
        value_type = payload.get("value_type")
        if value_type not in {"number", "string", "string_array"}:
            raise ValueError(f"unsupported value_type for field {payload.get('name')!r}")
        name = str(payload.get("name") or "").strip()
        label = str(payload.get("label") or "").strip()
        if not name or not label:
            raise ValueError("each schema field requires name and label")
        unit = payload.get("unit")
        return cls(name=name, label=label, value_type=value_type, unit=str(unit) if unit else None)


@dataclass(frozen=True, slots=True)
class TestTypeSchema:
    schema_version: int
    test_type_id: int | None
    test_type_name: str
    fields: tuple[SchemaField, ...]
    source_path: Path

    @property
    def fields_by_name(self) -> dict[str, SchemaField]:
        return {field.name: field for field in self.fields}

    @classmethod
    def from_path(cls, path: Path) -> "TestTypeSchema":
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid test-type schema {path.name}: {exc.msg}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"test-type schema {path.name} must be a JSON object")

        schema_version = payload.get("schema_version")
        test_type_id = payload.get("test_type_id")
        test_type_name = str(payload.get("test_type_name") or "").strip()
        raw_fields = payload.get("fields")
        valid_test_type_id = test_type_id is None or (isinstance(test_type_id, int) and test_type_id > 0)
        if schema_version != 1 or not valid_test_type_id or not test_type_name:
            raise ValueError(f"test-type schema {path.name} has invalid metadata")
        if not isinstance(raw_fields, list) or not raw_fields:
            raise ValueError(f"test-type schema {path.name} must define fields")
        fields = tuple(SchemaField.from_dict(field) for field in raw_fields if isinstance(field, dict))
        if len(fields) != len(raw_fields) or len({field.name for field in fields}) != len(fields):
            raise ValueError(f"test-type schema {path.name} has invalid or duplicate fields")
        return cls(schema_version, test_type_id, test_type_name, fields, path)


class TestTypeSchemaRegistry:
    def __init__(self, schema_root: Path) -> None:
        self._schema_root = schema_root

    @classmethod
    def from_settings(cls, settings: Settings) -> "TestTypeSchemaRegistry":
        return cls(settings.test_type_schemas_root)

    def get(self, test_type_id: int | None) -> TestTypeSchema:
        file_name = "null.json" if test_type_id is None else f"{test_type_id:02d}.json"
        path = self._schema_root / file_name
        if not path.is_file():
            raise KeyError(test_type_id)
        schema = TestTypeSchema.from_path(path)
        if schema.test_type_id != test_type_id:
            raise ValueError(f"schema file {path.name} has mismatched test_type_id")
        return schema

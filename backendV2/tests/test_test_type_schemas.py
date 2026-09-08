from __future__ import annotations

import json
import unittest
from pathlib import Path

from backendV2.core.test_type_schemas.registry import TestTypeSchema


SCHEMA_DIRECTORY = Path(__file__).resolve().parents[1] / "core" / "test_type_schemas"
UNIVERSAL_FIELDS = {"length_mm", "width_mm", "height_mm", "max_load_kg"}
COMMON_QUOTE_FIELDS = {
    "raw_test_type",
    "standard_codes",
    "standard_document_section",
    "pricing_mode",
    "pricing_quantity",
    "sample_count",
}


class TestTypeSchemaTests(unittest.TestCase):
    def test_every_catalog_type_has_a_schema_with_universal_fields(self) -> None:
        schema_paths = sorted(SCHEMA_DIRECTORY.glob("[0-9][0-9].json"))
        self.assertEqual([path.name for path in schema_paths], [f"{value:02d}.json" for value in range(1, 19)])

        for path in schema_paths:
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], 1)
            self.assertEqual(payload["test_type_id"], int(path.stem))
            fields = payload["fields"]
            names = [field["name"] for field in fields]
            self.assertTrue(UNIVERSAL_FIELDS.issubset(names), path.name)
            self.assertTrue(COMMON_QUOTE_FIELDS.issubset(names), path.name)
            self.assertEqual(len(names), len(set(names)), path.name)

    def test_vibration_schema_has_only_vibration_specific_capabilities(self) -> None:
        payload = json.loads((SCHEMA_DIRECTORY / "10.json").read_text(encoding="utf-8"))
        names = {field["name"] for field in payload["fields"]}
        self.assertTrue({"freq_min", "freq_max", "accel_min", "accel_max", "displacement_min", "displacement_max"}.issubset(names))
        self.assertTrue({"temp_min", "temp_max", "humidity_min", "humidity_max"}.isdisjoint(names))

    def test_null_schema_contains_common_quote_and_universal_fields(self) -> None:
        schema = TestTypeSchema.from_path(SCHEMA_DIRECTORY / "null.json")
        self.assertIsNone(schema.test_type_id)
        self.assertEqual({field.name for field in schema.fields}, COMMON_QUOTE_FIELDS | UNIVERSAL_FIELDS)


if __name__ == "__main__":
    unittest.main()

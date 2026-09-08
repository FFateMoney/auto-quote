from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backendV2.core.submissions.validator import QuoteTableValidator


class QuoteTableValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = QuoteTableValidator()

    def test_accepts_a_valid_quote_table(self) -> None:
        result = self.validator.validate_payload(
            {
                "schema_version": 1,
                "test_project_id": 24,
                "values": self._vibration_values(),
            }
        )
        self.assertTrue(result.accepted)
        self.assertEqual(result.message, "成功")

    def test_reports_format_error_for_invalid_json_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "quote_table.json"
            path.write_text("{not-json", encoding="utf-8")
            result = self.validator.validate_file(path)
        self.assertFalse(result.accepted)
        self.assertEqual(result.message, "格式错误")
        self.assertEqual(result.details[0]["rule"], "json")

    def test_accepts_a_quote_with_an_unknown_test_project(self) -> None:
        result = self.validator.validate_payload(
            {
                "schema_version": 1,
                "test_project_id": None,
                "values": {
                    "固定字段": {
                        "length_mm": 100,
                        "width_mm": None,
                        "height_mm": None,
                    },
                    "专有字段": {},
                },
            }
        )
        self.assertTrue(result.accepted)

    @staticmethod
    def _vibration_values() -> dict[str, object]:
        return {
            "固定字段": {
                "raw_test_type": "振动运输试验",
                "standard_code": "MIL-STD-810G",
                "standard_document_section": "clause 514.6C-I, paragraph 2.1.2",
                "pricing_mode": "小时",
                "pricing_quantity": 15,
                "sample_count": 2,
                "length_mm": 1143,
                "width_mm": 488.95,
                "height_mm": 209.55,
            },
            "专有字段": {
                "frequency_min_hz": 10,
                "frequency_max_hz": 500,
                "acceleration_min_m_per_s2": None,
                "acceleration_max_m_per_s2": None,
                "max_peak_to_peak_displacement_mm": None,
            },
        }


if __name__ == "__main__":
    unittest.main()

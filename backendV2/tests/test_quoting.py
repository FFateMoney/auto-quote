from __future__ import annotations

from decimal import Decimal
import unittest

from backendV2.core.catalog.special_fields import SpecialFieldDefinition
from backendV2.core.quoting.matching import matches
from backendV2.core.quoting.repository import DeviceCandidate, QuotationProject, SpecificationOption
from backendV2.core.quoting.service import CoreQuotationService
from backendV2.core.submissions.models import QuoteTable, QuoteTableSubmission


class InMemoryQuotationRepository:
    def get_quotation_project(self, test_project_id: int) -> QuotationProject:
        if test_project_id != 23:
            raise KeyError(test_project_id)
        return QuotationProject(
            23,
            Decimal("800"),
            Decimal("200"),
            ("F10", "F3", "F1"),
            "振动",
            "随机振动",
            "3吨台",
            "时长",
        )

    def list_specification_options(self, test_project_id: int) -> list[SpecificationOption]:
        if test_project_id != 23:
            raise KeyError(test_project_id)
        return [
            SpecificationOption(22, "1吨台", "时长"),
            SpecificationOption(23, "3吨台", "时长"),
        ]

    def list_device_candidates(self, device_codes: tuple[str, ...]) -> list[DeviceCandidate]:
        del device_codes
        return [
            DeviceCandidate(
                "F1",
                Decimal("38.2"),
                {"frequency_min_hz": 5, "frequency_max_hz": 2000, "max_peak_to_peak_displacement_mm": 51},
            ),
            DeviceCandidate(
                "F3",
                Decimal("55.02"),
                {"frequency_min_hz": 2, "frequency_max_hz": 2500, "max_peak_to_peak_displacement_mm": 76},
            ),
            DeviceCandidate(
                "F10",
                Decimal("21"),
                {"frequency_min_hz": 5, "frequency_max_hz": 2000, "max_peak_to_peak_displacement_mm": 40},
            ),
        ]


class InMemorySpecialFieldRepository:
    def find_by_field_names(self, field_names: tuple[str, ...]) -> list[SpecialFieldDefinition]:
        types = {
            "frequency_min_hz": 0,
            "frequency_max_hz": 1,
            "max_peak_to_peak_displacement_mm": 1,
            "acceleration_min_m_per_s2": 0,
        }
        return [SpecialFieldDefinition(field_name, types[field_name]) for field_name in field_names]


class CoreQuotationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = CoreQuotationService(InMemoryQuotationRepository(), InMemorySpecialFieldRepository())

    def test_matches_all_comparison_types(self) -> None:
        self.assertTrue(matches(1, 2, 0))
        self.assertTrue(matches(2, 1, 1))
        self.assertTrue(matches("A", "A", 2))
        self.assertTrue(matches("ABC", "B", 3))

    def test_selects_lowest_power_eligible_device_and_calculates_amount(self) -> None:
        result = self.service.quote_table(self._submission())

        self.assertEqual(result.eligible_device_codes, ("F1", "F3"))
        self.assertEqual(result.selected_device_code, "F1")
        self.assertEqual(result.amount, Decimal("3800"))
        self.assertEqual(result.standard_type, "振动")
        self.assertEqual(result.test_item, "随机振动")
        self.assertEqual(result.specification, "3吨台")
        self.assertEqual(result.specification_options[0].specification, "1吨台")

    def test_can_select_another_eligible_device(self) -> None:
        result = self.service.quote_values(
            "quote-001",
            23,
            {"pricing_quantity": 15},
            {
                "frequency_min_hz": 10,
                "frequency_max_hz": 500,
                "max_peak_to_peak_displacement_mm": 51,
            },
            selected_device_code="F3",
        )

        self.assertEqual(result.selected_device_code, "F3")
        self.assertEqual(result.amount, Decimal("3800"))

    def test_calculates_amount_when_no_device_matches(self) -> None:
        result = self.service.quote_values(
            "quote-001",
            23,
            {"pricing_quantity": 15},
            {"frequency_max_hz": 5000},
        )

        self.assertEqual(result.eligible_device_codes, ())
        self.assertIsNone(result.selected_device_code)
        self.assertEqual(result.amount, Decimal("3800"))

    def test_ignores_a_requirement_when_device_capability_is_null(self) -> None:
        table = QuoteTable.model_validate(
            {
                "schema_version": 1,
                "test_project_id": 23,
                "values": {
                    "固定字段": {"pricing_quantity": 1},
                    "专有字段": {
                        "frequency_min_hz": 10,
                        "frequency_max_hz": 500,
                        "max_peak_to_peak_displacement_mm": 51,
                        "acceleration_min_m_per_s2": 0,
                    },
                },
            }
        )
        result = self.service.quote_table(QuoteTableSubmission("quote-001", table))

        self.assertEqual(result.eligible_device_codes, ("F1", "F3"))

    @staticmethod
    def _submission() -> QuoteTableSubmission:
        table = QuoteTable.model_validate(
            {
                "schema_version": 1,
                "test_project_id": 23,
                "values": {
                    "固定字段": {"pricing_quantity": 15},
                    "专有字段": {
                        "frequency_min_hz": 10,
                        "frequency_max_hz": 500,
                        "max_peak_to_peak_displacement_mm": 51,
                    },
                },
            }
        )
        return QuoteTableSubmission("quote-001", table)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

from backendV2.core.catalog.bootstrap_database import CAPABILITY_FIELD_NAMES, _build_test_project_capability_sets


class CatalogBootstrapTests(unittest.TestCase):
    def test_capability_set_is_the_union_of_nonempty_device_capabilities(self) -> None:
        project = {
            "standard_type": "振动",
            "test_item": "随机振动",
            "max_specification": "3吨台",
            "applicable_device_codes": ["F3", "N3"],
        }
        devices = [
            {
                **dict.fromkeys(CAPABILITY_FIELD_NAMES),
                "device_code": "F3",
                "max_length_mm": 1000,
                "frequency_min_hz": 2,
                "frequency_max_hz": 2500,
            },
            {
                **dict.fromkeys(CAPABILITY_FIELD_NAMES),
                "device_code": "N3",
                "max_width_mm": 1200,
                "frequency_min_hz": 5,
                "max_peak_to_peak_displacement_mm": 76,
            },
        ]

        result = _build_test_project_capability_sets([project], devices)

        self.assertEqual(
            result,
            [
                {
                    "standard_type": "振动",
                    "test_item": "随机振动",
                    "max_specification": "3吨台",
                    "capability_fields": [
                        "max_length_mm",
                        "max_width_mm",
                        "frequency_min_hz",
                        "frequency_max_hz",
                        "max_peak_to_peak_displacement_mm",
                    ],
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()

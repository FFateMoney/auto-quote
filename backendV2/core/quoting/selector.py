from __future__ import annotations

from dataclasses import dataclass

from backendV2.core.catalog.special_fields import SpecialFieldDefinitionReader
from backendV2.core.quoting.matching import matches
from backendV2.core.quoting.repository import (
    DeviceCandidate,
    QuotationProject,
    QuotationProjectReader,
    SpecificationOption,
)


@dataclass(frozen=True, slots=True)
class EquipmentSelection:
    project: QuotationProject
    specification_options: tuple[SpecificationOption, ...]
    eligible_devices: tuple[DeviceCandidate, ...]
    selected_device: DeviceCandidate | None


class EquipmentSelector:
    """Finds devices that satisfy one quotation's special requirements."""

    def __init__(
        self,
        projects: QuotationProjectReader,
        special_fields: SpecialFieldDefinitionReader,
    ) -> None:
        self._projects = projects
        self._special_fields = special_fields

    def select(
        self,
        test_project_id: int,
        requirements: dict[str, object],
        selected_device_code: str | None = None,
    ) -> EquipmentSelection:
        project = self._projects.get_quotation_project(test_project_id)
        comparison_types = {
            definition.field_name: definition.comparison_type_id
            for definition in self._special_fields.find_by_field_names(tuple(requirements))
        }
        candidates = self._projects.list_device_candidates(project.applicable_device_codes)
        eligible_devices = tuple(
            sorted(
                (
                    candidate
                    for candidate in candidates
                    if self._satisfies_requirements(candidate, requirements, comparison_types)
                ),
                key=lambda candidate: (candidate.power_kwh is None, candidate.power_kwh, candidate.device_code),
            )
        )
        selected_device = self._select_device(eligible_devices, selected_device_code)
        return EquipmentSelection(
            project=project,
            specification_options=tuple(self._projects.list_specification_options(test_project_id)),
            eligible_devices=eligible_devices,
            selected_device=selected_device,
        )

    @staticmethod
    def _select_device(
        eligible_devices: tuple[DeviceCandidate, ...],
        selected_device_code: str | None,
    ) -> DeviceCandidate | None:
        if selected_device_code is None:
            return eligible_devices[0] if eligible_devices else None
        for candidate in eligible_devices:
            if candidate.device_code == selected_device_code:
                return candidate
        raise ValueError(f"selected device is not eligible: {selected_device_code}")

    @staticmethod
    def _satisfies_requirements(
        candidate: DeviceCandidate,
        requirements: dict[str, object],
        comparison_types: dict[str, int],
    ) -> bool:
        for field_name, requirement_value in requirements.items():
            device_value = candidate.capabilities.get(field_name)
            if requirement_value is None or device_value is None:
                continue
            if not matches(device_value, requirement_value, comparison_types[field_name]):
                return False
        return True

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, Sequence

from backendV2.core.catalog.special_fields import SpecialFieldDefinitionReader
from backendV2.core.quoting.repository import DeviceCandidate, QuotationProjectReader, SpecificationOption
from backendV2.core.quoting.selector import EquipmentSelector
from backendV2.core.submissions.models import QuoteTableSubmission


@dataclass(frozen=True, slots=True)
class QuotationResult:
    quote_id: str
    test_project_id: int | None
    eligible_device_codes: tuple[str, ...]
    selected_device_code: str | None
    base_fee: Decimal | None
    unit_price: Decimal | None
    pricing_quantity: object | None
    amount: Decimal | None
    pricing_mode: str | None = None
    specification: str | None = None
    standard_type: str | None = None
    test_item: str | None = None
    specification_options: tuple[SpecificationOption, ...] = ()
    eligible_devices: tuple[DeviceCandidate, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "quote_id": self.quote_id,
            "test_project_id": self.test_project_id,
            "eligible_device_codes": list(self.eligible_device_codes),
            "selected_device_code": self.selected_device_code,
            "base_fee": float(self.base_fee) if self.base_fee is not None else None,
            "unit_price": float(self.unit_price) if self.unit_price is not None else None,
            "pricing_quantity": self.pricing_quantity,
            "amount": float(self.amount) if self.amount is not None else None,
            "pricing_mode": self.pricing_mode,
            "specification": self.specification,
            "standard_type": self.standard_type,
            "test_item": self.test_item,
            "specification_options": [option.to_dict() for option in self.specification_options],
            "eligible_devices": [device.to_dict() for device in self.eligible_devices],
        }


class QuotationProcessor(Protocol):
    def quote_batch(self, quote_tables: Sequence[QuoteTableSubmission]) -> list[QuotationResult]: ...

    def quote_values(
        self,
        quote_id: str,
        test_project_id: int | None,
        fixed_fields: dict[str, object],
        special_fields: dict[str, object],
        selected_device_code: str | None = None,
    ) -> QuotationResult: ...


class CoreQuotationService:
    """Selects suitable equipment and calculates submitted quotation amounts."""

    def __init__(
        self,
        projects: QuotationProjectReader,
        special_fields: SpecialFieldDefinitionReader,
    ) -> None:
        self._projects = projects
        self._selector = EquipmentSelector(projects, special_fields)

    def quote_batch(self, quote_tables: Sequence[QuoteTableSubmission]) -> list[QuotationResult]:
        return [self.quote_table(submission) for submission in quote_tables]

    def quote_table(self, submission: QuoteTableSubmission) -> QuotationResult:
        table = submission.quote_table
        return self.quote_values(
            submission.quote_id,
            table.test_project_id,
            table.values.fixed_fields,
            table.values.special_fields,
        )

    def quote_values(
        self,
        quote_id: str,
        test_project_id: int | None,
        fixed_fields: dict[str, object],
        special_fields: dict[str, object],
        selected_device_code: str | None = None,
    ) -> QuotationResult:
        if test_project_id is None:
            return QuotationResult(quote_id, None, (), None, None, None, None, None)

        selection = self._selector.select(test_project_id, special_fields, selected_device_code)
        project = selection.project
        quantity = fixed_fields.get("pricing_quantity")
        amount = self._amount(project.base_fee, project.unit_price, quantity) if quantity is not None else None
        return QuotationResult(
            quote_id=quote_id,
            test_project_id=test_project_id,
            eligible_device_codes=tuple(candidate.device_code for candidate in selection.eligible_devices),
            selected_device_code=selection.selected_device.device_code if selection.selected_device is not None else None,
            base_fee=project.base_fee,
            unit_price=project.unit_price,
            pricing_quantity=quantity,
            amount=amount,
            pricing_mode=project.pricing_mode,
            specification=project.max_specification,
            standard_type=project.standard_type,
            test_item=project.test_item,
            specification_options=selection.specification_options,
            eligible_devices=selection.eligible_devices,
        )

    @staticmethod
    def _amount(base_fee: Decimal, unit_price: Decimal, quantity: object | None) -> Decimal:
        return base_fee + Decimal(str(quantity)) * unit_price

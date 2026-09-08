from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

import psycopg
from psycopg.rows import dict_row

from backendV2.core.catalog.fields import DEVICE_CAPABILITY_FIELDS, TEST_PROJECT_CAPABILITY_FIELDS
from backendV2.core.settings import Settings


@dataclass(frozen=True, slots=True)
class CatalogTestProject:
    id: int
    standard_type: str
    test_item: str
    max_specification: str
    pricing_mode: str
    base_fee: Decimal
    unit_price: Decimal
    applicable_device_codes: tuple[str, ...]
    aliases: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "standard_type": self.standard_type,
            "test_item": self.test_item,
            "max_specification": self.max_specification,
            "pricing_mode": self.pricing_mode,
            "base_fee": float(self.base_fee),
            "unit_price": float(self.unit_price),
            "applicable_device_codes": list(self.applicable_device_codes),
            "aliases": list(self.aliases),
        }


@dataclass(frozen=True, slots=True)
class CatalogDevice:
    id: int
    device_code: str
    capabilities: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "device_code": self.device_code,
            "capabilities": self.capabilities,
        }


@dataclass(frozen=True, slots=True)
class CatalogTestProjectDraft:
    standard_type: str
    test_item: str
    max_specification: str
    pricing_mode: str
    base_fee: Decimal
    unit_price: Decimal
    applicable_device_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CatalogDeviceDraft:
    device_code: str
    capabilities: dict[str, object]


class CatalogManagementReader(Protocol):
    def list_catalog_test_projects(self) -> list[CatalogTestProject]: ...

    def list_catalog_devices(self) -> list[CatalogDevice]: ...

    def list_deleted_catalog_test_projects(self) -> list[CatalogTestProject]: ...

    def create_catalog_test_project(self, draft: CatalogTestProjectDraft) -> CatalogTestProject: ...

    def update_catalog_test_project(self, test_project_id: int, draft: CatalogTestProjectDraft) -> CatalogTestProject: ...

    def soft_delete_catalog_test_project(self, test_project_id: int) -> None: ...

    def restore_catalog_test_project(self, test_project_id: int) -> None: ...

    def update_catalog_test_project_aliases(self, test_project_id: int, aliases: tuple[str, ...]) -> CatalogTestProject: ...

    def list_deleted_catalog_devices(self) -> list[CatalogDevice]: ...

    def create_catalog_device(self, draft: CatalogDeviceDraft) -> CatalogDevice: ...

    def update_catalog_device(self, device_id: int, draft: CatalogDeviceDraft) -> CatalogDevice: ...

    def soft_delete_catalog_device(self, device_id: int) -> None: ...

    def restore_catalog_device(self, device_id: int) -> None: ...


class CatalogManagementRepository:
    """Database catalog used by the settings page."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def list_catalog_test_projects(self) -> list[CatalogTestProject]:
        return self._list_catalog_test_projects(is_deleted=False)

    def list_deleted_catalog_test_projects(self) -> list[CatalogTestProject]:
        return self._list_catalog_test_projects(is_deleted=True)

    def create_catalog_test_project(self, draft: CatalogTestProjectDraft) -> CatalogTestProject:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO public.test_projects (
                    standard_type, test_item, max_specification, pricing_mode,
                    base_fee, unit_price, applicable_device_codes
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id, standard_type, test_item, max_specification, pricing_mode,
                          base_fee, unit_price, applicable_device_codes, aliases
                """,
                self._draft_values(draft),
            )
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError("test project was not created")
            project = self._project_from_row(row)
            self._replace_capability_set(cursor, project.id, project.applicable_device_codes)
            return project

    def update_catalog_test_project(self, test_project_id: int, draft: CatalogTestProjectDraft) -> CatalogTestProject:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE public.test_projects
                SET
                    standard_type = %s,
                    test_item = %s,
                    max_specification = %s,
                    pricing_mode = %s,
                    base_fee = %s,
                    unit_price = %s,
                    applicable_device_codes = %s
                WHERE id = %s AND is_deleted = FALSE
                RETURNING id, standard_type, test_item, max_specification, pricing_mode,
                          base_fee, unit_price, applicable_device_codes, aliases
                """,
                (*self._draft_values(draft), test_project_id),
            )
            row = cursor.fetchone()
            if row is None:
                raise KeyError(test_project_id)
            project = self._project_from_row(row)
            self._replace_capability_set(cursor, project.id, project.applicable_device_codes)
            return project

    def soft_delete_catalog_test_project(self, test_project_id: int) -> None:
        self._set_deletion_status(test_project_id, is_deleted=True, expected_is_deleted=False)

    def restore_catalog_test_project(self, test_project_id: int) -> None:
        self._set_deletion_status(test_project_id, is_deleted=False, expected_is_deleted=True)

    def update_catalog_test_project_aliases(self, test_project_id: int, aliases: tuple[str, ...]) -> CatalogTestProject:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE public.test_projects
                SET aliases = %s
                WHERE id = %s AND is_deleted = FALSE
                RETURNING id, standard_type, test_item, max_specification, pricing_mode,
                          base_fee, unit_price, applicable_device_codes, aliases
                """,
                ([alias.strip() for alias in aliases if alias.strip()], test_project_id),
            )
            row = cursor.fetchone()
            if row is None:
                raise KeyError(test_project_id)
            return self._project_from_row(row)

    def list_catalog_devices(self) -> list[CatalogDevice]:
        return self._list_catalog_devices(is_deleted=False)

    def list_deleted_catalog_devices(self) -> list[CatalogDevice]:
        return self._list_catalog_devices(is_deleted=True)

    def create_catalog_device(self, draft: CatalogDeviceDraft) -> CatalogDevice:
        columns = ("device_code", *DEVICE_CAPABILITY_FIELDS)
        placeholders = ", ".join("%s" for _ in columns)
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO public.device_capabilities ({", ".join(columns)})
                VALUES ({placeholders})
                RETURNING id, device_code, to_jsonb(device_capabilities) - 'id' - 'device_code' AS capabilities
                """,
                self._device_draft_values(draft),
            )
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError("device was not created")
            return self._device_from_row(row)

    def update_catalog_device(self, device_id: int, draft: CatalogDeviceDraft) -> CatalogDevice:
        assignments = ", ".join(f"{column} = %s" for column in ("device_code", *DEVICE_CAPABILITY_FIELDS))
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT device_code FROM public.device_capabilities WHERE id = %s AND is_deleted = FALSE",
                (device_id,),
            )
            previous = cursor.fetchone()
            if previous is None:
                raise KeyError(device_id)
            previous_code = str(previous["device_code"])
            cursor.execute(
                f"""
                UPDATE public.device_capabilities
                SET {assignments}
                WHERE id = %s AND is_deleted = FALSE
                RETURNING id, device_code, to_jsonb(device_capabilities) - 'id' - 'device_code' AS capabilities
                """,
                (*self._device_draft_values(draft), device_id),
            )
            row = cursor.fetchone()
            if row is None:
                raise KeyError(device_id)
            device = self._device_from_row(row)
            if previous_code != device.device_code:
                cursor.execute(
                    """
                    UPDATE public.test_projects
                    SET applicable_device_codes = array_replace(applicable_device_codes, %s, %s)
                    WHERE %s = ANY(applicable_device_codes)
                    """,
                    (previous_code, device.device_code, previous_code),
                )
            self._refresh_capability_sets_for_device(cursor, device.device_code)
            return device

    def soft_delete_catalog_device(self, device_id: int) -> None:
        self._set_device_deletion_status(device_id, is_deleted=True, expected_is_deleted=False)

    def restore_catalog_device(self, device_id: int) -> None:
        self._set_device_deletion_status(device_id, is_deleted=False, expected_is_deleted=True)

    def _list_catalog_devices(self, is_deleted: bool) -> list[CatalogDevice]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, device_code, to_jsonb(device_capabilities) - 'id' - 'device_code' AS capabilities
                FROM public.device_capabilities
                WHERE is_deleted = %s
                ORDER BY device_code, id
                """,
                (is_deleted,),
            )
            return [self._device_from_row(row) for row in cursor.fetchall()]

    def _list_catalog_test_projects(self, is_deleted: bool) -> list[CatalogTestProject]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    standard_type,
                    test_item,
                    max_specification,
                    pricing_mode,
                    base_fee,
                    unit_price,
                    applicable_device_codes,
                    aliases
                FROM public.test_projects
                WHERE is_deleted = %s
                ORDER BY standard_type, test_item, max_specification, id
                """,
                (is_deleted,),
            )
            return [self._project_from_row(row) for row in cursor.fetchall()]

    def _replace_capability_set(
        self,
        cursor: psycopg.Cursor[dict[str, object]],
        test_project_id: int,
        device_codes: tuple[str, ...],
        *,
        allow_deleted_devices: bool = False,
    ) -> None:
        cursor.execute(
            "SELECT device_code, is_deleted, to_jsonb(device_capabilities) AS capabilities "
            "FROM public.device_capabilities WHERE device_code = ANY(%s)",
            (list(device_codes),),
        )
        devices = cursor.fetchall()
        found_codes = {str(row["device_code"]) for row in devices}
        unknown_codes = sorted(set(device_codes) - found_codes)
        if unknown_codes:
            raise ValueError(f"unknown device codes: {', '.join(unknown_codes)}")
        deleted_codes = sorted(str(row["device_code"]) for row in devices if row["is_deleted"])
        if deleted_codes and not allow_deleted_devices:
            raise ValueError(f"deleted device codes cannot be selected: {', '.join(deleted_codes)}")
        active_devices = [row for row in devices if not row["is_deleted"]]
        capability_fields = [
            field_name
            for field_name in TEST_PROJECT_CAPABILITY_FIELDS
            if any(row["capabilities"].get(field_name) is not None for row in active_devices)
        ]
        cursor.execute(
            """
            INSERT INTO public.test_project_capability_sets (test_project_id, capability_fields)
            VALUES (%s, %s)
            ON CONFLICT (test_project_id)
            DO UPDATE SET capability_fields = EXCLUDED.capability_fields
            """,
            (test_project_id, capability_fields),
        )

    def _refresh_capability_sets_for_device(
        self,
        cursor: psycopg.Cursor[dict[str, object]],
        device_code: str,
    ) -> None:
        cursor.execute(
            """
            SELECT id, applicable_device_codes
            FROM public.test_projects
            WHERE is_deleted = FALSE AND %s = ANY(applicable_device_codes)
            """,
            (device_code,),
        )
        for row in cursor.fetchall():
            self._replace_capability_set(
                cursor,
                int(row["id"]),
                tuple(str(code) for code in row["applicable_device_codes"]),
                allow_deleted_devices=True,
            )

    def _set_deletion_status(self, test_project_id: int, *, is_deleted: bool, expected_is_deleted: bool) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "UPDATE public.test_projects SET is_deleted = %s WHERE id = %s AND is_deleted = %s",
                (is_deleted, test_project_id, expected_is_deleted),
            )
            if cursor.rowcount != 1:
                raise KeyError(test_project_id)

    def _set_device_deletion_status(self, device_id: int, *, is_deleted: bool, expected_is_deleted: bool) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE public.device_capabilities
                SET is_deleted = %s
                WHERE id = %s AND is_deleted = %s
                RETURNING device_code
                """,
                (is_deleted, device_id, expected_is_deleted),
            )
            row = cursor.fetchone()
            if row is None:
                raise KeyError(device_id)
            self._refresh_capability_sets_for_device(cursor, str(row["device_code"]))

    @staticmethod
    def _draft_values(draft: CatalogTestProjectDraft) -> tuple[object, ...]:
        return (
            draft.standard_type.strip(),
            draft.test_item.strip(),
            draft.max_specification.strip(),
            draft.pricing_mode.strip(),
            draft.base_fee,
            draft.unit_price,
            list(draft.applicable_device_codes),
        )

    @staticmethod
    def _project_from_row(row: dict[str, object]) -> CatalogTestProject:
        return CatalogTestProject(
            id=int(row["id"]),
            standard_type=str(row["standard_type"]).strip(),
            test_item=str(row["test_item"]).strip(),
            max_specification=str(row["max_specification"]).strip(),
            pricing_mode=str(row["pricing_mode"]).strip(),
            base_fee=Decimal(row["base_fee"]),
            unit_price=Decimal(row["unit_price"]),
            applicable_device_codes=tuple(str(code) for code in row["applicable_device_codes"]),
            aliases=tuple(str(alias) for alias in row["aliases"]),
        )

    @staticmethod
    def _device_draft_values(draft: CatalogDeviceDraft) -> tuple[object, ...]:
        unknown_fields = set(draft.capabilities) - set(DEVICE_CAPABILITY_FIELDS)
        if unknown_fields:
            raise ValueError(f"unknown device capability fields: {', '.join(sorted(unknown_fields))}")
        return (
            draft.device_code.strip(),
            *(draft.capabilities.get(field_name) for field_name in DEVICE_CAPABILITY_FIELDS),
        )

    @staticmethod
    def _device_from_row(row: dict[str, object]) -> CatalogDevice:
        capabilities = dict(row["capabilities"])
        return CatalogDevice(
            id=int(row["id"]),
            device_code=str(row["device_code"]).strip(),
            capabilities={field: capabilities.get(field) for field in DEVICE_CAPABILITY_FIELDS},
        )

    def _connect(self) -> psycopg.Connection[dict[str, object]]:
        connection_args = {key: value for key, value in self._settings.database.items() if value not in (None, "")}
        return psycopg.connect(row_factory=dict_row, **connection_args)

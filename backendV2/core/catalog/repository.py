from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import psycopg
from psycopg.rows import dict_row

from backendV2.core.settings import Settings


@dataclass(frozen=True, slots=True)
class TestProject:
    id: int
    standard_type: str
    test_item: str
    max_specification: str
    pricing_mode: str

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "standard_type": self.standard_type,
            "test_item": self.test_item,
            "max_specification": self.max_specification,
            "pricing_mode": self.pricing_mode,
        }


@dataclass(frozen=True, slots=True)
class TestProjectQuoteTemplate:
    pricing_mode: str
    capability_fields: tuple[str, ...]
    max_specification: str = ""


class TestProjectReader(Protocol):
    def list_test_projects(self) -> list[TestProject]: ...


class TestProjectQuoteTemplateReader(Protocol):
    def get_quote_template(self, test_project_id: int) -> TestProjectQuoteTemplate: ...


class TestProjectAliasReader(Protocol):
    def get_test_project_aliases(self, test_project_id: int) -> tuple[str, ...]: ...


class TestProjectAliasWriter(Protocol):
    def append_test_project_aliases(self, aliases_by_project: dict[int, tuple[str, ...]]) -> None: ...


class TestProjectRepository:
    """Read-only access to the project-pricing catalog used by quotation agents."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def list_test_projects(self) -> list[TestProject]:
        connection_args = {key: value for key, value in self._settings.database.items() if value not in (None, "")}
        with psycopg.connect(row_factory=dict_row, **connection_args) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, standard_type, test_item, max_specification, pricing_mode
                    FROM public.test_projects
                    WHERE is_deleted = FALSE
                    ORDER BY standard_type, test_item, max_specification
                    """
                )
                return [
                    TestProject(
                        id=int(row["id"]),
                        standard_type=str(row["standard_type"]).strip(),
                        test_item=str(row["test_item"]).strip(),
                        max_specification=str(row["max_specification"]).strip(),
                        pricing_mode=str(row["pricing_mode"]).strip(),
                    )
                    for row in cursor.fetchall()
                ]

    def get_quote_template(self, test_project_id: int) -> TestProjectQuoteTemplate:
        connection_args = {key: value for key, value in self._settings.database.items() if value not in (None, "")}
        with psycopg.connect(row_factory=dict_row, **connection_args) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT project.pricing_mode, project.max_specification, capability_set.capability_fields
                    FROM public.test_projects AS project
                    INNER JOIN public.test_project_capability_sets AS capability_set
                        ON capability_set.test_project_id = project.id
                    WHERE project.id = %s
                    """,
                    (test_project_id,),
                )
                row = cursor.fetchone()
                if row is None:
                    raise KeyError(test_project_id)
                return TestProjectQuoteTemplate(
                    pricing_mode=str(row["pricing_mode"]).strip(),
                    capability_fields=tuple(str(field) for field in row["capability_fields"]),
                    max_specification=str(row["max_specification"]).strip(),
                )

    def get_test_project_aliases(self, test_project_id: int) -> tuple[str, ...]:
        connection_args = {key: value for key, value in self._settings.database.items() if value not in (None, "")}
        with psycopg.connect(row_factory=dict_row, **connection_args) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT aliases
                    FROM public.test_projects
                    WHERE id = %s AND is_deleted = FALSE
                    """,
                    (test_project_id,),
                )
                row = cursor.fetchone()
                if row is None:
                    raise KeyError(test_project_id)
                return tuple(str(alias) for alias in row["aliases"])

    def append_test_project_aliases(self, aliases_by_project: dict[int, tuple[str, ...]]) -> None:
        if not aliases_by_project:
            return
        connection_args = {key: value for key, value in self._settings.database.items() if value not in (None, "")}
        with psycopg.connect(row_factory=dict_row, **connection_args) as connection:
            with connection.cursor() as cursor:
                for test_project_id, aliases in aliases_by_project.items():
                    cleaned_aliases = [alias.strip() for alias in aliases if alias.strip()]
                    if not cleaned_aliases:
                        continue
                    cursor.execute(
                        """
                        SELECT aliases
                        FROM public.test_projects
                        WHERE id = %s AND is_deleted = FALSE
                        FOR UPDATE
                        """,
                        (test_project_id,),
                    )
                    row = cursor.fetchone()
                    if row is None:
                        continue
                    current_aliases = [str(alias) for alias in row["aliases"]]
                    for alias in cleaned_aliases:
                        if alias not in current_aliases:
                            current_aliases.append(alias)
                    cursor.execute(
                        "UPDATE public.test_projects SET aliases = %s WHERE id = %s",
                        (current_aliases, test_project_id),
                    )

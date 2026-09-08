from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

import psycopg
from psycopg.rows import dict_row

from backendV2.core.settings import Settings


@dataclass(frozen=True, slots=True)
class SpecialFieldDefinition:
    field_name: str
    comparison_type_id: int


class SpecialFieldDefinitionReader(Protocol):
    def find_by_field_names(self, field_names: Sequence[str]) -> list[SpecialFieldDefinition]: ...


class SpecialFieldDefinitionRepository:
    """Reads the comparison protocol assigned to Agent-facing special fields."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def find_by_field_names(self, field_names: Sequence[str]) -> list[SpecialFieldDefinition]:
        if not field_names:
            return []
        connection_args = {key: value for key, value in self._settings.database.items() if value not in (None, "")}
        with psycopg.connect(row_factory=dict_row, **connection_args) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT field_name, comparison_type_id
                    FROM public.special_field_definitions
                    WHERE field_name = ANY(%s)
                    ORDER BY id
                    """,
                    (list(field_names),),
                )
                return [
                    SpecialFieldDefinition(
                        field_name=str(row["field_name"]),
                        comparison_type_id=int(row["comparison_type_id"]),
                    )
                    for row in cursor.fetchall()
                ]

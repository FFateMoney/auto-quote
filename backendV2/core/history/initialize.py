from __future__ import annotations

from pathlib import Path

import psycopg

from backendV2.core.settings import Settings


MIGRATION_PATHS = (
    Path(__file__).parents[1] / "catalog" / "migrations" / "006_create_historical_quotations.sql",
    Path(__file__).parents[1] / "catalog" / "migrations" / "007_create_historical_quotation_reuse_fields.sql",
)


def initialize_historical_quotations(settings: Settings) -> None:
    connection_args = {key: value for key, value in settings.database.items() if value not in (None, "")}
    with psycopg.connect(**connection_args) as connection:
        with connection.cursor() as cursor:
            for migration_path in MIGRATION_PATHS:
                cursor.execute(migration_path.read_text(encoding="utf-8"))

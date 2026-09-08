from __future__ import annotations

from pathlib import Path

import psycopg

from backendV2.core.settings import Settings


INITIALIZATION_SQL_PATH = Path(__file__).parent / "migrations" / "002_create_special_field_definitions.sql"


def initialize_special_field_definitions(settings: Settings) -> None:
    connection_args = {key: value for key, value in settings.database.items() if value not in (None, "")}
    with psycopg.connect(**connection_args) as connection:
        with connection.cursor() as cursor:
            cursor.execute(INITIALIZATION_SQL_PATH.read_text(encoding="utf-8"))


def main() -> None:
    initialize_special_field_definitions(Settings.from_environment())


if __name__ == "__main__":
    main()

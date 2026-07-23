"""Shared SQLite/PostgreSQL connection helpers."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


def uses_postgres(database_url: str) -> bool:
    return bool(database_url.strip())


def adapt_query(query: str, database_url: str) -> str:
    """Convert portable ``?`` placeholders to psycopg placeholders."""
    return query.replace("?", "%s") if uses_postgres(database_url) else query


@contextmanager
def connect(database_url: str, sqlite_path: Path) -> Iterator[Any]:
    if uses_postgres(database_url):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as error:
            raise RuntimeError(
                "psycopg is required when DATABASE_URL is configured"
            ) from error

        # AIDEV-NOTE: Disabling prepared statements keeps this compatible with either Supabase pooler mode.
        with psycopg.connect(
            database_url,
            row_factory=dict_row,
            prepare_threshold=None,
        ) as connection:
            yield connection
        return

    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(sqlite_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        with connection:
            yield connection
    finally:
        connection.close()

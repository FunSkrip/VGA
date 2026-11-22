"""SQLite connection settings applied through SQLAlchemy."""
from __future__ import annotations

import sqlite3

from sqlalchemy import event
from sqlalchemy.engine import Engine

_BUSY_TIMEOUT_MS = 5000


def _apply_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
    if not isinstance(dbapi_connection, sqlite3.Connection):
        return
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA temp_store=MEMORY")
    finally:
        cursor.close()


def register_sqlite_pragmas() -> None:
    """Enable WAL, foreign keys and sane SQLite defaults for every connection."""
    if not event.contains(Engine, "connect", _apply_sqlite_pragmas):
        event.listen(Engine, "connect", _apply_sqlite_pragmas)

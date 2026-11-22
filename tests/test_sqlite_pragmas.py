import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from app.database import register_sqlite_pragmas


def test_sqlite_pragmas_are_applied(tmp_path):
    register_sqlite_pragmas()
    engine = create_engine(f"sqlite:///{tmp_path / 'vga.db'}")
    try:
        with engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA journal_mode").scalar().lower() == "wal"
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
            assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar() == 5000
            assert connection.exec_driver_sql("PRAGMA synchronous").scalar() == 1
            assert connection.exec_driver_sql("PRAGMA temp_store").scalar() == 2
    finally:
        engine.dispose()


def test_foreign_keys_are_enforced(tmp_path):
    register_sqlite_pragmas()
    engine = create_engine(f"sqlite:///{tmp_path / 'foreign.db'}")
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE parent (id INTEGER PRIMARY KEY)"))
            connection.execute(
                text(
                    "CREATE TABLE child (id INTEGER PRIMARY KEY, "
                    "parent_id INTEGER REFERENCES parent(id))"
                )
            )
        with engine.connect() as connection:
            with pytest.raises(IntegrityError):
                connection.execute(text("INSERT INTO child (id, parent_id) VALUES (1, 999)"))
    finally:
        engine.dispose()

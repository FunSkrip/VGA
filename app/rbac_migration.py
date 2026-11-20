"""Small SQLite schema migration for existing VGA installations.

Flask-SQLAlchemy's create_all() does not add columns to an existing table, so this
module upgrades the legacy `user` table before the first request is handled.
"""
from sqlalchemy import inspect, text


def upgrade_legacy_schema(db):
    inspector = inspect(db.engine)
    tables = set(inspector.get_table_names())
    if "user" not in tables:
        return

    columns = {column["name"] for column in inspector.get_columns("user")}
    with db.engine.begin() as connection:
        if "role" not in columns:
            connection.execute(
                text("ALTER TABLE \"user\" ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'user'")
            )
        if "is_blocked" not in columns:
            connection.execute(
                text("ALTER TABLE \"user\" ADD COLUMN is_blocked BOOLEAN NOT NULL DEFAULT 0")
            )
        connection.execute(
            text("UPDATE \"user\" SET role = 'user' WHERE role IS NULL OR role = ''")
        )

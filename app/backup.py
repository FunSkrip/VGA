"""Create, verify and restore encrypted SQLite backups."""
from __future__ import annotations

import glob
import os
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone

from app.backup_crypto import (
    BackupFormatError,
    KeyringError,
    decrypt_file,
    encrypt_file,
    load_keyring,
    read_header,
)


class BackupError(RuntimeError):
    """Raised when a backup or restore operation cannot be completed safely."""


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _sqlite_connect(path: str) -> sqlite3.Connection:
    return sqlite3.connect(path, timeout=30.0)


def _check_integrity(path: str) -> None:
    connection = _sqlite_connect(path)
    try:
        result = connection.execute("PRAGMA integrity_check").fetchone()
    finally:
        connection.close()
    if not result or str(result[0]).lower() != "ok":
        detail = result[0] if result else "no result"
        raise BackupError(f"SQLite integrity check failed: {detail}")


def create_sqlite_snapshot(source_path: str, destination_path: str) -> None:
    """Create a consistent SQLite snapshot, including committed WAL data."""
    if not os.path.isfile(source_path):
        raise BackupError(f"Database not found: {source_path}")
    destination_dir = os.path.dirname(destination_path) or "."
    os.makedirs(destination_dir, exist_ok=True)
    if os.path.exists(destination_path):
        os.unlink(destination_path)

    source = _sqlite_connect(source_path)
    destination = _sqlite_connect(destination_path)
    try:
        source.backup(destination)
        destination.commit()
    finally:
        destination.close()
        source.close()
    _check_integrity(destination_path)


def _next_backup_path(backup_dir: str) -> str:
    base = f"vga-{_timestamp()}.db.vgaenc"
    candidate = os.path.join(backup_dir, base)
    if not os.path.exists(candidate):
        return candidate

    counter = 1
    while True:
        candidate = os.path.join(backup_dir, f"vga-{_timestamp()}-{counter}.db.vgaenc")
        if not os.path.exists(candidate):
            return candidate
        counter += 1


def prune_backups(backup_dir: str, keep_days: int) -> list[str]:
    """Delete old encrypted backups, keeping at least one file."""
    if keep_days <= 0:
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)
    paths = sorted(
        glob.glob(os.path.join(backup_dir, "vga-*.db.vgaenc")),
        key=lambda path: os.path.getmtime(path),
    )
    removed = []
    for path in paths[:-1]:
        modified = datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc)
        if modified >= cutoff:
            continue
        try:
            os.unlink(path)
            removed.append(path)
        except OSError:
            continue
    return removed


def create_database_backup(
    db_path: str,
    backup_dir: str,
    keyring_path: str,
    *,
    keep_days: int = 15,
    prune: bool = True,
) -> dict:
    keyring = load_keyring(keyring_path)
    os.makedirs(backup_dir, exist_ok=True)

    descriptor, snapshot_path = tempfile.mkstemp(
        dir=backup_dir, prefix=".vga-snapshot.", suffix=".db"
    )
    os.close(descriptor)
    os.unlink(snapshot_path)
    backup_path = _next_backup_path(backup_dir)

    try:
        create_sqlite_snapshot(db_path, snapshot_path)
        metadata = encrypt_file(snapshot_path, backup_path, keyring)
    except (BackupError, BackupFormatError, KeyringError):
        try:
            os.unlink(backup_path)
        except OSError:
            pass
        raise
    except Exception as exc:
        try:
            os.unlink(backup_path)
        except OSError:
            pass
        raise BackupError("Unable to create the encrypted backup") from exc
    finally:
        try:
            os.unlink(snapshot_path)
        except OSError:
            pass

    removed = prune_backups(backup_dir, keep_days) if prune else []
    return {**metadata, "removed_old": removed}


def verify_backup(backup_path: str, keyring_path: str) -> dict:
    if not os.path.isfile(backup_path):
        raise BackupError(f"Backup not found: {backup_path}")
    keyring = load_keyring(keyring_path)
    header = read_header(backup_path)

    descriptor, restored_path = tempfile.mkstemp(
        dir=os.path.dirname(backup_path) or ".",
        prefix=".vga-verify.",
        suffix=".db",
    )
    os.close(descriptor)
    try:
        metadata = decrypt_file(
            backup_path,
            restored_path,
            keyring,
            expected_sha256=header.get("sha256"),
        )
        _check_integrity(restored_path)
        connection = _sqlite_connect(restored_path)
        try:
            tables = [
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                )
            ]
        finally:
            connection.close()
        return {**metadata, "tables": tables}
    except BackupFormatError as exc:
        raise BackupError("Backup authentication or format check failed") from exc
    finally:
        try:
            os.unlink(restored_path)
        except OSError:
            pass


def restore_database_backup(
    backup_path: str,
    db_path: str,
    keyring_path: str,
    *,
    keep_current: bool = True,
) -> dict:
    if not os.path.isfile(backup_path):
        raise BackupError(f"Backup not found: {backup_path}")
    db_dir = os.path.dirname(db_path) or "."
    os.makedirs(db_dir, exist_ok=True)
    keyring = load_keyring(keyring_path)
    header = read_header(backup_path)

    descriptor, restored_path = tempfile.mkstemp(
        dir=db_dir, prefix=".vga-restore.", suffix=".db"
    )
    os.close(descriptor)
    os.unlink(restored_path)
    pre_restore_path = None

    try:
        decrypt_file(
            backup_path,
            restored_path,
            keyring,
            expected_sha256=header.get("sha256"),
        )
        _check_integrity(restored_path)

        if keep_current and os.path.isfile(db_path):
            pre_restore_path = os.path.join(
                db_dir, f"VKR_YOLO.db.pre-restore-{_timestamp()}"
            )
            create_sqlite_snapshot(db_path, pre_restore_path)

        try:
            os.replace(restored_path, db_path)
        except OSError as exc:
            raise BackupError(
                "Could not replace the database. Stop the application first."
            ) from exc
        restored_path = ""

        for suffix in ("-wal", "-shm"):
            sidecar = db_path + suffix
            try:
                os.unlink(sidecar)
            except OSError:
                pass

        _check_integrity(db_path)
        connection = _sqlite_connect(db_path)
        try:
            counts = {
                table: connection.execute(
                    f'SELECT COUNT(*) FROM "{table}"'
                ).fetchone()[0]
                for table in ("user", "media_file", "audit_log")
            }
        finally:
            connection.close()
        return {
            "path": db_path,
            "pre_restore_backup": pre_restore_path,
            "counts": counts,
            "backup": header,
        }
    except BackupFormatError as exc:
        raise BackupError("Backup authentication or format check failed") from exc
    finally:
        if restored_path:
            try:
                os.unlink(restored_path)
            except OSError:
                pass




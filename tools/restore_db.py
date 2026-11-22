"""Restore the VGA database from an encrypted backup.

Stop the application before running this command.
"""
from __future__ import annotations

import argparse
import glob
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import Config
from app.backup import BackupError, restore_database_backup
from app.backup_crypto import KeyringError


def latest_backup(backup_dir: str) -> str | None:
    paths = sorted(
        glob.glob(os.path.join(backup_dir, "vga-*.db.vgaenc")),
        key=lambda path: os.path.getmtime(path),
    )
    return paths[-1] if paths else None


def write_audit_event(action: str, details: dict) -> None:
    try:
        from app import create_app
        from app.security import audit_event

        app = create_app()
        with app.app_context():
            audit_event(
                action,
                target_type="database",
                target_id="VKR_YOLO.db",
                details=details,
            )
    except Exception as exc:
        print(f"Warning: audit event was not written: {type(exc).__name__}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", help="encrypted backup file; defaults to the newest")
    parser.add_argument("--db", default=Config.DATABASE_PATH)
    parser.add_argument("--keyring", default=Config.BACKUP_KEYRING)
    parser.add_argument("--no-keep-current", action="store_true")
    parser.add_argument("--yes", action="store_true")
    arguments = parser.parse_args()

    backup_path = arguments.backup or latest_backup(Config.BACKUP_DIR)
    if not backup_path:
        print("No backup found.", file=sys.stderr)
        return 1

    print("Stop the VGA application before restoring.")
    print(f"Backup: {backup_path}")
    print(f"Database: {arguments.db}")
    if not arguments.yes:
        answer = input('Type "restore" to continue: ').strip().lower()
        if answer != "restore":
            print("Restore cancelled.")
            return 1

    try:
        result = restore_database_backup(
            backup_path,
            arguments.db,
            arguments.keyring,
            keep_current=not arguments.no_keep_current,
        )
    except (BackupError, KeyringError) as exc:
        print(f"Restore failed: {exc}", file=sys.stderr)
        return 1

    print("Restore completed.")
    for table, count in result["counts"].items():
        print(f"  {table}: {count}")
    if result["pre_restore_backup"]:
        print(f"Previous database saved as: {result['pre_restore_backup']}")

    write_audit_event(
        "backup_restored",
        {
            "backup": os.path.basename(backup_path),
            "counts": result["counts"],
            "pre_restore_backup": (
                os.path.basename(result["pre_restore_backup"])
                if result["pre_restore_backup"]
                else None
            ),
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

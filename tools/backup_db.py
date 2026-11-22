"""Create an encrypted backup of the VGA SQLite database.

Examples:
    python tools/backup_db.py --init-keyring
    python tools/backup_db.py
    python tools/backup_db.py --keep-days 15
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import Config
from app.backup import BackupError, create_database_backup
from app.backup_crypto import KeyringError, create_keyring


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024 or unit == "GiB":
            return f"{int(value)} B" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


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
    parser.add_argument("--init-keyring", action="store_true")
    parser.add_argument("--db", default=Config.DATABASE_PATH)
    parser.add_argument("--backup-dir", default=Config.BACKUP_DIR)
    parser.add_argument("--keyring", default=Config.BACKUP_KEYRING)
    parser.add_argument("--keep-days", type=int, default=Config.BACKUP_KEEP_DAYS)
    parser.add_argument("--no-prune", action="store_true")
    arguments = parser.parse_args()

    try:
        if arguments.init_keyring:
            create_keyring(arguments.keyring)
            print(f"Keyring created: {arguments.keyring}")
            print("Store this file outside the project and keep a secure copy.")
            return 0

        result = create_database_backup(
            arguments.db,
            arguments.backup_dir,
            arguments.keyring,
            keep_days=arguments.keep_days,
            prune=not arguments.no_prune,
        )
    except (BackupError, KeyringError) as exc:
        print(f"Backup failed: {exc}", file=sys.stderr)
        return 1

    print(f"Backup created: {result['path']}")
    print(f"Plaintext size: {human_size(result['original_size'])}")
    print(f"Encrypted size: {human_size(result['encrypted_size'])}")
    print(f"Key id: {result['key_id']}")
    if result["removed_old"]:
        print(f"Removed old backups: {len(result['removed_old'])}")

    write_audit_event(
        "backup_created",
        {
            "backup": os.path.basename(result["path"]),
            "key_id": result["key_id"],
            "size_bytes": result["original_size"],
            "encrypted_size": result["encrypted_size"],
            "removed_old": len(result["removed_old"]),
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

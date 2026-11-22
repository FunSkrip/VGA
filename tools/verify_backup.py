"""Verify an encrypted VGA database backup without restoring it."""
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
from app.backup import BackupError, verify_backup
from app.backup_crypto import KeyringError


def latest_backup(backup_dir: str) -> str | None:
    paths = sorted(
        glob.glob(os.path.join(backup_dir, "vga-*.db.vgaenc")),
        key=lambda path: os.path.getmtime(path),
    )
    return paths[-1] if paths else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", help="encrypted backup file; defaults to the newest")
    parser.add_argument("--keyring", default=Config.BACKUP_KEYRING)
    arguments = parser.parse_args()

    backup_path = arguments.backup or latest_backup(Config.BACKUP_DIR)
    if not backup_path:
        print("No backup found.", file=sys.stderr)
        return 1

    try:
        result = verify_backup(backup_path, arguments.keyring)
    except (BackupError, KeyringError) as exc:
        print(f"Verification failed: {exc}", file=sys.stderr)
        return 1

    print(f"Backup verified: {backup_path}")
    print(f"Key id: {result['key_id']}")
    print(f"Original size: {result['original_size']} bytes")
    print(f"Tables: {', '.join(result['tables'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

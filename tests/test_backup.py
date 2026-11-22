import sqlite3
from pathlib import Path

import pytest

from app.backup import (
    BackupError,
    create_database_backup,
    restore_database_backup,
    verify_backup,
)
from app.backup_crypto import KeyringError, create_keyring


def make_database(path: Path, *, users: int = 3, media: int = 2, audit: int = 5) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE "user" (id INTEGER PRIMARY KEY, username TEXT);
            CREATE TABLE media_file (uid TEXT PRIMARY KEY);
            CREATE TABLE audit_log (id INTEGER PRIMARY KEY, action TEXT);
            """
        )
        connection.executemany(
            'INSERT INTO "user" (id, username) VALUES (?, ?)',
            [(index, f"user{index}") for index in range(users)],
        )
        connection.executemany(
            "INSERT INTO media_file (uid) VALUES (?)",
            [(f"media{index}",) for index in range(media)],
        )
        connection.executemany(
            "INSERT INTO audit_log (action) VALUES (?)",
            [("login_success",) for _ in range(audit)],
        )
        connection.commit()
    finally:
        connection.close()


@pytest.fixture
def backup_env(tmp_path):
    db_path = tmp_path / "VKR_YOLO.db"
    make_database(db_path)
    keyring_path = tmp_path / "keys" / "backup-keyring.json"
    keyring = create_keyring(str(keyring_path))
    backup_dir = tmp_path / "backups"
    return {
        "db": str(db_path),
        "keyring": str(keyring_path),
        "keyring_data": keyring,
        "backup_dir": str(backup_dir),
    }


def test_backup_roundtrip_and_restore(backup_env):
    result = create_database_backup(
        backup_env["db"],
        backup_env["backup_dir"],
        backup_env["keyring"],
        keep_days=365,
    )
    assert Path(result["path"]).is_file()
    assert Path(result["path"]).read_bytes().startswith(b"VGAENC1\n")
    assert not list(Path(backup_env["backup_dir"]).glob("*.db"))

    verified = verify_backup(result["path"], backup_env["keyring"])
    assert {"user", "media_file", "audit_log"}.issubset(verified["tables"])

    connection = sqlite3.connect(backup_env["db"])
    connection.execute('DELETE FROM "user"')
    connection.commit()
    connection.close()

    restored = restore_database_backup(
        result["path"], backup_env["db"], backup_env["keyring"]
    )
    assert restored["counts"]["user"] == 3
    assert restored["counts"]["media_file"] == 2
    assert restored["counts"]["audit_log"] == 5
    assert restored["pre_restore_backup"]
    assert Path(restored["pre_restore_backup"]).is_file()


def test_tampered_backup_is_rejected(backup_env):
    result = create_database_backup(
        backup_env["db"],
        backup_env["backup_dir"],
        backup_env["keyring"],
        keep_days=365,
    )
    path = Path(result["path"])
    data = bytearray(path.read_bytes())
    data[-1] ^= 0x01
    path.write_bytes(data)

    with pytest.raises(BackupError):
        verify_backup(str(path), backup_env["keyring"])


def test_wrong_keyring_is_rejected(backup_env, tmp_path):
    result = create_database_backup(
        backup_env["db"],
        backup_env["backup_dir"],
        backup_env["keyring"],
        keep_days=365,
    )
    other_keyring = tmp_path / "other-keyring.json"
    create_keyring(str(other_keyring))
    with pytest.raises(KeyringError):
        verify_backup(result["path"], str(other_keyring))


def test_missing_keyring_prevents_backup(backup_env, tmp_path):
    missing = tmp_path / "missing-keyring.json"
    with pytest.raises(KeyringError):
        create_database_backup(
            backup_env["db"],
            backup_env["backup_dir"],
            str(missing),
            keep_days=365,
        )

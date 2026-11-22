"""AES-256-GCM helpers for encrypted VGA database backups."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import tempfile
from datetime import datetime, timezone

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

MAGIC = b"VGAENC1\n"
BACKUP_VERSION = 1
KEY_BYTES = 32
NONCE_BYTES = 12
TAG_BYTES = 16
_CHUNK_SIZE = 1024 * 1024
_MAX_HEADER_BYTES = 64 * 1024


class KeyringError(RuntimeError):
    """Raised when the backup keyring is missing or invalid."""


class BackupFormatError(RuntimeError):
    """Raised when an encrypted backup is malformed or fails authentication."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value.encode("ascii"))


def _atomic_write_text(path: str, text: str, mode: int = 0o600) -> None:
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    descriptor, temporary_path = tempfile.mkstemp(
        dir=directory, prefix=".vga-keyring.", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(text)
            output.flush()
            os.fsync(output.fileno())
        try:
            os.chmod(temporary_path, mode)
        except OSError:
            pass
        os.replace(temporary_path, path)
    except Exception:
        try:
            os.unlink(temporary_path)
        except OSError:
            pass
        raise


def create_keyring(path: str, *, key_id: str | None = None, overwrite: bool = False) -> dict:
    """Create a new keyring with one active 256-bit key."""
    if os.path.exists(path) and not overwrite:
        raise KeyringError(f"Keyring already exists: {path}")

    key_id = key_id or (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + "-"
        + secrets.token_hex(4)
    )
    key = secrets.token_bytes(KEY_BYTES)
    keyring = {
        "version": 1,
        "active_key_id": key_id,
        "keys": {key_id: _b64encode(key)},
        "created_at": _now(),
    }
    _atomic_write_text(path, json.dumps(keyring, ensure_ascii=False, indent=2) + "\n")
    return keyring


def load_keyring(path: str) -> dict:
    if not os.path.isfile(path):
        raise KeyringError(
            "Backup keyring not found. Create it with "
            f"`python tools/backup_db.py --init-keyring` ({path})"
        )
    try:
        with open(path, "r", encoding="utf-8") as keyring_file:
            keyring = json.load(keyring_file)
    except (OSError, json.JSONDecodeError) as exc:
        raise KeyringError("Unable to read the backup keyring") from exc

    if not isinstance(keyring, dict) or not isinstance(keyring.get("keys"), dict):
        raise KeyringError("Backup keyring has an invalid structure")
    active_key_id = str(keyring.get("active_key_id") or "").strip()
    if not active_key_id or active_key_id not in keyring["keys"]:
        raise KeyringError("Backup keyring has no active key")

    for key_id, encoded in keyring["keys"].items():
        try:
            key = _b64decode(str(encoded))
        except (ValueError, TypeError) as exc:
            raise KeyringError(f"Invalid key material for key {key_id!r}") from exc
        if len(key) != KEY_BYTES:
            raise KeyringError(f"Key {key_id!r} must be 32 bytes")
    return keyring


def active_key(keyring: dict) -> tuple[str, bytes]:
    key_id = str(keyring["active_key_id"])
    return key_id, _b64decode(keyring["keys"][key_id])


def _key_for_id(keyring: dict, key_id: str) -> bytes:
    try:
        encoded = keyring["keys"][key_id]
    except KeyError as exc:
        raise KeyringError(f"Backup key {key_id!r} is not in the keyring") from exc
    return _b64decode(str(encoded))


def _header_bytes(header: dict) -> bytes:
    return json.dumps(header, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )


def encrypt_file(source_path: str, destination_path: str, keyring: dict) -> dict:
    """Encrypt source_path into destination_path and return backup metadata."""
    key_id, key = active_key(keyring)
    original_size = os.path.getsize(source_path)
    original_sha256 = sha256_file(source_path)
    nonce = os.urandom(NONCE_BYTES)
    header = {
        "version": BACKUP_VERSION,
        "key_id": key_id,
        "nonce": _b64encode(nonce),
        "original_size": original_size,
        "sha256": original_sha256,
        "created_at": _now(),
    }
    header_bytes = _header_bytes(header)

    encryptor = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
    encryptor.authenticate_additional_data(header_bytes)

    os.makedirs(os.path.dirname(destination_path) or ".", exist_ok=True)
    descriptor, temporary_path = tempfile.mkstemp(
        dir=os.path.dirname(destination_path) or ".",
        prefix=".vga-backup.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(descriptor, "wb") as output, open(source_path, "rb") as source:
            output.write(MAGIC)
            output.write(header_bytes)
            output.write(b"\n")
            for chunk in iter(lambda: source.read(_CHUNK_SIZE), b""):
                output.write(encryptor.update(chunk))
            output.write(encryptor.finalize())
            output.write(encryptor.tag)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_path, destination_path)
    except Exception:
        try:
            os.unlink(temporary_path)
        except OSError:
            pass
        raise

    return {
        **header,
        "path": destination_path,
        "encrypted_size": os.path.getsize(destination_path),
    }


def read_header(path: str) -> dict:
    with open(path, "rb") as backup_file:
        magic = backup_file.read(len(MAGIC))
        if magic != MAGIC:
            raise BackupFormatError("Not a VGA encrypted backup")
        header_line = backup_file.readline(_MAX_HEADER_BYTES)
        if not header_line.endswith(b"\n"):
            raise BackupFormatError("Backup header is too large or truncated")
    try:
        header = json.loads(header_line.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BackupFormatError("Backup header is invalid") from exc
    if not isinstance(header, dict) or header.get("version") != BACKUP_VERSION:
        raise BackupFormatError("Unsupported backup format")
    return header


def decrypt_file(
    source_path: str,
    destination_path: str,
    keyring: dict,
    *,
    expected_sha256: str | None = None,
) -> dict:
    """Decrypt and authenticate a backup into destination_path."""
    with open(source_path, "rb") as source:
        if source.read(len(MAGIC)) != MAGIC:
            raise BackupFormatError("Not a VGA encrypted backup")
        header_line = source.readline(_MAX_HEADER_BYTES)
        if not header_line.endswith(b"\n"):
            raise BackupFormatError("Backup header is too large or truncated")
        header = json.loads(header_line.decode("utf-8"))
        if not isinstance(header, dict) or header.get("version") != BACKUP_VERSION:
            raise BackupFormatError("Unsupported backup format")

        header_bytes = header_line[:-1]
        key_id = str(header.get("key_id") or "")
        key = _key_for_id(keyring, key_id)
        try:
            nonce = _b64decode(str(header["nonce"]))
        except (KeyError, ValueError, TypeError) as exc:
            raise BackupFormatError("Backup nonce is invalid") from exc
        if len(nonce) != NONCE_BYTES:
            raise BackupFormatError("Backup nonce has the wrong size")

        source.seek(0, os.SEEK_END)
        file_size = source.tell()
        ciphertext_size = file_size - len(MAGIC) - len(header_line) - TAG_BYTES
        if ciphertext_size < 0:
            raise BackupFormatError("Backup is truncated")
        source.seek(file_size - TAG_BYTES)
        tag = source.read(TAG_BYTES)
        source.seek(len(MAGIC) + len(header_line))

        decryptor = Cipher(algorithms.AES(key), modes.GCM(nonce, tag)).decryptor()
        decryptor.authenticate_additional_data(header_bytes)

        descriptor, temporary_path = tempfile.mkstemp(
            dir=os.path.dirname(destination_path) or ".",
            prefix=".vga-restore.",
            suffix=".tmp",
        )
        digest = hashlib.sha256()
        written = 0
        try:
            with os.fdopen(descriptor, "wb") as output:
                remaining = ciphertext_size
                while remaining:
                    chunk = source.read(min(_CHUNK_SIZE, remaining))
                    if not chunk:
                        raise BackupFormatError("Backup is truncated")
                    remaining -= len(chunk)
                    plaintext = decryptor.update(chunk)
                    digest.update(plaintext)
                    written += len(plaintext)
                    output.write(plaintext)
                try:
                    output.write(decryptor.finalize())
                except InvalidTag as exc:
                    raise BackupFormatError("Backup authentication failed") from exc
                output.flush()
                os.fsync(output.fileno())

            if written != int(header.get("original_size", -1)):
                raise BackupFormatError("Restored file has an unexpected size")
            actual_sha256 = digest.hexdigest()
            expected = str(header.get("sha256") or "").lower()
            if expected_sha256 is not None:
                expected = str(expected_sha256).lower()
            if not hmac.compare_digest(actual_sha256, expected):
                raise BackupFormatError("Restored file failed SHA-256 verification")

            os.replace(temporary_path, destination_path)
        except Exception:
            try:
                os.unlink(temporary_path)
            except OSError:
                pass
            raise

    return {
        **header,
        "path": destination_path,
        "restored_size": written,
        "restored_sha256": actual_sha256,
    }

"""SHA-256 integrity checks for YOLO model weights.

The manifest in ``app/model_hashes.json`` is the trusted reference. A weight
file must be verified before Ultralytics/PyTorch loads it, because ``.pt`` files
are pickles and can execute code during deserialization.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading

DEFAULT_MANIFEST_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "model_hashes.json"
)
_CHUNK_SIZE = 1024 * 1024
_VERIFIED_CACHE: dict[str, tuple[tuple[int, int, str], str]] = {}
_CACHE_LOCK = threading.Lock()


class ModelIntegrityError(RuntimeError):
    """Raised when a model is missing, has the wrong size or fails SHA-256."""


class ModelManifestError(RuntimeError):
    """Raised when the trusted model manifest is malformed."""


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as weights:
        for chunk in iter(lambda: weights.read(_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_manifest_entry(filename: str, entry: object) -> None:
    if not isinstance(entry, dict):
        raise ModelManifestError(f"Manifest entry for {filename!r} is not an object")
    if (
        not filename.endswith(".pt")
        or os.path.basename(filename) != filename
        or "/" in filename
        or "\\" in filename
    ):
        raise ModelManifestError(f"Invalid model filename in manifest: {filename!r}")

    digest = str(entry.get("sha256") or "").strip().lower()
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ModelManifestError(f"Invalid SHA-256 for {filename!r}")

    try:
        size = int(entry.get("size"))
    except (TypeError, ValueError) as exc:
        raise ModelManifestError(f"Invalid size for {filename!r}") from exc
    if size <= 0:
        raise ModelManifestError(f"Invalid size for {filename!r}")

    url = str(entry.get("url") or "").strip()
    if not url.startswith("https://"):
        raise ModelManifestError(f"Model URL for {filename!r} must use HTTPS")


def load_manifest(path: str | None = None) -> dict:
    manifest_path = path or DEFAULT_MANIFEST_PATH
    try:
        with open(manifest_path, "r", encoding="utf-8") as manifest_file:
            data = json.load(manifest_file)
    except (OSError, json.JSONDecodeError) as exc:
        raise ModelManifestError("Unable to read the trusted model manifest") from exc

    if not isinstance(data, dict) or not data:
        raise ModelManifestError("The model manifest is empty or invalid")

    for filename, entry in data.items():
        _validate_manifest_entry(filename, entry)
    return data


def verify_model_file(
    path: str,
    expected_sha256: str,
    expected_size: int | None = None,
    *,
    use_cache: bool = True,
) -> str:
    """Return the verified digest or raise ModelIntegrityError."""
    absolute_path = os.path.abspath(path)
    if not os.path.isfile(absolute_path):
        raise ModelIntegrityError(f"Model file is missing: {os.path.basename(path)}")

    stat = os.stat(absolute_path)
    if expected_size is not None and stat.st_size != int(expected_size):
        raise ModelIntegrityError(
            f"Model size mismatch: {os.path.basename(path)}"
        )

    expected = str(expected_sha256 or "").strip().lower()
    if len(expected) != 64:
        raise ModelIntegrityError("Invalid expected SHA-256 value")

    cache_key = (stat.st_size, stat.st_mtime_ns, expected)
    if use_cache:
        with _CACHE_LOCK:
            cached = _VERIFIED_CACHE.get(absolute_path)
        if cached is not None and cached[0] == cache_key:
            return cached[1]

    actual = sha256_file(absolute_path)
    if not hmac.compare_digest(actual, expected):
        raise ModelIntegrityError(
            f"Model integrity check failed: {os.path.basename(path)}"
        )

    if use_cache:
        with _CACHE_LOCK:
            _VERIFIED_CACHE[absolute_path] = (cache_key, actual)
    return actual


def clear_verification_cache() -> None:
    with _CACHE_LOCK:
        _VERIFIED_CACHE.clear()

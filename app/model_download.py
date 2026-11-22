"""Download official YOLO weights from the trusted manifest.

Only manifest entries are accepted. The file is written to a staging directory,
hashed while downloading, and atomically moved into place only after SHA-256
matches the trusted value.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import stat
import tempfile
import threading
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from flask import current_app

from app.model_integrity import (
    ModelManifestError,
    clear_verification_cache,
    load_manifest,
)
from app.model_registry import ModelRegistryError, resolve_model_path

ALLOWED_DOWNLOAD_HOSTS = {
    "github.com",
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
}
_CHUNK_SIZE = 1024 * 1024
_DOWNLOAD_LOCK = threading.Lock()


class ModelDownloadError(RuntimeError):
    """Raised when an official model cannot be downloaded safely."""


def _validate_download_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_DOWNLOAD_HOSTS:
        raise ModelDownloadError("Model URL is not from an allowed HTTPS host")


def _open_url(url: str, timeout: int):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "VGA-model-loader/1.0"},
    )
    return urllib.request.urlopen(request, timeout=timeout)


def _make_writable(path: str) -> None:
    if os.path.exists(path):
        try:
            os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
        except OSError:
            pass


def _make_read_only(path: str) -> None:
    try:
        os.chmod(path, stat.S_IREAD)
    except OSError:
        current_app.logger.warning("Could not mark model file read-only: %s", path)


def download_official_model(filename: str) -> dict:
    """Download, verify and install one official model.

    The registry is not modified here; the caller verifies/enables the entry.
    """
    manifest = load_manifest(current_app.config["MODEL_MANIFEST_PATH"])
    entry = manifest.get(filename)
    if entry is None:
        raise ModelDownloadError("Model is not in the trusted manifest")

    _validate_download_url(entry["url"])
    expected_size = int(entry["size"])
    expected_sha256 = str(entry["sha256"]).lower()
    max_bytes = int(current_app.config.get("MODEL_DOWNLOAD_MAX_BYTES", 512 * 1024 * 1024))
    if expected_size > max_bytes:
        raise ModelDownloadError("Model exceeds the configured download limit")

    models_dir = os.path.abspath(current_app.config["YOLO_MODELS_DIR"])
    staging_dir = os.path.join(models_dir, ".staging")
    os.makedirs(staging_dir, exist_ok=True)
    target_path = resolve_model_path(filename)
    timeout = max(1, int(current_app.config.get("MODEL_DOWNLOAD_TIMEOUT_SECONDS", 600)))

    descriptor, temporary_path = tempfile.mkstemp(
        dir=staging_dir, prefix=f"{filename}.", suffix=".part"
    )
    os.close(descriptor)
    written = 0
    digest = hashlib.sha256()

    try:
        with _DOWNLOAD_LOCK:
            with _open_url(entry["url"], timeout) as response:
                final_url = response.geturl()
                _validate_download_url(final_url)

                content_length = response.headers.get("Content-Length")
                if content_length is not None:
                    try:
                        advertised_size = int(content_length)
                    except (TypeError, ValueError):
                        advertised_size = None
                    if advertised_size is not None and advertised_size > expected_size:
                        raise ModelDownloadError("Downloaded file is larger than expected")

                with open(temporary_path, "wb") as output:
                    while True:
                        chunk = response.read(_CHUNK_SIZE)
                        if not chunk:
                            break
                        written += len(chunk)
                        if written > expected_size:
                            raise ModelDownloadError(
                                "Downloaded file is larger than expected"
                            )
                        digest.update(chunk)
                        output.write(chunk)
                    output.flush()
                    os.fsync(output.fileno())

        if written != expected_size:
            raise ModelDownloadError("Downloaded file has an unexpected size")

        actual_sha256 = digest.hexdigest()
        if not hmac.compare_digest(actual_sha256, expected_sha256):
            raise ModelDownloadError("Downloaded model failed SHA-256 verification")

        _make_writable(target_path)
        os.replace(temporary_path, target_path)
        temporary_path = ""
        _make_read_only(target_path)
        clear_verification_cache()
        current_app.logger.info("Installed verified YOLO model: %s", target_path)
        return {
            "filename": filename,
            "size": written,
            "sha256": actual_sha256,
            "path": target_path,
        }
    except ModelDownloadError:
        raise
    except (ModelManifestError, ModelRegistryError, OSError, urllib.error.URLError) as exc:
        raise ModelDownloadError("Unable to download the model") from exc
    except Exception as exc:
        raise ModelDownloadError("Unable to download the model") from exc
    finally:
        if temporary_path:
            try:
                os.unlink(temporary_path)
            except OSError:
                pass

"""JSON registry of available YOLO models.

This deliberately does not touch SQLite: the project keeps model metadata in
``app/instance/models_registry.json`` while the trusted hashes stay in the
versioned ``app/model_hashes.json`` manifest.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime, timezone

from flask import current_app

from app.model_integrity import (
    DEFAULT_MANIFEST_PATH,
    ModelIntegrityError,
    load_manifest,
    verify_model_file,
)

REGISTRY_FILENAME = "models_registry.json"
REGISTRY_VERSION = 1
MODEL_ORDER = (
    "yolov8n.pt",
    "yolov8s.pt",
    "yolov8m.pt",
    "yolov8l.pt",
    "yolov8x.pt",
)
_DEFAULT_DISPLAY_NAMES = {
    "yolov8n.pt": "YOLOv8 Nano",
    "yolov8s.pt": "YOLOv8 Small",
    "yolov8m.pt": "YOLOv8 Medium",
    "yolov8l.pt": "YOLOv8 Large",
    "yolov8x.pt": "YOLOv8 X-Large",
}
_REGISTRY_LOCK = threading.RLock()


class ModelRegistryError(RuntimeError):
    """Raised when the model registry is invalid or unsafe."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _models_dir() -> str:
    return os.path.abspath(current_app.config["YOLO_MODELS_DIR"])


def _manifest_path() -> str:
    return current_app.config.get("MODEL_MANIFEST_PATH") or DEFAULT_MANIFEST_PATH


def _registry_path() -> str:
    return current_app.config.get("MODEL_REGISTRY_PATH") or os.path.join(
        current_app.instance_path, REGISTRY_FILENAME
    )


def resolve_model_path(relative_path: str) -> str:
    """Resolve a registry path and reject traversal outside YOLO_MODELS_DIR."""
    relative_path = str(relative_path or "").strip()
    if not relative_path:
        raise ModelRegistryError("Empty model path")

    models_dir = _models_dir()
    absolute_path = os.path.abspath(os.path.join(models_dir, relative_path))
    try:
        common = os.path.commonpath([models_dir, absolute_path])
    except ValueError as exc:
        raise ModelRegistryError("Invalid model path") from exc
    if common != models_dir:
        raise ModelRegistryError("Model path escapes the models directory")
    return absolute_path


def _display_name(filename: str, manifest_entry: dict) -> str:
    return str(
        manifest_entry.get("display_name")
        or _DEFAULT_DISPLAY_NAMES.get(filename)
        or filename
    )


def _new_entry(
    filename: str,
    manifest_entry: dict,
    *,
    enabled: bool,
    status: str,
    last_verified: str | None = None,
) -> dict:
    return {
        "path": filename,
        "display_name": _display_name(filename, manifest_entry),
        "sha256": manifest_entry["sha256"],
        "size": manifest_entry["size"],
        "enabled": enabled,
        "status": status,
        "last_verified": last_verified,
        "trust": "official",
    }


def _bootstrap_registry(manifest: dict) -> dict:
    models = {}
    for filename, manifest_entry in manifest.items():
        path = resolve_model_path(filename)
        if not os.path.isfile(path):
            models[filename] = _new_entry(
                filename, manifest_entry, enabled=False, status="missing"
            )
            continue

        try:
            verify_model_file(
                path,
                manifest_entry["sha256"],
                manifest_entry["size"],
                use_cache=False,
            )
        except ModelIntegrityError:
            models[filename] = _new_entry(
                filename, manifest_entry, enabled=False, status="hash_failed"
            )
        else:
            models[filename] = _new_entry(
                filename,
                manifest_entry,
                enabled=True,
                status="verified",
                last_verified=_now(),
            )
    return {"version": REGISTRY_VERSION, "models": models}


def _load_registry_file(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as registry_file:
            data = json.load(registry_file)
    except (OSError, json.JSONDecodeError) as exc:
        raise ModelRegistryError("Unable to read the model registry") from exc

    if not isinstance(data, dict) or not isinstance(data.get("models"), dict):
        raise ModelRegistryError("The model registry has an invalid structure")
    return data


def _atomic_write_registry(registry: dict) -> None:
    path = _registry_path()
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)

    descriptor, temporary_path = tempfile.mkstemp(
        dir=directory, prefix=".models_registry.", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as registry_file:
            json.dump(registry, registry_file, ensure_ascii=False, indent=2)
            registry_file.write("\n")
            registry_file.flush()
            os.fsync(registry_file.fileno())
        os.replace(temporary_path, path)
    except Exception:
        try:
            os.unlink(temporary_path)
        except OSError:
            pass
        raise


def save_registry(registry: dict) -> None:
    with _REGISTRY_LOCK:
        _atomic_write_registry(registry)


def load_registry(*, refresh_status: bool = False) -> dict:
    """Load, bootstrap or extend the registry without changing SQLite."""
    with _REGISTRY_LOCK:
        manifest = load_manifest(_manifest_path())
        path = _registry_path()
        changed = False

        if os.path.isfile(path):
            registry = _load_registry_file(path)
            registry.setdefault("version", REGISTRY_VERSION)
        else:
            registry = _bootstrap_registry(manifest)
            changed = True

        models = registry["models"]
        for filename, manifest_entry in manifest.items():
            if filename not in models or not isinstance(models[filename], dict):
                entry = _new_entry(
                    filename, manifest_entry, enabled=False, status="missing"
                )
                file_path = resolve_model_path(filename)
                if os.path.isfile(file_path):
                    try:
                        verify_model_file(
                            file_path,
                            manifest_entry["sha256"],
                            manifest_entry["size"],
                            use_cache=False,
                        )
                    except ModelIntegrityError:
                        entry["status"] = "hash_failed"
                    else:
                        entry["enabled"] = True
                        entry["status"] = "verified"
                        entry["last_verified"] = _now()
                models[filename] = entry
                changed = True
                continue

            entry = models[filename]
            # Official hashes and sizes always come from the versioned manifest.
            if entry.get("sha256") != manifest_entry["sha256"]:
                entry["sha256"] = manifest_entry["sha256"]
                changed = True
            if entry.get("size") != manifest_entry["size"]:
                entry["size"] = manifest_entry["size"]
                changed = True
            if not entry.get("display_name"):
                entry["display_name"] = _display_name(filename, manifest_entry)
                changed = True
            entry.setdefault("enabled", False)
            entry.setdefault("status", "missing")
            entry.setdefault("trust", "official")
            entry.setdefault("last_verified", None)
            entry.setdefault("path", filename)

        if refresh_status:
            _refresh_statuses(registry, manifest)
            changed = True

        if changed:
            _atomic_write_registry(registry)
        return registry


def _refresh_statuses(registry: dict, manifest: dict) -> None:
    for filename, entry in registry["models"].items():
        manifest_entry = manifest.get(filename)
        if not manifest_entry:
            entry["status"] = "not_in_manifest"
            continue
        path = resolve_model_path(entry.get("path", filename))
        if not os.path.isfile(path):
            entry["status"] = "missing"
            continue
        try:
            verify_model_file(
                path,
                manifest_entry["sha256"],
                manifest_entry["size"],
            )
        except ModelIntegrityError:
            entry["status"] = "hash_failed"
        else:
            entry["status"] = "verified"
            entry["last_verified"] = _now()


def get_model_entry(filename: str) -> dict:
    """Return a verified, enabled model or raise ModelIntegrityError."""
    registry = load_registry()
    entry = registry["models"].get(filename)
    if not entry:
        raise ModelIntegrityError("Unknown model")
    if not entry.get("enabled"):
        raise ModelIntegrityError("Model is disabled")

    manifest = load_manifest(_manifest_path())
    manifest_entry = manifest.get(filename)
    if not manifest_entry:
        raise ModelIntegrityError("Model is not in the trusted manifest")

    path = resolve_model_path(entry.get("path", filename))
    verify_model_file(path, manifest_entry["sha256"], manifest_entry["size"])
    return {
        **entry,
        "filename": filename,
        "absolute_path": path,
        "sha256": manifest_entry["sha256"],
        "size": manifest_entry["size"],
        "display_name": entry.get("display_name")
        or _display_name(filename, manifest_entry),
    }


def available_models() -> list[dict]:
    """Models shown to regular users: enabled, present and SHA-256 verified."""
    registry = load_registry()
    result = []
    for filename in sorted(
        registry["models"],
        key=lambda name: (
            MODEL_ORDER.index(name) if name in MODEL_ORDER else len(MODEL_ORDER),
            name,
        ),
    ):
        entry = registry["models"][filename]
        if not entry.get("enabled"):
            continue
        try:
            model = get_model_entry(filename)
        except (ModelIntegrityError, ModelRegistryError):
            continue
        result.append(
            {
                "filename": filename,
                "display_name": model["display_name"],
                "size": model["size"],
            }
        )
    return result


def get_admin_models(*, refresh_status: bool = True) -> list[dict]:
    registry = load_registry(refresh_status=refresh_status)
    manifest = load_manifest(_manifest_path())
    result = []
    for filename in sorted(
        registry["models"],
        key=lambda name: (
            MODEL_ORDER.index(name) if name in MODEL_ORDER else len(MODEL_ORDER),
            name,
        ),
    ):
        entry = dict(registry["models"][filename])
        entry["filename"] = filename
        entry["official"] = filename in manifest
        result.append(entry)
    return result


def verify_registry_entry(filename: str) -> dict:
    with _REGISTRY_LOCK:
        registry = load_registry()
        entry = registry["models"].get(filename)
        if entry is None:
            raise ModelRegistryError("Unknown model")
        manifest_entry = load_manifest(_manifest_path()).get(filename)
        if manifest_entry is None:
            raise ModelRegistryError("Model is not in the trusted manifest")

        path = resolve_model_path(entry.get("path", filename))
        try:
            verify_model_file(
                path,
                manifest_entry["sha256"],
                manifest_entry["size"],
                use_cache=False,
            )
        except ModelIntegrityError:
            entry["status"] = "hash_failed"
        else:
            entry["status"] = "verified"
            entry["last_verified"] = _now()
        _atomic_write_registry(registry)
        return dict(entry)


def set_model_enabled(filename: str, enabled: bool) -> dict:
    with _REGISTRY_LOCK:
        registry = load_registry()
        entry = registry["models"].get(filename)
        if entry is None:
            raise ModelRegistryError("Unknown model")

        if enabled:
            manifest_entry = load_manifest(_manifest_path()).get(filename)
            if manifest_entry is None:
                raise ModelRegistryError("Model is not in the trusted manifest")
            path = resolve_model_path(entry.get("path", filename))
            verify_model_file(
                path,
                manifest_entry["sha256"],
                manifest_entry["size"],
            )
            entry["status"] = "verified"
            entry["last_verified"] = _now()

        entry["enabled"] = bool(enabled)
        _atomic_write_registry(registry)
        return dict(entry)

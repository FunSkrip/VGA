import hashlib
import json

import pytest
from flask import Flask

from app.model_integrity import (
    ModelIntegrityError,
    ModelManifestError,
    load_manifest,
    verify_model_file,
)
from app.model_registry import (
    ModelRegistryError,
    available_models,
    get_model_entry,
    load_registry,
    resolve_model_path,
    set_model_enabled,
    verify_registry_entry,
)


@pytest.fixture
def model_app(tmp_path):
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    model_bytes = b"fake yolo weights for tests"
    model_path = models_dir / "yolov8n.pt"
    model_path.write_bytes(model_bytes)

    manifest = {
        "yolov8n.pt": {
            "display_name": "YOLOv8 Nano",
            "sha256": hashlib.sha256(model_bytes).hexdigest(),
            "size": len(model_bytes),
            "url": "https://example.invalid/yolov8n.pt",
        }
    }
    manifest_path = tmp_path / "model_hashes.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    app = Flask(__name__)
    app.config.update(
        YOLO_MODELS_DIR=str(models_dir),
        MODEL_MANIFEST_PATH=str(manifest_path),
        MODEL_REGISTRY_PATH=str(tmp_path / "models_registry.json"),
    )
    return app, model_path, model_bytes


def test_verify_model_file_success_and_failure(model_app):
    _app, model_path, model_bytes = model_app
    expected = hashlib.sha256(model_bytes).hexdigest()
    assert verify_model_file(model_path, expected) == expected
    with pytest.raises(ModelIntegrityError):
        verify_model_file(model_path, "0" * 64)
    with pytest.raises(ModelIntegrityError):
        verify_model_file(str(model_path) + ".missing", expected)


def test_manifest_rejects_invalid_hash(tmp_path):
    manifest_path = tmp_path / "bad.json"
    manifest_path.write_text(
        json.dumps(
            {
                "yolov8n.pt": {
                    "sha256": "not-a-hash",
                    "size": 1,
                    "url": "https://example.invalid/model.pt",
                }
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ModelManifestError):
        load_manifest(str(manifest_path))


def test_registry_bootstraps_and_toggles_model(model_app):
    app, _model_path, _model_bytes = model_app
    with app.app_context():
        registry = load_registry()
        entry = registry["models"]["yolov8n.pt"]
        assert entry["enabled"] is True
        assert entry["status"] == "verified"
        assert [m["filename"] for m in available_models()] == ["yolov8n.pt"]

        set_model_enabled("yolov8n.pt", False)
        assert available_models() == []

        set_model_enabled("yolov8n.pt", True)
        assert get_model_entry("yolov8n.pt")["display_name"] == "YOLOv8 Nano"


def test_tampered_model_is_hidden_and_cannot_be_enabled(model_app):
    app, model_path, _model_bytes = model_app
    with app.app_context():
        load_registry()
        model_path.write_bytes(b"tampered")
        entry = verify_registry_entry("yolov8n.pt")
        assert entry["status"] == "hash_failed"
        assert available_models() == []
        with pytest.raises(ModelIntegrityError):
            set_model_enabled("yolov8n.pt", True)


def test_registry_rejects_path_traversal(model_app):
    app, _model_path, _model_bytes = model_app
    with app.app_context():
        with pytest.raises(ModelRegistryError):
            resolve_model_path("../outside.pt")

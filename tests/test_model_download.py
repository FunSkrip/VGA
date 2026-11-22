import hashlib
import io
import json

import pytest
from flask import Flask

from app.model_download import ModelDownloadError, download_official_model
from app.model_registry import load_registry


class FakeResponse:
    def __init__(self, payload: bytes, final_url: str):
        self._stream = io.BytesIO(payload)
        self.headers = {"Content-Length": str(len(payload))}
        self._final_url = final_url

    def read(self, size=-1):
        return self._stream.read(size)

    def geturl(self):
        return self._final_url

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


def make_app(tmp_path, payload: bytes):
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    manifest = {
        "yolov8n.pt": {
            "display_name": "YOLOv8 Nano",
            "sha256": hashlib.sha256(payload).hexdigest(),
            "size": len(payload),
            "url": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt",
        }
    }
    manifest_path = tmp_path / "model_hashes.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    app = Flask(__name__)
    app.config.update(
        YOLO_MODELS_DIR=str(models_dir),
        MODEL_MANIFEST_PATH=str(manifest_path),
        MODEL_REGISTRY_PATH=str(tmp_path / "models_registry.json"),
        MODEL_DOWNLOAD_TIMEOUT_SECONDS=30,
        MODEL_DOWNLOAD_MAX_BYTES=1024 * 1024,
    )
    return app, models_dir / "yolov8n.pt"


def test_download_verifies_and_installs_model(tmp_path, monkeypatch):
    payload = b"official model bytes"
    app, target = make_app(tmp_path, payload)

    def fake_open_url(url, timeout):
        return FakeResponse(payload, url)

    monkeypatch.setattr("app.model_download._open_url", fake_open_url)

    with app.app_context():
        result = download_official_model("yolov8n.pt")
        assert result["sha256"] == hashlib.sha256(payload).hexdigest()
        assert target.read_bytes() == payload
        registry = load_registry()
        assert registry["models"]["yolov8n.pt"]["status"] == "verified"


def test_download_rejects_tampered_payload(tmp_path, monkeypatch):
    expected = b"expected bytes"
    app, target = make_app(tmp_path, expected)

    def fake_open_url(url, timeout):
        return FakeResponse(b"tampered bytes", url)

    monkeypatch.setattr("app.model_download._open_url", fake_open_url)

    with app.app_context():
        with pytest.raises(ModelDownloadError):
            download_official_model("yolov8n.pt")
        assert not target.exists()


def test_download_rejects_unknown_model(tmp_path):
    app, _target = make_app(tmp_path, b"payload")
    with app.app_context():
        with pytest.raises(ModelDownloadError):
            download_official_model("unknown.pt")

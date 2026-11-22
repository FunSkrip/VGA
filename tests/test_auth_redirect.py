from flask import Flask

from app.routes.auth import _safe_next_url


def test_relative_next_url_is_allowed():
    app = Flask(__name__)
    with app.test_request_context("/login"):
        assert _safe_next_url("/analysis?model=yolov8n.pt") == "/analysis?model=yolov8n.pt"


def test_same_origin_absolute_url_is_allowed():
    app = Flask(__name__)
    with app.test_request_context("/login"):
        assert _safe_next_url("http://localhost/media/abc") == "/media/abc"


def test_external_next_url_is_rejected():
    app = Flask(__name__)
    with app.test_request_context("/login"):
        assert _safe_next_url("https://evil.example/steal") is None
        assert _safe_next_url("//evil.example/steal") is None


def test_login_and_register_targets_are_rejected():
    app = Flask(__name__)
    with app.test_request_context("/login"):
        assert _safe_next_url("/login") is None
        assert _safe_next_url("/register") is None

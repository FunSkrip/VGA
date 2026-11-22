from datetime import timedelta

import pytest
from flask import Flask

from app.config_validation import (
    ConfigurationError,
    DEV_SECRET_KEY,
    validate_runtime_config,
)


def make_app(tmp_path, **overrides):
    app = Flask(__name__)
    app.config.update(
        APP_ENV="development",
        SECRET_KEY="x" * 48,
        SESSION_COOKIE_SECURE=False,
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=timedelta(minutes=30),
        WTF_CSRF_TIME_LIMIT=timedelta(minutes=30),
        UPLOAD_FOLDER=str(tmp_path / "processed"),
        GEMINI_API_KEY=None,
        TRUSTED_HOSTS=None,
    )
    app.config.update(overrides)
    return app


def test_production_requires_secret_key(tmp_path):
    app = make_app(tmp_path, APP_ENV="production", SECRET_KEY=None)
    with pytest.raises(ConfigurationError):
        validate_runtime_config(app)


def test_production_rejects_short_secret_key(tmp_path):
    app = make_app(tmp_path, APP_ENV="production", SECRET_KEY="short")
    with pytest.raises(ConfigurationError):
        validate_runtime_config(app)


def test_production_requires_secure_session_cookie(tmp_path):
    app = make_app(
        tmp_path,
        APP_ENV="production",
        SECRET_KEY="x" * 48,
        SESSION_COOKIE_SECURE=False,
    )
    with pytest.raises(ConfigurationError):
        validate_runtime_config(app)


def test_development_sets_fallback_secret_key(tmp_path):
    app = make_app(tmp_path, SECRET_KEY=None)
    validate_runtime_config(app)
    assert app.config["SECRET_KEY"] == DEV_SECRET_KEY


def test_invalid_samesite_is_rejected(tmp_path):
    app = make_app(tmp_path, SESSION_COOKIE_SAMESITE="Invalid")
    with pytest.raises(ConfigurationError):
        validate_runtime_config(app)


def test_upload_folder_inside_static_is_rejected(tmp_path):
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    app = make_app(tmp_path, UPLOAD_FOLDER=str(static_dir / "processed"))
    app.static_folder = str(static_dir)
    with pytest.raises(ConfigurationError):
        validate_runtime_config(app)


def test_valid_development_config_passes(tmp_path):
    app = make_app(tmp_path)
    validate_runtime_config(app)
    assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"

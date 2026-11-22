"""Fail-fast checks for security-sensitive Flask configuration.

The application must not start in production with a missing/weak SECRET_KEY,
insecure session cookies or private media stored below the public static root.
"""
from __future__ import annotations

import os

from flask import Flask

DEV_SECRET_KEY = "dev-only-insecure-secret-key-change-me"
MIN_SECRET_KEY_BYTES = 32
VALID_SAMESITE = {"Lax", "Strict", "None"}


class ConfigurationError(RuntimeError):
    """Raised when the runtime configuration would weaken VGA security."""


def is_production(app: Flask) -> bool:
    return str(app.config.get("APP_ENV", "")).lower() in {"production", "prod"}


def _validate_secret_key(app: Flask) -> None:
    secret = str(app.config.get("SECRET_KEY") or "").strip()
    production = is_production(app)

    if production:
        if not secret:
            raise ConfigurationError(
                "SECRET_KEY is required in production (set it in the environment)"
            )
        if secret == DEV_SECRET_KEY:
            raise ConfigurationError(
                "The development SECRET_KEY must not be used in production"
            )
        if len(secret.encode("utf-8")) < MIN_SECRET_KEY_BYTES:
            raise ConfigurationError(
                f"SECRET_KEY must contain at least {MIN_SECRET_KEY_BYTES} bytes"
            )
        return

    if not secret:
        app.config["SECRET_KEY"] = DEV_SECRET_KEY
        app.logger.warning(
            "SECRET_KEY is not set; using an insecure development-only value"
        )
    elif len(secret.encode("utf-8")) < MIN_SECRET_KEY_BYTES:
        app.logger.warning(
            "Development SECRET_KEY is shorter than %s bytes",
            MIN_SECRET_KEY_BYTES,
        )


def _validate_session_cookies(app: Flask) -> None:
    production = is_production(app)
    samesite = str(app.config.get("SESSION_COOKIE_SAMESITE") or "Lax").capitalize()
    if samesite not in VALID_SAMESITE:
        raise ConfigurationError(
            "SESSION_COOKIE_SAMESITE must be one of Lax, Strict or None"
        )
    app.config["SESSION_COOKIE_SAMESITE"] = samesite

    secure = bool(app.config.get("SESSION_COOKIE_SECURE"))
    if production and not secure:
        raise ConfigurationError(
            "SESSION_COOKIE_SECURE must be enabled in production"
        )
    if samesite == "None" and not secure:
        raise ConfigurationError(
            "SESSION_COOKIE_SAMESITE=None requires SESSION_COOKIE_SECURE=True"
        )


def _validate_lifetimes(app: Flask) -> None:
    session_lifetime = app.config.get("PERMANENT_SESSION_LIFETIME")
    if session_lifetime is None or session_lifetime.total_seconds() <= 0:
        raise ConfigurationError("PERMANENT_SESSION_LIFETIME must be positive")

    csrf_lifetime = app.config.get("WTF_CSRF_TIME_LIMIT")
    if csrf_lifetime is not None:
        if hasattr(csrf_lifetime, "total_seconds"):
            csrf_seconds = csrf_lifetime.total_seconds()
        else:
            try:
                csrf_seconds = float(csrf_lifetime)
            except (TypeError, ValueError) as exc:
                raise ConfigurationError(
                    "WTF_CSRF_TIME_LIMIT must be a number of seconds"
                ) from exc
        if csrf_seconds <= 0:
            raise ConfigurationError("WTF_CSRF_TIME_LIMIT must be positive")


def _validate_private_storage(app: Flask) -> None:
    upload_folder = os.path.abspath(app.config["UPLOAD_FOLDER"])
    static_folder = os.path.abspath(app.static_folder or "")
    try:
        inside_static = os.path.commonpath([upload_folder, static_folder]) == static_folder
    except ValueError:
        inside_static = False
    if inside_static:
        raise ConfigurationError(
            "UPLOAD_FOLDER must not be inside the public static folder"
        )


def validate_runtime_config(app: Flask) -> None:
    """Validate configuration before SQLAlchemy, Flask-Login or requests run."""
    _validate_secret_key(app)
    _validate_session_cookies(app)
    _validate_lifetimes(app)
    _validate_private_storage(app)

    if not app.config.get("GEMINI_API_KEY"):
        app.logger.warning(
            "GEMINI_API_KEY is not configured; the support chatbot will be disabled"
        )

    if is_production(app) and not app.config.get("TRUSTED_HOSTS"):
        app.logger.warning(
            "TRUSTED_HOSTS is empty; configure the production host names"
        )

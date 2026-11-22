import os
from datetime import timedelta

from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, "app", "instance")

load_dotenv()


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return max(minimum, int(value))
    except (TypeError, ValueError):
        return default


def _env_list(name: str) -> tuple[str, ...]:
    value = os.getenv(name)
    if not value:
        return ()
    return tuple(part.strip() for part in value.split(",") if part.strip())


class Config:
    APP_ENV = (os.getenv("APP_ENV") or "development").strip().lower()
    IS_PRODUCTION = APP_ENV in {"production", "prod"}

    # Secrets are loaded from the environment. Production startup refuses weak
    # or missing values in app.config_validation.
    SECRET_KEY = (os.getenv("SECRET_KEY") or "").strip() or None
    # Flask 3.1 supports validating old session signatures during key rotation.
    SECRET_KEY_FALLBACKS = _env_list("SECRET_KEY_FALLBACKS")
    GEMINI_API_KEY = (
        os.getenv("GEMINI_API_KEY") or os.getenv("gemini_api_key") or ""
    ).strip() or None

    SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(
        INSTANCE_DIR, "VKR_YOLO.db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Private media must stay outside app/static. create_app also enforces this.
    UPLOAD_FOLDER = os.path.join(INSTANCE_DIR, "processed")
    YOLO_MODELS_DIR = os.path.join(BASE_DIR, "models")
    MODEL_MANIFEST_PATH = os.path.join(BASE_DIR, "app", "model_hashes.json")
    MODEL_REGISTRY_PATH = os.path.join(INSTANCE_DIR, "models_registry.json")

    MAX_CONTENT_LENGTH = 250 * 1024 * 1024

    # Signed session and CSRF tokens expire after 30 minutes of inactivity by
    # default. Set SESSION_LIFETIME_MINUTES/CSRF_TIME_LIMIT_MINUTES to change.
    PERMANENT_SESSION_LIFETIME = timedelta(
        minutes=_env_int("SESSION_LIFETIME_MINUTES", 30)
    )
    SESSION_REFRESH_EACH_REQUEST = True
    SESSION_COOKIE_SECURE = _env_bool(
        "SESSION_COOKIE_SECURE", IS_PRODUCTION
    )
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Lax").strip() or "Lax"
    WTF_CSRF_TIME_LIMIT = timedelta(
        minutes=_env_int("CSRF_TIME_LIMIT_MINUTES", 30)
    )

    PREFERRED_URL_SCHEME = "https" if IS_PRODUCTION else "http"
    TRUSTED_HOSTS = _env_list("TRUSTED_HOSTS") or None

    # Set TRUST_PROXY=1 only when Flask is reachable exclusively through the
    # reverse proxy (normally 127.0.0.1). Otherwise clients could spoof
    # X-Forwarded-For and X-Forwarded-Proto.
    TRUST_PROXY = _env_bool("TRUST_PROXY", IS_PRODUCTION)
    TRUSTED_PROXY_COUNT = _env_int("TRUSTED_PROXY_COUNT", 1)
    HSTS_MAX_AGE = _env_int("HSTS_MAX_AGE", 31536000, minimum=0)
    HSTS_INCLUDE_SUBDOMAINS = _env_bool("HSTS_INCLUDE_SUBDOMAINS", False)

    LOG_LEVEL = (os.getenv("LOG_LEVEL") or "INFO").strip().upper()

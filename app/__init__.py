import os

from flask import Flask, session
from flask_login import current_user
from werkzeug.middleware.proxy_fix import ProxyFix

from config import Config
from app.config_validation import validate_runtime_config
from app.database import register_sqlite_pragmas
from app.extensions import db, login_manager, migrate
from app.models import AuditLog, MediaFile, User  # noqa: F401 - register SQLAlchemy models
from app.security_headers import install_security_headers


def create_app():
    here = os.path.abspath(os.path.dirname(__file__))
    instance_path = os.path.join(here, "instance")
    app = Flask(
        __name__,
        instance_path=instance_path,
        instance_relative_config=True,
    )
    os.makedirs(app.instance_path, exist_ok=True)

    app.config.from_object(Config)
    if not app.config.get("MAX_CONTENT_LENGTH"):
        app.config["MAX_CONTENT_LENGTH"] = 250 * 1024 * 1024
    # Private media must not live under app/static: static routes bypass ownership checks.
    app.config["UPLOAD_FOLDER"] = os.path.join(app.instance_path, "processed")

    # Validate secrets and cookie policy before any extension or request uses them.
    validate_runtime_config(app)

    if app.config.get("TRUST_PROXY"):
        proxy_count = max(1, int(app.config.get("TRUSTED_PROXY_COUNT", 1)))
        app.wsgi_app = ProxyFix(
            app.wsgi_app,
            x_for=proxy_count,
            x_proto=proxy_count,
            x_host=proxy_count,
            x_port=proxy_count,
        )

    install_security_headers(app)

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    os.makedirs(app.config["YOLO_MODELS_DIR"], exist_ok=True)

    register_sqlite_pragmas()
    db.init_app(app)
    migrate.init_app(app, db, render_as_batch=True)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Войдите в систему для доступа к этому разделу."
    login_manager.login_message_category = "warning"

    from app.forms.auth_forms import LogoutForm

    @app.context_processor
    def inject_logout_form():
        return {"logout_form": LogoutForm()}

    @app.before_request
    def enforce_permanent_session():
        """Upgrade legacy non-permanent sessions to the configured idle lifetime."""
        if getattr(current_user, "is_authenticated", False) and not session.permanent:
            session.permanent = True

    from app.routes.main import main
    from app.routes.auth import auth
    from app.routes.analysis import analysis
    from app.routes.files import files_bp
    from app.routes.chat_bot import bp as chatbot_bp
    from app.routes.admin import admin_bp
    from app.routes.audit import audit_bp
    from app.routes.models_admin import models_admin_bp

    app.register_blueprint(main)
    app.register_blueprint(auth)
    app.register_blueprint(analysis)
    app.register_blueprint(files_bp)
    app.register_blueprint(chatbot_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(audit_bp)
    app.register_blueprint(models_admin_bp)

    if app.config.get("AUTO_CREATE_DB"):
        with app.app_context():
            db.create_all()

    return app

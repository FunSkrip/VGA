import os

from flask import Flask
from config import Config
from app.extensions import db, login_manager
from app.models import AuditLog, MediaFile, User  # noqa: F401 - register SQLAlchemy models
from app.rbac_migration import upgrade_legacy_schema


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
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    os.makedirs(app.config["YOLO_MODELS_DIR"], exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Войдите в систему для доступа к этому разделу."
    login_manager.login_message_category = "warning"

    from app.routes.main import main
    from app.routes.auth import auth
    from app.routes.analysis import analysis
    from app.routes.files import files_bp
    from app.routes.chat_bot import bp as chatbot_bp
    from app.routes.admin import admin_bp
    from app.routes.audit import audit_bp

    app.register_blueprint(main)
    app.register_blueprint(auth)
    app.register_blueprint(analysis)
    app.register_blueprint(files_bp)
    app.register_blueprint(chatbot_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(audit_bp)

    with app.app_context():
        db.create_all()
        upgrade_legacy_schema(db)

    return app

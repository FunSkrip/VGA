import os
from flask import Flask
from config import Config
from app.models.user import User
from .extensions import db, login_manager


def create_app():

    here = os.path.abspath(os.path.dirname(__file__))  # это app/
    inst_path = os.path.join(here, 'instance')

    app = Flask(
        __name__,
        instance_path=inst_path,
        instance_relative_config=True
    )

    os.makedirs(app.instance_path, exist_ok=True)

    app.config.from_object(Config)

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['YOLO_MODELS_DIR'], exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)

    from app.routes.main import main
    from app.routes.auth import auth
    from app.routes.analysis import analysis
    from app.routes.files import files_bp

    from app.routes.chat_bot import bp

    app.register_blueprint(main)
    app.register_blueprint(auth)
    app.register_blueprint(analysis)
    app.register_blueprint(files_bp)

    app.register_blueprint(bp)

    with app.app_context():
        db.create_all()

    return app

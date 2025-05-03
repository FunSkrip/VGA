import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'ef78f8ae12c9585b22cc7273b2bd52b0f3447a8fdd037e69b7dcb04886181a06')
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(
        os.path.abspath(os.path.dirname(__file__)),
        'app', 'instance', 'VKR_YOLO.db'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'app', 'static', 'processed')
    YOLO_MODELS_DIR = os.path.join(BASE_DIR, 'models')

"""Production WSGI entry point.

Use a real WSGI server instead of ``python run.py``:
    waitress-serve --listen=127.0.0.1:8000 wsgi:app   # Windows
    gunicorn -w 1 -b 127.0.0.1:8000 wsgi:app          # Linux
"""
from app import create_app

app = create_app()

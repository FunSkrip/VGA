from flask import Flask

from app.security_headers import install_security_headers


def make_app():
    app = Flask(__name__)
    app.config.update(
        APP_ENV="production",
        HSTS_MAX_AGE=31536000,
        HSTS_INCLUDE_SUBDOMAINS=False,
    )
    install_security_headers(app)

    @app.route("/")
    def index():
        return "ok"

    return app


def test_security_headers_are_added():
    app = make_app()
    with app.test_client() as client:
        response = client.get("/", base_url="https://localhost")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "Content-Security-Policy" in response.headers


def test_hsts_only_on_https():
    app = make_app()
    with app.test_client() as client:
        secure = client.get("/", base_url="https://localhost")
        plain = client.get("/", base_url="http://localhost")
    assert secure.headers["Strict-Transport-Security"] == "max-age=31536000"
    assert "Strict-Transport-Security" not in plain.headers


def test_hsts_can_be_disabled():
    app = make_app()
    app.config["HSTS_MAX_AGE"] = 0
    with app.test_client() as client:
        response = client.get("/", base_url="https://localhost")
    assert "Strict-Transport-Security" not in response.headers

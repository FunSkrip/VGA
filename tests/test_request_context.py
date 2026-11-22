from flask import Flask

from app.request_context import register_request_context, request_id_from_header


def test_valid_request_id_is_kept():
    assert request_id_from_header("abc-123.REQUEST_1") == "abc-123.REQUEST_1"


def test_invalid_request_id_is_replaced():
    generated = request_id_from_header("bad id with spaces")
    assert generated != "bad id with spaces"
    assert len(generated) == 32


def test_request_id_header_is_returned():
    app = Flask(__name__)
    register_request_context(app)

    @app.route("/")
    def index():
        return "ok"

    with app.test_client() as client:
        preserved = client.get("/", headers={"X-Request-ID": "request-42"})
        generated = client.get("/")

    assert preserved.headers["X-Request-ID"] == "request-42"
    assert len(generated.headers["X-Request-ID"]) == 32

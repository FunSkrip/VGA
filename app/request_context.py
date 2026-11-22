"""Request correlation IDs shared by proxy, application and audit log."""
from __future__ import annotations

import re
import uuid

from flask import Flask, g, request

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
REQUEST_ID_HEADER = "X-Request-ID"


def request_id_from_header(value: str | None) -> str:
    candidate = (value or "").strip()
    if candidate and REQUEST_ID_PATTERN.fullmatch(candidate):
        return candidate
    return uuid.uuid4().hex


def register_request_context(app: Flask) -> None:
    @app.before_request
    def set_request_id():
        g.request_id = request_id_from_header(request.headers.get(REQUEST_ID_HEADER))

    @app.after_request
    def expose_request_id(response):
        request_id = getattr(g, "request_id", None)
        if request_id:
            response.headers[REQUEST_ID_HEADER] = request_id
        return response

"""HTTP security headers applied to every Flask response.

TLS itself is terminated by the reverse proxy. HSTS is emitted here only for
requests that Flask sees as HTTPS (ProxyFix + X-Forwarded-Proto), so local HTTP
development is not affected.
"""
from flask import Flask, request


CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "img-src 'self' data: blob:; "
    "media-src 'self' blob:; "
    "font-src 'self' data: https://cdn.jsdelivr.net; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)


def install_security_headers(app: Flask) -> None:
    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault(
            "Referrer-Policy", "strict-origin-when-cross-origin"
        )
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
        )
        response.headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)

        hsts_max_age = int(app.config.get("HSTS_MAX_AGE", 0) or 0)
        if request.is_secure and hsts_max_age > 0:
            value = f"max-age={hsts_max_age}"
            if app.config.get("HSTS_INCLUDE_SUBDOMAINS"):
                value += "; includeSubDomains"
            response.headers["Strict-Transport-Security"] = value

        return response

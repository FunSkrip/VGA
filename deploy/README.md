# Deployment

- `nginx/` — TLS 1.3 termination, HSTS, rate limits and proxy headers.
- `systemd/` — Linux service running Gunicorn on 127.0.0.1.
- `windows/` — Waitress/NSSM and reverse-proxy notes for Windows.
- `caddy/` — local HTTPS demo with a trusted internal certificate.

Flask must always listen on `127.0.0.1`; only the reverse proxy is reachable
from the network. Set `TRUST_PROXY=1` only in that setup, otherwise clients can
spoof forwarding headers.

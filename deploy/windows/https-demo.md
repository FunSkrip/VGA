# Local HTTPS stand

This setup runs:

```text
Browser -> https://localhost -> Caddy (TLS) -> 127.0.0.1:5000 -> Waitress -> Flask
```

## 1. Install Caddy

```powershell
winget install CaddyServer.Caddy
```

Or download `caddy.exe` from the official Caddy releases page and place it here:

```text
D:\VKR_YOLO\tools\caddy\caddy.exe
```

`tools\caddy\` is ignored by Git.

## 2. Install Python dependencies

```powershell
cd D:\VKR_YOLO
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 3. Trust the local Caddy certificate once

Open PowerShell **as Administrator**:

```powershell
cd D:\VKR_YOLO
.\tools\start_https_demo.ps1 -Trust
```

The script installs Caddy's local CA, starts Waitress and Caddy, and keeps Caddy
in the foreground. Stop it with `Ctrl+C`.

## 4. Normal start

After the first trusted run:

```powershell
cd D:\VKR_YOLO
.\tools\start_https_demo.ps1
```

Open:

```text
https://localhost
```

Caddy also redirects `http://localhost` to HTTPS.

## What the script sets

```text
APP_ENV=production
SESSION_COOKIE_SECURE=1
TRUST_PROXY=1
TRUSTED_PROXY_COUNT=1
TRUSTED_HOSTS=localhost,127.0.0.1
HSTS_MAX_AGE=300
```

`HSTS_MAX_AGE=300` is deliberately short for localhost. For a real domain set
it to `31536000`. Set it to `0` if you want to disable HSTS during local tests.

## Check that HTTPS security is active

In DevTools:

- Application -> Cookies: `Secure`, `HttpOnly`, `SameSite=Lax`;
- Network -> Response Headers: `Strict-Transport-Security`,
  `Content-Security-Policy`, `X-Frame-Options`, `X-Content-Type-Options`.

Via PowerShell:

```powershell
curl.exe -I https://localhost
curl.exe -I http://localhost
```

The first should return security headers; the second should redirect.

## Important

- Do not open `http://127.0.0.1:5000` for normal use in this mode: the session
  cookie is `Secure`, so the browser will not send it over HTTP.
- `TRUST_PROXY=1` is safe only while Flask is bound to `127.0.0.1` and reachable
  exclusively through Caddy.
- Port 443 may require an elevated shell the first time.
- Stop the demo with `Ctrl+C`; the script also stops Waitress.

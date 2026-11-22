# Production on Windows

BitLocker and the data location are managed outside this project. Do not move
`app/instance` just for this setup.

## 1. Install a real WSGI server

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 2. Run Flask on loopback only

```powershell
$env:APP_ENV = "production"
$env:SESSION_COOKIE_SECURE = "1"
$env:TRUST_PROXY = "1"
$env:TRUSTED_PROXY_COUNT = "1"
$env:TRUSTED_HOSTS = "vga.example.ru"
.\venv\Scripts\waitress-serve.exe --listen=127.0.0.1:8000 wsgi:app
```

Never use `python run.py` in production: it starts Flask's development server.

## 3. Wrap it as a Windows service

Use NSSM, WinSW or Task Scheduler with "Run whether user is logged on or not".

NSSM example:

```powershell
nssm install VGA "D:\VKR_YOLO\venv\Scripts\waitress-serve.exe"
nssm set VGA AppParameters "--listen=127.0.0.1:8000 wsgi:app"
nssm set VGA AppDirectory "D:\VKR_YOLO"
nssm set VGA AppEnvironmentExtra APP_ENV=production SESSION_COOKIE_SECURE=1 TRUST_PROXY=1 TRUSTED_PROXY_COUNT=1
nssm set VGA AppStdout "D:\VKR_YOLO\logs\vga.out.log"
nssm set VGA AppStderr "D:\VKR_YOLO\logs\vga.err.log"
nssm start VGA
```

Create the `logs` directory and restrict its ACL to the service account.

## 4. Terminate TLS in a reverse proxy

Use nginx for Windows or IIS with ARR. The proxy must:

- listen on 443 with a valid certificate;
- allow TLS 1.3 only;
- redirect HTTP to HTTPS;
- send `Strict-Transport-Security`;
- proxy to `http://127.0.0.1:8000`;
- set `X-Forwarded-Proto`, `X-Forwarded-For`, `X-Forwarded-Host`, `X-Request-ID`;
- limit request body to 250 MB and apply rate limits for `/login`, `/register`, `/upload`, `/chatbot`.

Use `deploy/nginx/vga.conf` and `deploy/nginx/vga-proxy-headers.conf` as the Linux
template; on Windows, adjust certificate paths and include paths.

## 5. Firewall

Block inbound access to port 8000 from anything except the local machine. Flask
must not be reachable directly from the network.

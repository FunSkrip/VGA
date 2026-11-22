param(
    [int]$Port = 5000,
    [switch]$Trust
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$waitress = Join-Path $root "venv\Scripts\waitress-serve.exe"
if (-not (Test-Path $waitress)) {
    Write-Host "Waitress is not installed. Run: .\venv\Scripts\python.exe -m pip install -r requirements.txt"
    exit 1
}

$caddyCommand = Get-Command caddy -ErrorAction SilentlyContinue
$caddy = if ($caddyCommand) { $caddyCommand.Source } else { $null }
if (-not $caddy) {
    $localCaddy = Join-Path $root "tools\caddy\caddy.exe"
    if (Test-Path $localCaddy) {
        $caddy = $localCaddy
    }
}
if (-not $caddy) {
    $wingetCaddy = Get-ChildItem `
        "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\CaddyServer.Caddy_*\caddy.exe" `
        -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($wingetCaddy) {
        $caddy = $wingetCaddy.FullName
    }
}
if (-not $caddy) {
    Write-Host "Caddy not found."
    Write-Host "Install it with: winget install CaddyServer.Caddy"
    Write-Host "Or put caddy.exe into: $root\tools\caddy\caddy.exe"
    exit 1
}

# Production-like settings for a local HTTPS demonstration.
$env:APP_ENV = "production"
$env:SESSION_COOKIE_SECURE = "1"
$env:TRUST_PROXY = "1"
$env:TRUSTED_PROXY_COUNT = "1"
$env:TRUSTED_HOSTS = "localhost,127.0.0.1"
if (-not $env:HSTS_MAX_AGE) { $env:HSTS_MAX_AGE = "300" }

if ($Trust) {
    Write-Host "Installing the local Caddy CA certificate (administrator rights required)..."
    & $caddy trust
}

Write-Host "Starting Waitress on 127.0.0.1:$Port ..."
$waitressProcess = Start-Process `
    -FilePath $waitress `
    -ArgumentList "--listen=127.0.0.1:$Port", "--trusted-proxy=127.0.0.1", "wsgi:app" `
    -WorkingDirectory $root `
    -PassThru `
    -WindowStyle Hidden

try {
    $ready = $false
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        try {
            $client = New-Object System.Net.Sockets.TcpClient
            $client.Connect("127.0.0.1", $Port)
            $client.Close()
            $ready = $true
            break
        }
        catch {
            Start-Sleep -Milliseconds 250
        }
    }
    if (-not $ready) {
        throw "Waitress did not start on 127.0.0.1:$Port"
    }

    Write-Host ""
    Write-Host "Open: https://localhost"
    Write-Host "If the certificate is not trusted yet, run this script once with -Trust from an elevated shell:"
    Write-Host "  .\tools\start_https_demo.ps1 -Trust"
    Write-Host ""
    Push-Location (Join-Path $root "deploy\caddy")
    & $caddy run --config Caddyfile
    Pop-Location
}
finally {
    if ($waitressProcess -and -not $waitressProcess.HasExited) {
        Stop-Process -Id $waitressProcess.Id -Force -ErrorAction SilentlyContinue
    }
}

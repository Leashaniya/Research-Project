# Run local gateway (no Docker). Proxies /guidance -> :8000, /papers -> :8001.
# Usage: from backend/ run: .\scripts\run-gateway.ps1

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$GatewayRoot = Resolve-Path (Join-Path $ScriptDir "..\gateway-local")
Set-Location $GatewayRoot

$VenvDir = Join-Path $GatewayRoot ".venv"
if (-not (Test-Path $VenvDir)) {
    Write-Host "Creating venv at $VenvDir ..."
    python -m venv $VenvDir
}
& (Join-Path $VenvDir "Scripts\Activate.ps1")

Write-Host "Installing gateway dependencies ..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

$Port = if ($env:PORT) { $env:PORT } else { "80" }
Write-Host "Starting gateway on port $Port (guidance -> 8000, papers -> 8001) ..."
python -m uvicorn main:app --host 0.0.0.0 --port $Port

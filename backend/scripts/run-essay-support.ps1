# Run Essay Support System service with a venv (no Docker).
# Usage: from backend/ run: .\scripts\run-essay-support.ps1

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ServiceRoot = Resolve-Path (Join-Path $ScriptDir "..\services\essay-support-system")
Set-Location $ServiceRoot

$VenvDir = Join-Path $ServiceRoot ".venv"
if (-not (Test-Path $VenvDir)) {
    Write-Host "Creating venv at $VenvDir ..."
    python -m venv $VenvDir
}
& (Join-Path $VenvDir "Scripts\Activate.ps1")

Write-Host "Installing/updating dependencies from requirements.txt ..."
python -m pip install -q --upgrade pip
if (Test-Path "requirements.txt") {
    pip install -q -r requirements.txt
}

$Port = if ($env:PORT) { $env:PORT } else { "8002" }
Write-Host "Starting Essay Support System on port $Port ..."
python -m uvicorn app.main:app --host 0.0.0.0 --port $Port

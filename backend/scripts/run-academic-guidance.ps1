# Run Academic Guidance service with a venv (no Docker).
# Usage: from backend/ run: .\scripts\run-academic-guidance.ps1
# Or: cd backend; .\scripts\run-academic-guidance.ps1

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ServiceRoot = Resolve-Path (Join-Path $ScriptDir "..\services\academic-guidance")
Set-Location $ServiceRoot

$VenvDir = Join-Path $ServiceRoot ".venv"
if (-not (Test-Path $VenvDir)) {
    Write-Host "Creating venv at $VenvDir ..."
    python -m venv $VenvDir
}
& (Join-Path $VenvDir "Scripts\Activate.ps1")

Write-Host "Installing/updating dependencies from pyproject.toml ..."
pip install -q --upgrade pip
pip install -q -e .

$Port = if ($env:PORT) { $env:PORT } else { "8000" }
Write-Host "Starting Academic Guidance on port $Port ..."
python -m uvicorn app.main:app --host 0.0.0.0 --port $Port

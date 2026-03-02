# Run Model Paper Generation service with a venv (no Docker).
# Usage: from backend/ run: .\scripts\run-model-paper.ps1

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ServiceRoot = Resolve-Path (Join-Path $ScriptDir "..\services\model-paper-generation")
Set-Location $ServiceRoot

$VenvDir = Join-Path $ServiceRoot ".venv"
if (-not (Test-Path $VenvDir)) {
    Write-Host "Creating venv at $VenvDir ..."
    python -m venv $VenvDir
}
& (Join-Path $VenvDir "Scripts\Activate.ps1")

Write-Host "Installing/updating dependencies from requirements.txt ..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

# Optional: use app\data as data if data folder missing
$DataDir = Join-Path $ServiceRoot "data"
$AppDataDir = Join-Path $ServiceRoot "app\data"
if (-not (Test-Path $DataDir) -and (Test-Path $AppDataDir)) {
    Write-Host "Linking app\data -> data for local run ..."
    New-Item -ItemType Junction -Path $DataDir -Target $AppDataDir -Force | Out-Null
}

$Port = if ($env:PORT) { $env:PORT } else { "8001" }
Write-Host "Starting Model Paper Generation on port $Port ..."
python -m uvicorn app.main:app --host 0.0.0.0 --port $Port

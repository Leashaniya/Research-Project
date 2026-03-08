# Run MCQ Studyplan Generation service with a venv (no Docker).
# Usage: from backend/ run: .\scripts\run-mcq-studyplan.ps1

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ServiceRoot = Resolve-Path (Join-Path $ScriptDir "..\services\mcq-studyplan-generation")
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

# Ensure spaCy English model is installed (required by nlp_utils)
Write-Host "Ensuring spaCy model en_core_web_sm is installed ..."
python -m spacy download en_core_web_sm

$Port = if ($env:PORT) { $env:PORT } else { "8003" }
Write-Host "Starting MCQ Studyplan Generation on port $Port ..."
python -m uvicorn app.main:app --host 0.0.0.0 --port $Port

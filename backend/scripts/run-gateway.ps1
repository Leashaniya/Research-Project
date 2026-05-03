# Run local gateway (no Docker). Proxies /guidance -> :8081, /papers -> :8000, etc.
# Usage: from backend/ run: .\scripts\run-gateway.ps1

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$GatewayRoot = Resolve-Path (Join-Path $ScriptDir "..\gateway-local")
Set-Location $GatewayRoot

$Port = if ($env:PORT) { $env:PORT } else { "7777" }
$env:DEFAULT_PROXY_TIMEOUT = if ($env:DEFAULT_PROXY_TIMEOUT) { $env:DEFAULT_PROXY_TIMEOUT } else { "86400" }
$env:GUIDANCE_PROXY_TIMEOUT = if ($env:GUIDANCE_PROXY_TIMEOUT) { $env:GUIDANCE_PROXY_TIMEOUT } else { "86400" }
$env:PAPERS_PROXY_TIMEOUT = if ($env:PAPERS_PROXY_TIMEOUT) { $env:PAPERS_PROXY_TIMEOUT } else { "86400" }
$env:MCQ_PROXY_TIMEOUT = if ($env:MCQ_PROXY_TIMEOUT) { $env:MCQ_PROXY_TIMEOUT } else { "86400" }

# If port is in use (e.g. previous gateway), try to free it so we can bind without changing port
$existing = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
if ($existing) {
    foreach ($procId in $existing) {
        try {
            $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
            if ($proc -and ($proc.ProcessName -eq "python" -or $proc.ProcessName -eq "python3")) {
                Write-Host "Stopping existing process on port $Port (PID $procId, $($proc.ProcessName)) ..."
                Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
                Start-Sleep -Seconds 1
            }
        } catch { }
    }
}

$VenvDir = Join-Path $GatewayRoot ".venv"
if (-not (Test-Path $VenvDir)) {
    Write-Host "Creating venv at $VenvDir ..."
    python -m venv $VenvDir
}
& (Join-Path $VenvDir "Scripts\Activate.ps1")

Write-Host "Installing gateway dependencies ..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

Write-Host "Starting gateway on port $Port (guidance -> 8081, papers -> 8000, essay -> 8002, mcq -> 8003) ..."
python -m uvicorn main:app --host 0.0.0.0 --port $Port

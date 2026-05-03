# Run all services and local gateway in separate windows
# Usage: from backend/ run: .\scripts\run-all.ps1

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

function Get-ListeningPidsByPort {
    param([int]$Port)

    $lines = netstat -ano | Select-String "LISTENING"
    $pids = @()
    foreach ($line in $lines) {
        $text = [string]$line.Line
        if ($text -match "^\s*TCP\s+\S+:$Port\s+\S+\s+LISTENING\s+(\d+)\s*$") {
            $pids += [int]$matches[1]
        }
    }
    return $pids | Sort-Object -Unique
}

function Stop-BackendPorts {
    $portsToClear = @(8081, 8000, 8002, 8003, 7777)
    Write-Host "Stopping processes on ports: $($portsToClear -join ', ') ..."

    foreach ($port in $portsToClear) {
        $pids = Get-ListeningPidsByPort -Port $port
        if (-not $pids -or $pids.Count -eq 0) {
            Write-Host "  - Port ${port}: no LISTENING process."
            continue
        }

        foreach ($targetPid in $pids) {
            if ($targetPid -eq $PID) { continue }
            Write-Host "  - Port ${port}: killing PID $targetPid"
            try {
                taskkill /PID $targetPid /F | Out-Null
            } catch {
                Write-Warning "Failed to kill PID $targetPid on port ${port}: $($_.Exception.Message)"
            }
        }
    }

    Start-Sleep -Seconds 1
}

Stop-BackendPorts

Write-Host "Starting all backend services..."

# 1. Academic Guidance (Port 8081)
$AgScript = Join-Path $ScriptDir "run-academic-guidance.ps1"
if (Test-Path $AgScript) {
    Write-Host "- Academic Guidance (Port 8081)"
    Start-Process powershell -ArgumentList "-NoExit","-Command","`$env:PORT='8081'; `$env:ACADEMIC_GUIDANCE_WORKERS='2'; & '$AgScript'"
}

# 2. Model Paper Generation (Port 8000)
$MpScript = Join-Path $ScriptDir "run-model-paper.ps1"
if (Test-Path $MpScript) {
    Write-Host "- Model Paper Generation (Port 8000)"
    Start-Process powershell -ArgumentList "-NoExit","-Command","`$env:PORT='8000'; & '$MpScript'"
}

# 3. Essay Support System (Port 8002)
$EsScript = Join-Path $ScriptDir "run-essay-support.ps1"
if (Test-Path $EsScript) {
    Write-Host "- Essay Support System (Port 8002)"
    Start-Process powershell -ArgumentList "-NoExit","-Command","`$env:PORT='8002'; & '$EsScript'"
}

# 4. MCQ Studyplan Generation (Port 8003)
$McqScript = Join-Path $ScriptDir "run-mcq-studyplan.ps1"
if (Test-Path $McqScript) {
    Write-Host "- MCQ Studyplan Generation (Port 8003)"
    Start-Process powershell -ArgumentList "-NoExit","-Command","`$env:PORT='8003'; & '$McqScript'"
}

# Wait a few seconds for services to start initializing
Start-Sleep -Seconds 3

# 5. Local Gateway (Port 7777)
$GwScript = Join-Path $ScriptDir "run-gateway.ps1"
if (Test-Path $GwScript) {
    Write-Host "- Local Gateway (Port 7777)"
    $GwArgs = "-NoExit", "-Command", "`$env:GUIDANCE_TARGET='http://127.0.0.1:8081'; `$env:PAPERS_TARGET='http://127.0.0.1:8000'; `$env:ESSAY_TARGET='http://127.0.0.1:8002'; `$env:MCQ_TARGET='http://127.0.0.1:8003'; `$env:DEFAULT_PROXY_TIMEOUT='86400'; `$env:GUIDANCE_PROXY_TIMEOUT='86400'; `$env:PAPERS_PROXY_TIMEOUT='86400'; `$env:MCQ_PROXY_TIMEOUT='86400'; `$env:PORT='7777'; & '$GwScript'"
    Start-Process powershell -ArgumentList $GwArgs

    Write-Host "Waiting for gateway to listen on port 7777 ..."
    $gatewayReady = $false
    for ($i = 1; $i -le 120; $i++) {
        $pids = Get-ListeningPidsByPort -Port 7777
        if ($pids -and $pids.Count -gt 0) {
            $gatewayReady = $true
            Write-Host "Gateway is listening on http://127.0.0.1:7777/ (PID(s): $($pids -join ', '))"
            break
        }
        Start-Sleep -Seconds 1
    }
    if (-not $gatewayReady) {
        Write-Warning "Gateway did not start listening on port 7777 within 120 seconds. Check the Local Gateway PowerShell window."
    }
}

Write-Host "Done! Services are booting up in separate PowerShell windows."
Write-Host "Gateway will be available at http://127.0.0.1:7777/"

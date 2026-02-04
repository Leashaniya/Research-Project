# Start Backend Server (kills existing process if needed)

Write-Host "Checking for existing backend server..." -ForegroundColor Yellow

# Find process using port 8000
$connection = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue

if ($connection) {
    $pid = $connection.OwningProcess
    Write-Host "Found existing process (PID: $pid) on port 8000. Stopping it..." -ForegroundColor Yellow
    Stop-Process -Id $pid -Force
    Start-Sleep -Seconds 2
    Write-Host "Old process stopped." -ForegroundColor Green
}

Write-Host "Starting backend server..." -ForegroundColor Green
python start_server.py

# Start Both Backends Script
Write-Host "🚀 Starting both backends..." -ForegroundColor Green

# Get the script directory
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Start Model Paper Backend
Write-Host "📄 Starting Model Paper Backend on port 8000..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$scriptDir\backend\model-paper-backend'; python -m uvicorn app.main:app --port 8000"

# Wait a moment
Start-Sleep -Seconds 2

# Start CA Guidance Backend
Write-Host "📚 Starting CA Guidance Backend on port 8001..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$scriptDir\backend\ca-guidance-and-summarization-backend'; python main.py"

Write-Host "✅ Both backends are starting in separate windows" -ForegroundColor Green
Write-Host "   - Model Paper Backend: http://localhost:8000" -ForegroundColor Yellow
Write-Host "   - CA Guidance Backend: http://localhost:8001" -ForegroundColor Yellow

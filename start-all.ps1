# Start All Services Script
Write-Host "🚀 Starting all services..." -ForegroundColor Green
Write-Host ""

# Get the script directory
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Start Model Paper Backend
Write-Host "📄 Starting Model Paper Backend (port 8000)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$scriptDir\backend\model-paper-backend'; python -m uvicorn app.main:app --port 8000"

Start-Sleep -Seconds 2

# Start CA Guidance Backend
Write-Host "📚 Starting CA Guidance Backend (port 8001)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$scriptDir\backend\ca-guidance-and-summarization-backend'; python main.py"

Start-Sleep -Seconds 2

# Start Model Paper Frontend
Write-Host "📄 Starting Model Paper Frontend (port 3000)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$scriptDir\frontend\model-paper-frontend'; npm start"

Start-Sleep -Seconds 2

# Start CA Guidance Frontend
Write-Host "📚 Starting CA Guidance Frontend (port 3333)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$scriptDir\frontend\ca-guidance-and-summarization-frontend'; npm run dev"

Start-Sleep -Seconds 2

# Start Dashboard (last, so it opens in browser)
Write-Host "🎯 Starting Dashboard (port 4000)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$scriptDir\frontend\dashboard'; npm start"

Write-Host ""
Write-Host "✅ All services are starting!" -ForegroundColor Green
Write-Host ""
Write-Host "Services will be available at:" -ForegroundColor Yellow
Write-Host "   🎯 Dashboard: http://localhost:4000" -ForegroundColor White
Write-Host "   📄 Model Paper: http://localhost:3000" -ForegroundColor White
Write-Host "   📚 CA Guidance: http://localhost:3333" -ForegroundColor White
Write-Host ""
Write-Host "Backends:" -ForegroundColor Yellow
Write-Host "   📄 Model Paper API: http://localhost:8000" -ForegroundColor White
Write-Host "   📚 CA Guidance API: http://localhost:8001" -ForegroundColor White
Write-Host ""
Write-Host "Opening dashboard in browser in 5 seconds..." -ForegroundColor Cyan
Start-Sleep -Seconds 5
Start-Process "http://localhost:4000"

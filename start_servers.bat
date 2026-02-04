@echo off
echo Starting Backend and Frontend Servers...
echo.

REM Start Backend in a new window
start "Backend Server" cmd /k "cd /d %~dp0 && python start_server.py"

REM Wait a moment for backend to start
timeout /t 3 /nobreak >nul

REM Start Frontend in a new window
start "Frontend Server" cmd /k "cd /d %~dp0frontend && npm start"

echo.
echo Both servers are starting in separate windows...
echo Backend: http://localhost:8000
echo Frontend: http://localhost:3000
echo.
echo Press any key to exit this window (servers will continue running)...
pause >nul

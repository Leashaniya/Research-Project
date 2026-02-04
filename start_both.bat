@echo off
echo ========================================
echo Starting Both Servers
echo ========================================
echo.
echo Starting Backend Server in new window...
start "Backend Server" cmd /k "cd /d %~dp0 && python start_server.py"
timeout /t 3 /nobreak >nul
echo.
echo Starting Frontend Server in new window...
start "Frontend Server" cmd /k "cd /d %~dp0\frontend && npm start"
echo.
echo Both servers are starting...
echo Backend: http://localhost:8000
echo Frontend: http://localhost:3000
echo.
echo Press any key to run connection test...
pause >nul
python test_connection.py
pause

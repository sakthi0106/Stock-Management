@echo off
title Saravanan Electricals - Stock Management Frontend UI
cd /d "%~dp0frontend"
echo ===================================================
echo Starting Stock Management Frontend (Port 5173)...
echo ===================================================
call npm run dev -- --host 127.0.0.1 --port 5173
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Vite dev failed, trying preview...
    call npm run preview -- --port 5173
)
pause

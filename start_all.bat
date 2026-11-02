@echo off
title Saravanan Electricals - Stock Management Launcher
echo ===================================================================
echo Starting Saravanan Electricals Stock Management System...
echo ===================================================================
start "Backend API (Flask :5050)" cmd /k "%~dp0start_backend.bat"
timeout /t 2 /nobreak > nul
start "Frontend UI (Vite :5173)" cmd /k "%~dp0start_frontend.bat"
echo.
echo Both servers are launching.
echo Backend API : http://127.0.0.1:5050
echo Frontend UI : http://127.0.0.1:5173
echo ===================================================================

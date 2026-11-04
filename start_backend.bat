@echo off
title Saravanan Electricals - Stock Management
cd /d "%~dp0backend"
echo ===================================================
echo Starting Stock Management System on Port 5050...
echo ===================================================
echo.
echo Opening browser at http://127.0.0.1:5050 ...
start http://127.0.0.1:5050
python app.py
pause

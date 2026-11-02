@echo off
title Saravanan Electricals - Stock Management Backend
cd /d "%~dp0backend"
echo ===================================================
echo Starting Stock Management Flask API (Port 5050)...
echo ===================================================
python app.py
pause

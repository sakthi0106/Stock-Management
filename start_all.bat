@echo off
title Saravanan Electricals - Stock Management
cd /d "%~dp0backend"
echo ===================================================================
echo Starting Saravanan Electricals Stock Management System...
echo ===================================================================
echo Opening web interface at http://127.0.0.1:5050 ...
start http://127.0.0.1:5050
python app.py
pause

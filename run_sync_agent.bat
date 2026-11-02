@echo off
title StockGuard LAN Sync Agent
cd /d "%~dp0sync-agent"
echo ===================================================
echo Running StockGuard Excel LAN Sync Agent...
echo ===================================================
python agent.py --once
echo.
pause

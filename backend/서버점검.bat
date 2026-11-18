@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Checking server code with real models (1-2 min)...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run_py.ps1" scripts\smoke_test.py
echo.
echo Result saved in the check-result folder. Tell Claude.
pause

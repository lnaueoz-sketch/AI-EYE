@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Starting server... open http://localhost:8000/docs after "Application startup complete"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run_py.ps1" scripts\serve.py
pause

@echo off
chcp 65001 >nul
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run_extract.ps1"
echo.
echo ===== Finished (or stopped). Tell Claude. =====
pause

@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PY=venv\Scripts\python.exe
where python >nul 2>nul
if errorlevel 1 ( echo [ERROR] python not found. Install Python 3.10+ & pause & exit /b 1 )

echo [1/3] Creating virtual env (venv)...
if not exist %PY% python -m venv venv
if not exist %PY% ( echo [ERROR] venv creation failed & pause & exit /b 1 )
%PY% -m pip --version >nul 2>nul || %PY% -m ensurepip --upgrade
%PY% -m pip --version >nul 2>nul || ( echo [ERROR] pip not available in venv & pause & exit /b 1 )

echo [2/3] Installing packages (first time: 5~10 min, torch is large)...
%PY% -m pip install --upgrade pip
%PY% -m pip install -r requirements.txt
if errorlevel 1 ( echo [ERROR] pip install failed. Copy the red messages above. & pause & exit /b 1 )

echo [3/3] Running logic tests...
%PY% -m pytest -q -p no:cacheprovider
echo.
echo ===== Setup done. Close this window and double-click run.bat =====
pause

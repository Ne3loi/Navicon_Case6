@echo off
chcp 65001 >nul
title Navicon Sanitizer 3.0
setlocal

cd /d "%~dp0"

echo ======================================================
echo          NAVICON SANITIZER 3.0 (CASE 6)
echo ======================================================
echo.

if not exist venv (
    echo [INFO] First launch detected. Creating virtual environment...
    python -m venv venv

    echo.
    echo [INFO] Installing dependencies...
    .\venv\Scripts\python.exe -m pip install --upgrade pip
    .\venv\Scripts\python.exe -m pip install -r requirements.txt
    echo.
    echo [OK] Installation complete.
)

echo [INFO] Starting local launcher...
.\venv\Scripts\python.exe -u run_local.py

if errorlevel 1 (
    echo.
    echo [ERROR] Launcher failed. See backend.log for details.
)

echo.
echo Done.
pause

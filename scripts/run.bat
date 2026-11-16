@echo off
SETLOCAL EnableDelayedExpansion
TITLE NEXUS FILES - Local Storage Intelligence Suite

cd /d "%~dp0.."

IF NOT EXIST ".venv\Scripts\python.exe" (
    echo [NEXUS FILES] Creating local Python virtual environment...
    python -m venv .venv
    IF ERRORLEVEL 1 (
        echo [ERROR] Python 3.12+ was not found on PATH. Please install Python 3.12+.
        pause
        exit /b 1
    )
    echo [NEXUS FILES] Installing dependencies from requirements.txt...
    ".venv\Scripts\pip.exe" install --upgrade pip
    ".venv\Scripts\pip.exe" install -r requirements.txt
)

echo [NEXUS FILES] Launching application...
".venv\Scripts\python.exe" main.py %*
ENDLOCAL

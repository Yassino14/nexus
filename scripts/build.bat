@echo off
SETLOCAL EnableDelayedExpansion
TITLE NEXUS FILES - Windows Executable Builder (PyInstaller)

cd /d "%~dp0.."

IF NOT EXIST ".venv\Scripts\python.exe" (
    echo [NEXUS FILES] Creating virtual environment for packaging...
    python -m venv .venv
    ".venv\Scripts\pip.exe" install --upgrade pip
    ".venv\Scripts\pip.exe" install -r requirements.txt
)

echo [NEXUS FILES] Running automated test suite before packaging...
".venv\Scripts\python.exe" -m unittest discover -s tests -v
IF ERRORLEVEL 1 (
    echo [ERROR] Automated tests failed. Aborting build.
    pause
    exit /b 1
)

echo [NEXUS FILES] Building standalone Windows executable via PyInstaller...
".venv\Scripts\pyinstaller.exe" nexus_files.spec --noconfirm --clean

echo.
echo [SUCCESS] Build complete! Executable located at: dist\NexusFiles\NexusFiles.exe
ENDLOCAL

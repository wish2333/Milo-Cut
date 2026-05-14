@echo off
chcp 65001 >nul 2>&1
REM PyWebVue development startup script (Windows)
REM
REM Usage:
REM   dev.bat              Demo mode
REM   dev.bat --vite       Vue dev mode
REM   dev.bat --setup      Only install dependencies
REM   dev.bat --help       Show all options
REM
REM All arguments are passed to dev.py

where uv >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] uv not found. Install: https://docs.astral.sh/uv/getting-started/installation/
    pause
    exit /b 1
)

uv run dev.py %*

@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo.
echo ============================================================
echo         NEXORA PROVIDER SERVER  —  start.bat
echo ============================================================
echo.
echo  Usage:
echo    start.bat              Auto-detect backend (local then cloud)
echo    start.bat --online     Force cloud backend
echo    start.bat --local      Force local backend (127.0.0.1:8000)
echo    start.bat --url URL    Use a custom backend URL
echo    start.bat --token TOK  Override the provider shared token
echo.
echo  Environment overrides (optional):
echo    PROVIDER_SHARED_TOKEN  Auth token  (default: local-demo-token)
echo    COST_PER_HOUR          Billing rate (default: 0.15)
echo    NEXORA_FFMPEG_PATH     Full path to ffmpeg.exe if it is not on PATH
echo.
echo ============================================================
echo.

REM ─── Default token (matches Render env var and backend fallback) ─────────────
if not defined PROVIDER_SHARED_TOKEN (
    set "PROVIDER_SHARED_TOKEN=local-demo-token"
)

REM ─── RTSP source override for local Docker MediaMTX ──────────────────────────
REM When running --online (connected to Render) but MediaMTX is local Docker,
REM set PROVIDER_RTSP_BASE_URL so the provider reads from local RTSP, not Render's loopback.
if not defined PROVIDER_RTSP_BASE_URL (
    set "PROVIDER_RTSP_BASE_URL=rtsp://127.0.0.1:8554"
    echo [CONFIG] PROVIDER_RTSP_BASE_URL auto-set to rtsp://127.0.0.1:8554 ^(local Docker MediaMTX^)
)

REM ─── Locate Python ───────────────────────────────────────────────────────────
set "PYTHON="

if exist ".venv\Scripts\python.exe" (
    set "PYTHON=.venv\Scripts\python.exe"
    echo [PYTHON] Using virtual environment: .venv\Scripts\python.exe
) else (
    echo [INFO] No virtual environment found at .venv\Scripts\python.exe
    echo [INFO] Checking for system Python...
    where python >nul 2>&1
    if !errorlevel!==0 (
        set "PYTHON=python"
        echo [PYTHON] Using system Python.
    ) else (
        where py >nul 2>&1
        if !errorlevel!==0 (
            set "PYTHON=py"
            echo [PYTHON] Using py launcher.
        )
    )
)

if not defined PYTHON (
    echo.
    echo [ERROR] Python not found. Install Python 3.10+ or create a venv:
    echo.
    echo   py -m venv .venv
    echo   .venv\Scripts\python.exe -m pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

REM ─── Install / check requirements ────────────────────────────────────────────
if not exist ".venv\Scripts\python.exe" (
    echo.
    echo [TIP] Consider creating a virtual environment for isolation:
    echo   py -m venv .venv
    echo   .venv\Scripts\python.exe -m pip install -r requirements.txt
    echo.
) else (
    REM Check if requirements are installed (look for requests as a proxy)
    ".venv\Scripts\python.exe" -c "import requests" >nul 2>&1
    if not !errorlevel!==0 (
        echo [SETUP] Installing requirements into virtual environment...
        ".venv\Scripts\python.exe" -m pip install -r requirements.txt
        if not !errorlevel!==0 (
            echo [ERROR] pip install failed. Check requirements.txt and your internet connection.
            pause
            exit /b 1
        )
        echo [SETUP] Requirements installed.
        echo.
    )
)

REM ─── Launch provider with all CLI args forwarded ─────────────────────────────
echo [START] Launching provider server...
echo.

"%PYTHON%" main.py %*

echo.
echo ============================================================
echo  Provider stopped.
echo ============================================================
echo.
pause

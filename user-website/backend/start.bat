@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

title Nexora — Backend (Local Control Plane)

echo.
echo ============================================================
echo         NEXORA CONTROL PLANE  —  Local Backend
echo ============================================================
echo.
echo  This starts the FastAPI control plane on http://127.0.0.1:8000
echo.
echo  Online scenario  : Run this alongside the live Render deployment
echo                     (providers and frontend auto-discover the cloud).
echo  Offline scenario : Run this to provide a fully local control plane.
echo                     Set provider start.bat with --local, or just
echo                     double-click it — auto-discovery finds this first.
echo.
echo ============================================================
echo.

REM ─── Locate Python ───────────────────────────────────────────────────────────
set "PYTHON="

if exist ".venv\Scripts\python.exe" (
    set "PYTHON=.venv\Scripts\python.exe"
    echo [PYTHON] Using virtual environment: .venv\Scripts\python.exe
) else (
    echo [INFO] No virtual environment found. Checking system Python...
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
    echo [ERROR] Python not found.
    echo.
    echo To set up a virtual environment run:
    echo   py -m venv .venv
    echo   .venv\Scripts\python.exe -m pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

REM ─── Auto-install requirements if any are missing ─────────────────────────
"%PYTHON%" -c "import fastapi, uvicorn, multipart, imageio_ffmpeg" >nul 2>&1
if not !errorlevel!==0 (
    echo [SETUP] Missing dependencies detected. Installing requirements...
    "%PYTHON%" -m pip install -r requirements.txt
    if not !errorlevel!==0 (
        echo [ERROR] pip install failed. Check your internet connection.
        pause
        exit /b 1
    )
    echo [SETUP] Requirements installed successfully.
    echo.
)

REM ─── Environment ─────────────────────────────────────────────────────────────
REM  Copy the repository's .env.example to .env and configure MediaMTX URLs.
REM  main.py loads that ignored .env automatically for this direct local run.
REM  MEDIAMTX_INGEST_URL and MEDIAMTX_PROVIDER_READ_URL must point to the
REM  MediaMTX host reachable from the OBS source device and provider PC.
REM  PROVIDER_SHARED_TOKEN must match the token used by providers.
REM  "local-demo-token" is accepted by the backend as a built-in fallback.
if not defined PROVIDER_SHARED_TOKEN (
    set "PROVIDER_SHARED_TOKEN=local-demo-token"
)

REM  SECRET_KEY for JWT signing. Change in production.
if not defined SECRET_KEY (
    set "SECRET_KEY=dev-secret-key-change-in-production"
)

echo [ENV]    Provider authentication token is configured (value hidden).
echo [ENV]    SECRET_KEY            = (set; value hidden)
echo.
echo [START]  http://127.0.0.1:8000
echo [DOCS]   http://127.0.0.1:8000/docs
echo.

"%PYTHON%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir app

echo.
echo ============================================================
echo  Backend stopped.
echo ============================================================
echo.
pause

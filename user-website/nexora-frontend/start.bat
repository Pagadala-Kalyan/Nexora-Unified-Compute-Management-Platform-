@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

title Nexora — Frontend

echo.
echo ============================================================
echo         NEXORA UCMP  —  Frontend
echo   One Platform. Any Compute. Intelligent Execution.
echo ============================================================
echo.
echo  The frontend auto-detects the correct backend:
echo.
echo    Local (served on localhost)
echo      -> Connects to http://127.0.0.1:8000  (local backend)
echo         Start user-website\backend\start.bat first for offline use.
echo.
echo    Hosted / Remote
echo      -> Connects to https://nexora-unified-compute-management.onrender.com
echo         Works with the cloud backend automatically (no setup needed).
echo.
echo  Override via URL query string:
echo    http://localhost:5173?controlPlane=http://my-server:8000
echo.
echo ============================================================
echo.

REM ─── Locate Python for http.server ───────────────────────────────────────────
set "PYTHON="

where python >nul 2>&1
if !errorlevel!==0 (
    set "PYTHON=python"
) else (
    where py >nul 2>&1
    if !errorlevel!==0 (
        set "PYTHON=py"
    )
)

if not defined PYTHON (
    echo [ERROR] Python not found. Install Python 3.10+ to serve the frontend.
    echo.
    echo Download: https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

REM ─── Optional: show whether local backend appears reachable ──────────────────
echo [INFO] Checking for local backend at http://127.0.0.1:8000 ...
curl --silent --max-time 3 --head http://127.0.0.1:8000/health >nul 2>&1
if !errorlevel!==0 (
    echo [INFO] Local backend not detected — frontend will use the cloud backend.
    echo [INFO] To use local mode, start user-website\backend\start.bat first.
) else (
    echo [OK]   Local backend is reachable — frontend will connect to 127.0.0.1:8000
)
echo.

echo [START] Serving frontend at http://localhost:5173
echo [STOP]  Press Ctrl+C to stop.
echo.

"%PYTHON%" -m http.server 5173 --bind 127.0.0.1

echo.
echo ============================================================
echo  Frontend server stopped.
echo ============================================================
echo.
pause

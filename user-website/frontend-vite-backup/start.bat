@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

title Nexora — Frontend (Vite Dev Server)

echo.
echo ============================================================
echo         NEXORA UCMP  —  Vite Frontend (Dev)
echo   One Platform. Any Compute. Intelligent Execution.
echo ============================================================
echo.
echo  Online  : Connects to https://nexora-unified-compute-management.onrender.com
echo  Offline : Set VITE_API_URL=http://127.0.0.1:8000 below,
echo            then start user-website\backend\start.bat first.
echo.
echo ============================================================
echo.

REM ─── Backend URL ─────────────────────────────────────────────────────────────
REM  Check if local backend is running; use it if reachable, else fall back to cloud.
set "LOCAL_BACKEND=http://127.0.0.1:8000"
set "CLOUD_BACKEND=https://nexora-unified-compute-management.onrender.com"

echo [INFO] Checking for local backend at %LOCAL_BACKEND% ...
curl --silent --max-time 3 --head "%LOCAL_BACKEND%/health" >nul 2>&1
if !errorlevel!==0 (
    echo [INFO] Local backend not reachable — using cloud backend.
    set "VITE_API_URL=%CLOUD_BACKEND%"
) else (
    echo [OK]   Local backend reachable — using local backend.
    set "VITE_API_URL=%LOCAL_BACKEND%"
)

echo [ENV]  VITE_API_URL = %VITE_API_URL%
echo.

REM ─── Node / npm check ────────────────────────────────────────────────────────
where node >nul 2>&1
if not !errorlevel!==0 (
    echo [ERROR] Node.js not found.
    echo.
    echo Download: https://nodejs.org/
    echo.
    pause
    exit /b 1
)

where npm >nul 2>&1
if not !errorlevel!==0 (
    echo [ERROR] npm not found. Reinstall Node.js.
    pause
    exit /b 1
)

REM ─── Install dependencies if needed ──────────────────────────────────────────
if not exist "node_modules" (
    echo [SETUP] node_modules not found. Installing packages...
    call npm install
    if !errorlevel!==0 (
        echo [ERROR] npm install failed. Check your internet connection.
        pause
        exit /b 1
    )
    echo [SETUP] Packages installed.
    echo.
)

echo [START] Starting Vite dev server at http://127.0.0.1:5173
echo [STOP]  Press Ctrl+C to stop.
echo.

call npm run dev -- --host 127.0.0.1

echo.
echo ============================================================
echo  Vite dev server stopped.
echo ============================================================
echo.
pause

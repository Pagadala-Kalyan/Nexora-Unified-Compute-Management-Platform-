@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo Python virtual environment not found at .venv\Scripts\python.exe
    echo.
    echo Create it with:
    echo   py -m venv .venv
    echo.
    echo Then install packages with:
    echo   .venv\Scripts\python.exe -m pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

REM ============================================================
REM Nexora Provider Configuration
REM ============================================================

REM Local backend used by the current application/dashboard
set "UCMP_BACKEND_URL=http://127.0.0.1:8000"
set "PROVIDER_SHARED_TOKEN=local-demo-token"

echo.
echo ============================================
echo       Nexora Provider
echo ============================================
echo.
echo [BACKEND] %UCMP_BACKEND_URL%
echo [AUTH]    Local provider authentication
echo.

REM Check whether the local backend is reachable.
curl --silent --head --max-time 5 "%UCMP_BACKEND_URL%" >nul 2>&1

if not %errorlevel%==0 (
    echo [ERROR] Nexora local backend is not reachable.
    echo.
    echo Please start the backend first, then run this provider again.
    echo.
    echo Expected backend:
    echo   %UCMP_BACKEND_URL%
    echo.
    pause
    exit /b 1
)

echo [OK] Backend is reachable.
echo.
echo Starting Nexora Provider...
echo.

".venv\Scripts\python.exe" .\main.py

echo.
echo ============================================
echo Provider stopped.
echo ============================================
echo.
pause

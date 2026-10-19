@echo off
title Nexora UCMP - Frontend Console
cd /d "%~dp0"

echo ========================================================
echo        NEXORA UCMP - FRONTEND CONSOLE
echo   One Platform. Any Compute. Intelligent Execution.
echo ========================================================
echo.
echo Starting lightweight web server on http://localhost:5173...
echo Control Plane Backend target: http://127.0.0.1:8000
echo.

python -m http.server 5173 --bind 127.0.0.1
pause

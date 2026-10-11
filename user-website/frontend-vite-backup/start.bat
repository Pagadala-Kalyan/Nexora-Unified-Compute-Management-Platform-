@echo off
setlocal
cd /d "%~dp0"

rem Use the hosted control plane so this browser sees providers connected over the internet.
set "VITE_API_URL=https://nexora-unified-compute-management.onrender.com"

if not exist "node_modules" (
  echo Installing frontend packages for the first run...
  call npm install
  if errorlevel 1 (
    echo Frontend setup failed.
    pause
    exit /b 1
  )
)

echo Starting Nexora frontend at http://127.0.0.1:5173
call npm run dev -- --host 127.0.0.1
pause

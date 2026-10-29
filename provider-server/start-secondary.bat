@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

title Nexora — Secondary Provider (Recovery Node)

echo.
echo ============================================================
echo   NEXORA SECONDARY COMPUTE NODE  —  start-secondary.bat
echo   Node ID:   provider-backup-02
echo   Node Name: Nexora Recovery Node 02
echo ============================================================
echo.
echo  Usage:
echo    start-secondary.bat --local    Connect to local backend
echo    start-secondary.bat --online   Connect to cloud Render backend
echo.

set "PROVIDER_ID=provider-backup-02"
set "PROVIDER_NAME=Nexora Recovery Node 02"

REM Forward all arguments along with the secondary node ID and Name
call start.bat --id provider-backup-02 --name "Nexora Recovery Node 02" %*

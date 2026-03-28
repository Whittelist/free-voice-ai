@echo off
setlocal
cd /d "%~dp0"

start "" powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0studio_voice_connector.ps1"
exit /b 0

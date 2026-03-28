@echo off
setlocal
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0studio_voice_connector.ps1"
exit /b %ERRORLEVEL%

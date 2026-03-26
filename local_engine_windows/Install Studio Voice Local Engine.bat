@echo off
setlocal
cd /d "%~dp0"

set "PUBLIC_WEB_URL=%STUDIO_VOICE_PUBLIC_WEB_URL%"
if not defined PUBLIC_WEB_URL set "PUBLIC_WEB_URL=https://your-domain.example.com"

set "ALLOWED_ORIGINS=%PUBLIC_WEB_URL%,http://localhost:5173,http://127.0.0.1:5173"

echo [INFO] Instalando Studio Voice Local Engine (portable launcher)...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_local_engine.ps1" ^
  -LauncherBat "run_portable_engine.bat" ^
  -PublicWebUrl "%PUBLIC_WEB_URL%" ^
  -OpenWeb ^
  -AllowedOrigins "%ALLOWED_ORIGINS%"

if errorlevel 1 (
  echo [ERROR] La instalacion fallo.
  echo [INFO] La ventana se queda abierta para que puedas copiar el error.
  echo [INFO] Si existe, adjunta tambien logs desde: %USERPROFILE%\.studio_voice_local\logs
  echo [INFO] Entra en: %PUBLIC_WEB_URL%/support
  echo [INFO] O abre la web y pulsa "Reportar bug / soporte", pega el error y te ayudamos.
  if /i not "%STUDIO_VOICE_SKIP_PAUSE_ON_INSTALL_ERROR%"=="1" (
    echo.
    pause
  )
  exit /b 1
)

echo [INFO] Instalacion completada.
endlocal

@echo off
setlocal
cd /d "%~dp0"

set "PUBLIC_WEB_URL=%STUDIO_VOICE_PUBLIC_WEB_URL%"
set "ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173"
set "SUPPORT_URL=/support"

if defined PUBLIC_WEB_URL (
  set "ALLOWED_ORIGINS=%ALLOWED_ORIGINS%,%PUBLIC_WEB_URL%"
  set "SUPPORT_URL=%PUBLIC_WEB_URL%/support"
) else (
  echo [WARN] STUDIO_VOICE_PUBLIC_WEB_URL no definida. Se instalara solo para localhost.
)

echo [INFO] Instalando Studio Voice Local Engine (portable launcher)...
if defined PUBLIC_WEB_URL (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_local_engine.ps1" ^
    -LauncherBat "run_portable_engine.bat" ^
    -PublicWebUrl "%PUBLIC_WEB_URL%" ^
    -OpenWeb ^
    -AllowedOrigins "%ALLOWED_ORIGINS%"
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_local_engine.ps1" ^
    -LauncherBat "run_portable_engine.bat" ^
    -PublicWebUrl "" ^
    -AllowedOrigins "%ALLOWED_ORIGINS%"
)

if errorlevel 1 (
  echo [ERROR] La instalacion fallo.
  echo [INFO] La ventana se queda abierta para que puedas copiar el error.
  echo [INFO] Si existe, adjunta tambien logs desde: %USERPROFILE%\.studio_voice_local\logs
  echo [INFO] Entra en: %SUPPORT_URL%
  echo [INFO] O abre la web y pulsa "Reportar bug / soporte", pega el error y te ayudamos.
  if /i not "%STUDIO_VOICE_SKIP_PAUSE_ON_INSTALL_ERROR%"=="1" (
    echo.
    pause
  )
  exit /b 1
)

echo [INFO] Instalacion completada.
endlocal

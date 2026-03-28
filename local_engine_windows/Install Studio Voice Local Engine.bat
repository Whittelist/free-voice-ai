@echo off
setlocal
cd /d "%~dp0"

set "SOURCE_ENGINE_DIR=%cd%"
set "PORTABLE_ENGINE_HOME=%LOCALAPPDATA%\StudioVoiceLocal\engine"
set "ACTIVE_ENGINE_DIR=%SOURCE_ENGINE_DIR%"

if /i not "%SOURCE_ENGINE_DIR%"=="%PORTABLE_ENGINE_HOME%" (
  echo [INFO] Preparando instalacion en ruta corta para evitar errores de Windows por rutas largas...
  if not exist "%PORTABLE_ENGINE_HOME%" mkdir "%PORTABLE_ENGINE_HOME%" >nul 2>nul
  robocopy "%SOURCE_ENGINE_DIR%" "%PORTABLE_ENGINE_HOME%" /E /R:1 /W:1 /NFL /NDL /NJH /NJS /NP >nul
  set "ROBOCOPY_EXIT=%ERRORLEVEL%"
  if %ROBOCOPY_EXIT% GEQ 8 (
    echo [WARN] No se pudo copiar el launcher a "%PORTABLE_ENGINE_HOME%" ^(codigo %ROBOCOPY_EXIT%^).
    echo [WARN] Se continuara desde la carpeta actual: "%SOURCE_ENGINE_DIR%".
  ) else (
    set "ACTIVE_ENGINE_DIR=%PORTABLE_ENGINE_HOME%"
    echo [INFO] Launcher copiado a: "%ACTIVE_ENGINE_DIR%"
  )
)

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
  powershell -NoProfile -ExecutionPolicy Bypass -File "%ACTIVE_ENGINE_DIR%\install_local_engine.ps1" ^
    -LauncherBat "run_portable_engine.bat" ^
    -PublicWebUrl "%PUBLIC_WEB_URL%" ^
    -OpenWeb ^
    -AllowedOrigins "%ALLOWED_ORIGINS%"
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%ACTIVE_ENGINE_DIR%\install_local_engine.ps1" ^
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

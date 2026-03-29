@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "DATA_DIR=%USERPROFILE%\.studio_voice_local"
set "LOG_DIR=%DATA_DIR%\logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>nul
for /f %%T in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss"') do set "INSTALL_TS=%%T"
if not defined INSTALL_TS set "INSTALL_TS=unknown"
set "INSTALL_LOG=%LOG_DIR%\install-bootstrap-%INSTALL_TS%.log"

set "SOURCE_ENGINE_DIR=%cd%"
set "PREFERRED_ENGINE_HOME=%USERPROFILE%\StudioVoiceLocal\engine"
if defined STUDIO_VOICE_ENGINE_HOME set "PREFERRED_ENGINE_HOME=%STUDIO_VOICE_ENGINE_HOME%"
set "LEGACY_ENGINE_HOME=%LOCALAPPDATA%\StudioVoiceLocal\engine"
set "PORTABLE_ENGINE_HOME=%PREFERRED_ENGINE_HOME%"
set "ACTIVE_ENGINE_DIR=%SOURCE_ENGINE_DIR%"

echo [INFO] Inicio instalador portable. > "%INSTALL_LOG%"
echo [INFO] source_engine_dir=%SOURCE_ENGINE_DIR% >> "%INSTALL_LOG%"
echo [INFO] preferred_engine_home=%PREFERRED_ENGINE_HOME% >> "%INSTALL_LOG%"
echo [INFO] legacy_engine_home=%LEGACY_ENGINE_HOME% >> "%INSTALL_LOG%"
echo [INFO] portable_engine_home=%PORTABLE_ENGINE_HOME% >> "%INSTALL_LOG%"

echo [INFO] Preparando archivos descargados (unblock)...
echo [INFO] Preparando archivos descargados (unblock)... >> "%INSTALL_LOG%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-ChildItem -LiteralPath '%SOURCE_ENGINE_DIR%' -Recurse -File -ErrorAction SilentlyContinue | Unblock-File -ErrorAction SilentlyContinue" >nul 2>nul

if /i not "%SOURCE_ENGINE_DIR%"=="%PORTABLE_ENGINE_HOME%" (
  echo [INFO] Preparando instalacion en ruta corta ^(%PORTABLE_ENGINE_HOME%^) para evitar errores de rutas largas...
  echo [INFO] Copiando launcher a ruta corta... >> "%INSTALL_LOG%"
  if not exist "%PORTABLE_ENGINE_HOME%" mkdir "%PORTABLE_ENGINE_HOME%" >nul 2>nul
  robocopy "%SOURCE_ENGINE_DIR%" "%PORTABLE_ENGINE_HOME%" /E /R:1 /W:1 /NFL /NDL /NJH /NJS /NP >nul
  set "ROBOCOPY_EXIT=!ERRORLEVEL!"
  echo [INFO] robocopy_exit=!ROBOCOPY_EXIT! >> "%INSTALL_LOG%"
  if !ROBOCOPY_EXIT! GEQ 8 (
    echo [WARN] No se pudo copiar el launcher a "%PORTABLE_ENGINE_HOME%" ^(codigo !ROBOCOPY_EXIT!^).
    echo [WARN] Se continuara desde la carpeta actual: "%SOURCE_ENGINE_DIR%".
    echo [WARN] Copia a ruta corta fallo. Se continua desde source. >> "%INSTALL_LOG%"
    if exist "%LEGACY_ENGINE_HOME%\install_local_engine.ps1" (
      echo [INFO] Instalacion legacy detectada en "%LEGACY_ENGINE_HOME%". Se intentara usar esa ruta.
      echo [INFO] fallback_legacy_engine_home=%LEGACY_ENGINE_HOME% >> "%INSTALL_LOG%"
      set "ACTIVE_ENGINE_DIR=%LEGACY_ENGINE_HOME%"
    )
  ) else (
    set "ACTIVE_ENGINE_DIR=%PORTABLE_ENGINE_HOME%"
    echo [INFO] Launcher copiado a: "!ACTIVE_ENGINE_DIR!"
    echo [INFO] active_engine_dir=!ACTIVE_ENGINE_DIR! >> "%INSTALL_LOG%"
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-ChildItem -LiteralPath '!ACTIVE_ENGINE_DIR!' -Recurse -File -ErrorAction SilentlyContinue | Unblock-File -ErrorAction SilentlyContinue" >nul 2>nul
  )
)

set "PUBLIC_WEB_URL=%STUDIO_VOICE_PUBLIC_WEB_URL%"
if not defined PUBLIC_WEB_URL (
  set "PUBLIC_WEB_URL=https://vozgratisconia.online"
)
set "ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173"
set "SUPPORT_URL=/support"
set "INSTALL_OPEN_WEB_FLAG="
if /i "%STUDIO_VOICE_OPEN_WEB_ON_INSTALL%"=="1" (
  set "INSTALL_OPEN_WEB_FLAG=-OpenWeb"
  echo [INFO] STUDIO_VOICE_OPEN_WEB_ON_INSTALL=1 detectado. Se abrira la web al finalizar.
)

if defined PUBLIC_WEB_URL (
  set "ALLOWED_ORIGINS=%ALLOWED_ORIGINS%,%PUBLIC_WEB_URL%"
  set "SUPPORT_URL=%PUBLIC_WEB_URL%/support"
) else (
  echo [WARN] STUDIO_VOICE_PUBLIC_WEB_URL no definida. Se instalara solo para localhost.
  echo [WARN] PUBLIC_WEB_URL no definida; modo localhost. >> "%INSTALL_LOG%"
)

echo [INFO] Instalando Studio Voice Local Engine (portable launcher)...
echo [INFO] allowed_origins=%ALLOWED_ORIGINS% >> "%INSTALL_LOG%"
echo [INFO] install_ps1=%ACTIVE_ENGINE_DIR%\install_local_engine.ps1 >> "%INSTALL_LOG%"
if defined PUBLIC_WEB_URL (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%ACTIVE_ENGINE_DIR%\install_local_engine.ps1" -LauncherBat "run_portable_engine.bat" -PublicWebUrl "%PUBLIC_WEB_URL%" !INSTALL_OPEN_WEB_FLAG! -AllowedOrigins "%ALLOWED_ORIGINS%"
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%ACTIVE_ENGINE_DIR%\install_local_engine.ps1" ^
    -LauncherBat "run_portable_engine.bat" ^
    -PublicWebUrl "" ^
    -AllowedOrigins "%ALLOWED_ORIGINS%"
)

if errorlevel 1 (
  echo [ERROR] Instalador retorno errorlevel=!ERRORLEVEL! >> "%INSTALL_LOG%"
  echo [ERROR] La instalacion fallo.
  echo [INFO] La ventana se queda abierta para que puedas copiar el error.
  echo [INFO] Si existe, adjunta tambien logs desde: %USERPROFILE%\.studio_voice_local\logs
  echo [INFO] Entra en: %SUPPORT_URL%
  echo [INFO] O abre la web y pulsa "Reportar bug / soporte", pega el error y te ayudamos.
  echo [INFO] Log bootstrap: %INSTALL_LOG%
  if /i not "%STUDIO_VOICE_SKIP_PAUSE_ON_INSTALL_ERROR%"=="1" (
    echo.
    pause
  )
  exit /b 1
)

echo [INFO] Instalacion completada.
if defined PUBLIC_WEB_URL echo [INFO] Abre manualmente la web cuando quieras: %PUBLIC_WEB_URL%
echo [INFO] Instalacion completada OK. >> "%INSTALL_LOG%"
echo [INFO] Log bootstrap: %INSTALL_LOG%
endlocal

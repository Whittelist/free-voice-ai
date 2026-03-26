@echo off
setlocal
cd /d "%~dp0"

echo [INFO] Exportando diagnostico local...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0export_diagnostics.ps1"

if errorlevel 1 (
  echo [ERROR] No se pudo exportar el diagnostico.
  exit /b 1
)

echo [INFO] Diagnostico exportado correctamente.
endlocal

@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"

set "PY_CMD="

REM 1) Preferimos python.exe directo si existe (evita problemas del py launcher con versiones)
where python >nul 2>nul
if %errorlevel%==0 (
  python -c "import sys; print(sys.version)" >nul 2>nul
  if %errorlevel%==0 set "PY_CMD=python"
)

REM 2) Fallback al launcher py (sin fijar minor version)
if not defined PY_CMD (
  where py >nul 2>nul
  if %errorlevel%==0 (
    py -3 -c "import sys; print(sys.version)" >nul 2>nul
    if %errorlevel%==0 set "PY_CMD=py -3"
  )
)

if not defined PY_CMD (
  echo [ERROR] No se encontro un runtime Python funcional.
  echo [ERROR] Instala Python 3.11+ y marca "Add python.exe to PATH".
  echo [ERROR] Consejo: ejecuta "py -0" para ver runtimes detectados.
  exit /b 1
)

echo [INFO] Python seleccionado: %PY_CMD%

if not exist ".venv\Scripts\python.exe" (
  echo [INFO] Creating virtual environment... ^(puede tardar 1-3 minutos, no cierres la ventana^)
  %PY_CMD% -m venv .venv
  if errorlevel 1 (
    echo [ERROR] Fallo creando el entorno virtual.
    echo [ERROR] Si cancelaste antes, borra ".venv" y reintenta.
    exit /b 1
  )
)

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] El entorno virtual parece corrupto ^(falta .venv\Scripts\python.exe^).
  echo [ERROR] Borra la carpeta ".venv" y ejecuta de nuevo.
  exit /b 1
)

echo [INFO] Ensuring pip is available...
".venv\Scripts\python.exe" -m ensurepip --upgrade >nul 2>nul

echo [INFO] Upgrading pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 (
  echo [ERROR] Fallo al actualizar pip.
  exit /b 1
)

echo [INFO] Installing dependencies...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo [ERROR] Fallo instalando dependencias.
  exit /b 1
)

echo [INFO] Starting Studio Voice Local Engine...
".venv\Scripts\python.exe" app.py

endlocal

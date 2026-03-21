@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"
set "BOOTSTRAP_SENTINEL=.venv\.bootstrap_done"
set "PRO_SENTINEL=.venv\.pro_deps_done"
set "ENGINE_PORT=%LOCAL_ENGINE_PORT%"
if not defined ENGINE_PORT set "ENGINE_PORT=57641"

set "PY_CMD="
set "PY_VER="

REM 1) Preferimos runtimes compatibles con Modo Pro real.
where py >nul 2>nul && (
  py -3.12 -c "import sys; print(sys.version)" >nul 2>nul && (
    set "PY_CMD=py -3.12"
    set "PY_VER=3.12"
  )
)

if not defined PY_CMD (
  where py >nul 2>nul && (
    py -3.11 -c "import sys; print(sys.version)" >nul 2>nul && (
      set "PY_CMD=py -3.11"
      set "PY_VER=3.11"
    )
  )
)

REM 2) Fallback a python.exe del PATH.
if not defined PY_CMD (
  where python >nul 2>nul && (
    python -c "import sys; print(sys.version)" >nul 2>nul && set "PY_CMD=python"
  )
)

REM 3) Fallback al launcher py generico.
if not defined PY_CMD (
  where py >nul 2>nul && (
    py -3 -c "import sys; print(sys.version)" >nul 2>nul && set "PY_CMD=py -3"
  )
)

if not defined PY_CMD (
  echo [ERROR] No se encontro un runtime Python funcional.
  echo [ERROR] Instala Python 3.11+ y marca "Add python.exe to PATH".
  echo [ERROR] Consejo: ejecuta "py -0" para ver runtimes detectados.
  exit /b 1
)

if not defined PY_VER (
  set "PY_VER_FULL="
  for /f "tokens=2 delims= " %%v in ('%PY_CMD% -V 2^>^&1') do set "PY_VER_FULL=%%v"
  if defined PY_VER_FULL (
    for /f "tokens=1,2 delims=." %%a in ("!PY_VER_FULL!") do set "PY_VER=%%a.%%b"
  )
)
if not defined PY_VER set "PY_VER=unknown"

echo [INFO] Python seleccionado: %PY_CMD% ^(version !PY_VER!^)

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

set "VENV_PY_VER="
set "VENV_PY_VER_FULL="
for /f "tokens=2 delims= " %%v in ('".venv\Scripts\python.exe" -V 2^>^&1') do set "VENV_PY_VER_FULL=%%v"
if defined VENV_PY_VER_FULL (
  for /f "tokens=1,2 delims=." %%a in ("!VENV_PY_VER_FULL!") do set "VENV_PY_VER=%%a.%%b"
)
if defined VENV_PY_VER (
  if /i not "!VENV_PY_VER!"=="!PY_VER!" (
    echo [INFO] El entorno .venv usa Python !VENV_PY_VER!, se recreara con !PY_VER!.
    rmdir /s /q ".venv" >nul 2>nul
    if exist ".venv" (
      echo [ERROR] No se pudo eliminar .venv porque esta en uso.
      echo [ERROR] Cierra la ventana del motor local y cualquier terminal con ^(.venv^) activa.
      echo [ERROR] Luego reintenta este comando.
      exit /b 1
    )
    %PY_CMD% -m venv .venv
    if errorlevel 1 (
      echo [ERROR] Fallo recreando .venv con Python !PY_VER!.
      exit /b 1
    )
    del /f /q "%BOOTSTRAP_SENTINEL%" >nul 2>nul
    del /f /q "%PRO_SENTINEL%" >nul 2>nul
  )
)

if /i not "%LOCAL_ENGINE_SKIP_PRO_DEPS%"=="1" (
  set "PY_PRO_OK=0"
  if "!PY_VER!"=="3.11" set "PY_PRO_OK=1"
  if "!PY_VER!"=="3.12" set "PY_PRO_OK=1"
  if "!PY_PRO_OK!"=="0" (
    echo [WARN] Python !PY_VER! no es compatible con dependencias Pro reales ^(chatterbox/torch^).
    echo [WARN] Instala Python 3.12 o 3.11 y relanza el script para habilitar clonacion real.
    set "LOCAL_ENGINE_SKIP_PRO_DEPS=1"
  )
)

if /i "%LOCAL_ENGINE_FORCE_SETUP%"=="1" (
  echo [INFO] LOCAL_ENGINE_FORCE_SETUP=1 detectado. Reinstalando dependencias...
  del /f /q "%BOOTSTRAP_SENTINEL%" >nul 2>nul
  del /f /q "%PRO_SENTINEL%" >nul 2>nul
)

if not exist "%BOOTSTRAP_SENTINEL%" (
  echo [INFO] Preparando entorno Python ^(primer arranque, puede tardar^)...

  echo [INFO] Ensuring pip is available...
  ".venv\Scripts\python.exe" -m ensurepip --upgrade >nul 2>nul

  echo [INFO] Upgrading pip/tooling...
  ".venv\Scripts\python.exe" -m pip install --upgrade pip wheel "setuptools<81"
  if errorlevel 1 (
    echo [ERROR] Fallo al actualizar pip.
    echo [ERROR] Si ves "Operation cancelled by user", vuelve a ejecutar y no cierres la ventana.
    exit /b 1
  )

  echo [INFO] Installing dependencies...
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo [ERROR] Fallo instalando dependencias.
    exit /b 1
  )

  if /i not "%LOCAL_ENGINE_SKIP_PRO_DEPS%"=="1" (
    if exist "requirements_pro.txt" (
      echo [INFO] Installing optional Pro dependencies...
      ".venv\Scripts\python.exe" -m pip install -r requirements_pro.txt
      if errorlevel 1 (
        echo [WARN] No se pudieron instalar dependencias Pro completas.
        echo [WARN] El motor arrancara en modo mock hasta resolver dependencias.
      ) else (
        echo [INFO] Dependencias Pro instaladas.>%PRO_SENTINEL%
      )
    )
  )

  echo [INFO] Entorno listo.>%BOOTSTRAP_SENTINEL%
) else (
  echo [INFO] Entorno ya preparado. Saltando reinstalacion de dependencias.
)

set "BASE_DEPS_OK=1"
".venv\Scripts\python.exe" -c "import fastapi,uvicorn,requests,multipart,annotated_types" >nul 2>nul
if errorlevel 1 set "BASE_DEPS_OK=0"
if "!BASE_DEPS_OK!"=="0" (
  echo [INFO] Dependencias base incompletas. Reinstalando requirements.txt...
  ".venv\Scripts\python.exe" -m pip install --upgrade pip wheel "setuptools<81"
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo [ERROR] No se pudieron recuperar dependencias base.
    exit /b 1
  )
)

if /i not "%LOCAL_ENGINE_SKIP_PRO_DEPS%"=="1" (
  if exist "requirements_pro.txt" (
    set "NEED_PRO_DEPS=0"
    if not exist "%PRO_SENTINEL%" set "NEED_PRO_DEPS=1"
    ".venv\Scripts\python.exe" -c "import pkg_resources, numpy, perth; from chatterbox.mtl_tts import ChatterboxMultilingualTTS" >nul 2>nul
    if errorlevel 1 set "NEED_PRO_DEPS=1"

    if "!NEED_PRO_DEPS!"=="1" (
      echo [INFO] Verificando/instalando dependencias Pro faltantes...
      ".venv\Scripts\python.exe" -m pip install -r requirements_pro.txt
      if errorlevel 1 (
        echo [WARN] Dependencias Pro incompletas. Se mantendra modo mock.
      ) else (
        echo [INFO] Dependencias Pro instaladas.>%PRO_SENTINEL%
      )
    )
  )
)

set "PORT_PID="
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /r /c:":%ENGINE_PORT% .*LISTENING"') do set "PORT_PID=%%p"
if defined PORT_PID (
  echo [INFO] Ya hay un proceso escuchando en 127.0.0.1:%ENGINE_PORT% ^(PID !PORT_PID!^).
  echo [INFO] Si es el motor local, puedes usar esa instancia y cerrar esta ventana.
  exit /b 0
)

echo [INFO] Starting Studio Voice Local Engine...
".venv\Scripts\python.exe" app.py

endlocal

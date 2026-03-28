@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"
set "STUDIO_VOICE_KEEP_CONSOLE_OPEN_ON_ERROR=%STUDIO_VOICE_KEEP_CONSOLE_OPEN_ON_ERROR%"
if not defined STUDIO_VOICE_KEEP_CONSOLE_OPEN_ON_ERROR set "STUDIO_VOICE_KEEP_CONSOLE_OPEN_ON_ERROR=1"
set "BOOTSTRAP_SENTINEL=.venv\.bootstrap_done"
set "PRO_SENTINEL=.venv\.pro_deps_done"
set "CHATTERBOX_PACKAGE=chatterbox-tts==0.1.6"
set "TORCH_VERSION=2.6.0"
set "TORCH_CUDA_BUILD=12.4"
set "TORCH_GPU_INDEX_URL=https://download.pytorch.org/whl/cu124"
set "TORCH_GPU_PACKAGES=torch==%TORCH_VERSION% torchaudio==%TORCH_VERSION%"
set "TORCH_CPU_INDEX_URL=https://download.pytorch.org/whl/cpu"
set "TORCH_CPU_PACKAGES=torch==%TORCH_VERSION% torchaudio==%TORCH_VERSION%"
set "ENGINE_PORT=%LOCAL_ENGINE_PORT%"
if not defined ENGINE_PORT set "ENGINE_PORT=57641"
echo [INFO] Entorno aislado: este launcher usa solo ".venv" dentro de esta carpeta.
echo [INFO] No modifica el Python global ni paquetes del sistema.
if /i "%LOCAL_ENGINE_SKIP_PRO_DEPS%"=="1" (
  echo [WARN] LOCAL_ENGINE_SKIP_PRO_DEPS=1 ignorado para mantener instalacion determinista.
)
if /i "%LOCAL_ENGINE_SKIP_TORCH_CUDA_AUTOINSTALL%"=="1" (
  echo [WARN] LOCAL_ENGINE_SKIP_TORCH_CUDA_AUTOINSTALL=1 ignorado para mantener instalacion determinista.
)
set "LOCAL_ENGINE_SKIP_PRO_DEPS=0"
set "LOCAL_ENGINE_SKIP_TORCH_CUDA_AUTOINSTALL=0"

if /i not "%LOCAL_ENGINE_RESPECT_CUDA_VISIBLE_DEVICES%"=="1" (
  if defined CUDA_VISIBLE_DEVICES (
    if /i not "%CUDA_VISIBLE_DEVICES%"=="0" (
      echo [INFO] Detectado CUDA_VISIBLE_DEVICES=%CUDA_VISIBLE_DEVICES% en el entorno.
      echo [INFO] Se forzara CUDA_VISIBLE_DEVICES=0 por estabilidad multi-GPU ^(usa LOCAL_ENGINE_RESPECT_CUDA_VISIBLE_DEVICES=1 para mantener el valor original^).
      set "CUDA_VISIBLE_DEVICES=0"
    ) else (
      echo [INFO] Detectado CUDA_VISIBLE_DEVICES=0. Se mantiene por estabilidad.
    )
  ) else (
    if /i not "%LOCAL_ENGINE_PIN_FIRST_CUDA_DEVICE%"=="0" (
      echo [INFO] No se detecto CUDA_VISIBLE_DEVICES. Se fijara a 0 por estabilidad multi-GPU.
      set "CUDA_VISIBLE_DEVICES=0"
    )
  )
)

set "PY_CMD="
set "PY_VER="

REM V1 fija Python 3.11 como baseline del motor local.
where py >nul 2>nul && (
  py -3.11 -c "import sys; print(sys.version)" >nul 2>nul && (
    set "PY_CMD=py -3.11"
    set "PY_VER=3.11"
  )
)

if not defined PY_CMD (
  where python >nul 2>nul && (
    python -c "import sys; sys.exit(0 if sys.version_info[:2]==(3,11) else 1)" >nul 2>nul && (
      set "PY_CMD=python"
      set "PY_VER=3.11"
    )
  )
)

if not defined PY_CMD (
  echo [ERROR] No se encontro Python 3.11.
  echo [ERROR] Este motor fija Python 3.11 como baseline del runtime local.
  echo [ERROR] Instala Python 3.11 y marca "Add python.exe to PATH".
  echo [ERROR] Consejo: ejecuta "py -0p" para ver runtimes detectados.
  goto :error_exit
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
    goto :error_exit
  )
)

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] El entorno virtual parece corrupto ^(falta .venv\Scripts\python.exe^).
  echo [ERROR] Borra la carpeta ".venv" y ejecuta de nuevo.
  goto :error_exit
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
      goto :error_exit
    )
    %PY_CMD% -m venv .venv
    if errorlevel 1 (
      echo [ERROR] Fallo recreando .venv con Python !PY_VER!.
      goto :error_exit
    )
    del /f /q "%BOOTSTRAP_SENTINEL%" >nul 2>nul
    del /f /q "%PRO_SENTINEL%" >nul 2>nul
  )
)

if /i not "%LOCAL_ENGINE_SKIP_PRO_DEPS%"=="1" (
  set "PY_PRO_OK=0"
  if "!PY_VER!"=="3.11" set "PY_PRO_OK=1"
  if "!PY_PRO_OK!"=="0" (
    echo [WARN] Python !PY_VER! no es compatible con dependencias Pro reales ^(chatterbox/torch^).
    echo [WARN] Instala Python 3.11 y relanza el script para habilitar clonacion real.
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
    goto :error_exit
  )

  echo [INFO] Installing dependencies...
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo [ERROR] Fallo instalando dependencias.
    goto :error_exit
  )

  if /i not "%LOCAL_ENGINE_SKIP_PRO_DEPS%"=="1" (
    if exist "requirements_pro.txt" (
      echo [INFO] Installing optional Pro dependencies...
      ".venv\Scripts\python.exe" -m pip install -r requirements_pro.txt
      if errorlevel 1 (
        echo [WARN] No se pudieron instalar dependencias Pro completas.
        echo [WARN] El motor arrancara en modo mock hasta resolver dependencias.
      ) else (
        ".venv\Scripts\python.exe" -m pip install --no-deps %CHATTERBOX_PACKAGE%
        if errorlevel 1 (
          echo [WARN] No se pudo instalar %CHATTERBOX_PACKAGE% sin dependencias.
          echo [WARN] El motor arrancara en modo mock hasta resolver dependencias.
        ) else (
          echo [INFO] Dependencias Pro instaladas.>%PRO_SENTINEL%
        )
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
    goto :error_exit
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
        ".venv\Scripts\python.exe" -m pip install --no-deps %CHATTERBOX_PACKAGE%
        if errorlevel 1 (
          echo [WARN] No se pudo instalar %CHATTERBOX_PACKAGE% sin dependencias.
          echo [WARN] Dependencias Pro incompletas. Se mantendra modo mock.
        ) else (
          echo [INFO] Dependencias Pro instaladas.>%PRO_SENTINEL%
        )
      )
    )
  )
)

if /i not "%LOCAL_ENGINE_SKIP_PRO_DEPS%"=="1" (
  if /i not "%LOCAL_ENGINE_SKIP_TORCH_CUDA_AUTOINSTALL%"=="1" (
    set "HAS_NVIDIA=0"
    set "GPU_NAME="
    set "TORCH_TARGET_INDEX_URL=%TORCH_GPU_INDEX_URL%"
    set "TORCH_TARGET_PACKAGES=%TORCH_GPU_PACKAGES%"
    set "TORCH_TARGET_LABEL=GPU CUDA %TORCH_CUDA_BUILD%"
    where nvidia-smi >nul 2>nul && set "HAS_NVIDIA=1"
    if "!HAS_NVIDIA!"=="1" (
      for /f "tokens=2,* delims=:" %%a in ('nvidia-smi -L 2^>nul ^| findstr /b /c:"GPU 0"') do if not defined GPU_NAME set "GPU_NAME=%%a"
      if defined GPU_NAME for /f "tokens=1 delims=(" %%g in ("!GPU_NAME!") do set "GPU_NAME=%%g"
      if not defined GPU_NAME (
        for /f "skip=1 usebackq delims=" %%g in (`nvidia-smi --query-gpu=name --format=csv 2^>nul`) do if not defined GPU_NAME set "GPU_NAME=%%g"
      )
      if defined GPU_NAME (
        echo(!GPU_NAME! | findstr /i /c:"ERROR:" >nul && set "GPU_NAME="
      )
      if defined GPU_NAME (
        for /f "tokens=* delims= " %%g in ("!GPU_NAME!") do set "GPU_NAME=%%g"
        echo [INFO] GPU NVIDIA detectada: !GPU_NAME!
      ) else (
        echo [INFO] GPU NVIDIA detectada.
      )
      echo [INFO] Matriz oficial seleccionada: !TORCH_TARGET_LABEL! ^(!TORCH_TARGET_PACKAGES!^).
    ) else (
      set "TORCH_TARGET_INDEX_URL=%TORCH_CPU_INDEX_URL%"
      set "TORCH_TARGET_PACKAGES=%TORCH_CPU_PACKAGES%"
      set "TORCH_TARGET_LABEL=CPU"
      echo [INFO] No se detecto GPU NVIDIA. Se asegurara la matriz oficial CPU ^(!TORCH_TARGET_PACKAGES!^).
    )

    set "TORCH_MATRIX_OK=0"
    ".venv\Scripts\python.exe" -c "import sys,torch; expected_version='!TORCH_VERSION!'; expected_cuda='!TORCH_CUDA_BUILD!' if '!HAS_NVIDIA!'=='1' else ''; version_ok=str(getattr(torch,'__version__','')).startswith(expected_version); cuda_build=str(getattr(getattr(torch,'version',None),'cuda',None) or ''); cuda_ok=(cuda_build==expected_cuda) if expected_cuda else (cuda_build==''); compat_ok=True; arches=set(torch.cuda.get_arch_list()) if expected_cuda and torch.cuda.is_available() else set(); count=int(torch.cuda.device_count()) if expected_cuda and torch.cuda.is_available() else 0; compat_ok=(any((not arches) or (f'sm_{torch.cuda.get_device_properties(i).major}{torch.cuda.get_device_properties(i).minor}' in arches) for i in range(count)) if expected_cuda and count else compat_ok); sys.exit(0 if version_ok and cuda_ok and compat_ok else 1)" >nul 2>nul
    if not errorlevel 1 set "TORCH_MATRIX_OK=1"

    if "!TORCH_MATRIX_OK!"=="0" (
      echo [INFO] Instalando/actualizando la matriz oficial de torch para !TORCH_TARGET_LABEL!...
      ".venv\Scripts\python.exe" -m pip install --upgrade --index-url "!TORCH_TARGET_INDEX_URL!" !TORCH_TARGET_PACKAGES!
      if errorlevel 1 (
        echo [WARN] No se pudo instalar la matriz oficial de torch para !TORCH_TARGET_LABEL!.
        if "!HAS_NVIDIA!"=="1" (
          echo [WARN] Se intentara un fallback honesto a CPU para evitar un entorno roto.
          ".venv\Scripts\python.exe" -m pip install --upgrade --index-url "%TORCH_CPU_INDEX_URL%" %TORCH_CPU_PACKAGES%
        )
      )
    ) else (
      echo [INFO] La matriz oficial de torch ya esta lista para !TORCH_TARGET_LABEL!.
    )

    if "!HAS_NVIDIA!"=="1" (
      set "TORCH_GPU_COMPAT_OK=0"
      ".venv\Scripts\python.exe" -c "import sys,torch; arches=set(torch.cuda.get_arch_list()) if torch.cuda.is_available() else set(); count=torch.cuda.device_count() if torch.cuda.is_available() else 0; ok=any((not arches) or (f'sm_{torch.cuda.get_device_properties(i).major}{torch.cuda.get_device_properties(i).minor}' in arches) for i in range(count)); sys.exit(0 if ok else 1)" >nul 2>nul
      if not errorlevel 1 set "TORCH_GPU_COMPAT_OK=1"
      if "!TORCH_GPU_COMPAT_OK!"=="0" (
        echo [WARN] El build oficial instalado sigue sin poder usar esta GPU con el torch actual.
        echo [WARN] El daemon debera anunciarse como runtime real en CPU, no como GPU real.
      )
    )
  )
)

set "PORT_PID="
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /r /c:":%ENGINE_PORT% .*LISTENING"') do if not defined PORT_PID set "PORT_PID=%%p"
if defined PORT_PID (
  set "ENGINE_HEALTH_OK=0"
  powershell -NoProfile -Command "try { $r = Invoke-RestMethod -Uri 'http://127.0.0.1:%ENGINE_PORT%/health' -Method Get -TimeoutSec 2; if ($r.status -eq 'ok' -and $r.service -eq 'studio-voice-local-engine') { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>nul
  if not errorlevel 1 set "ENGINE_HEALTH_OK=1"

  if "!ENGINE_HEALTH_OK!"=="1" (
    echo [INFO] Ya hay un proceso del motor local escuchando en 127.0.0.1:%ENGINE_PORT% ^(PID !PORT_PID!^).
    echo [INFO] Puedes usar esa instancia y cerrar esta ventana.
    goto :success_exit
  )

  echo [ERROR] El puerto 127.0.0.1:%ENGINE_PORT% esta ocupado por otro proceso ^(PID !PORT_PID!^).
  echo [ERROR] Cierra ese proceso o cambia LOCAL_ENGINE_PORT y reintenta.
  goto :error_exit
)

echo [INFO] Starting Studio Voice Local Engine...
".venv\Scripts\python.exe" app.py
if errorlevel 1 (
  echo [ERROR] El proceso local finalizo con error.
  goto :error_exit
)

goto :success_exit

:error_exit
echo [INFO] Puedes copiar este log en pantalla y reportarlo en soporte.
echo [INFO] En la web de Studio Voice pulsa "Reportar bug / soporte" y pega este error.
echo [INFO] Opcional facil: ejecuta "Exportar Diagnostico Studio Voice.bat" y adjunta el ZIP de diagnostico.
if /i not "%STUDIO_VOICE_KEEP_CONSOLE_OPEN_ON_ERROR%"=="0" (
  echo.
  echo [INFO] Pulsa una tecla para cerrar esta ventana...
  pause >nul
)
endlocal & exit /b 1

:success_exit
endlocal & exit /b 0

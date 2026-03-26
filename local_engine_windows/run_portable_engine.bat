@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"
set "STUDIO_VOICE_KEEP_CONSOLE_OPEN_ON_ERROR=%STUDIO_VOICE_KEEP_CONSOLE_OPEN_ON_ERROR%"
if not defined STUDIO_VOICE_KEEP_CONSOLE_OPEN_ON_ERROR set "STUDIO_VOICE_KEEP_CONSOLE_OPEN_ON_ERROR=1"
set "ENGINE_PORT=%LOCAL_ENGINE_PORT%"
if not defined ENGINE_PORT set "ENGINE_PORT=57641"

set "EMBED_DIR=%~dp0runtime\python311"
set "EMBED_PY=%EMBED_DIR%\python.exe"
set "BOOTSTRAP_SENTINEL=%EMBED_DIR%\.portable_bootstrap_done"
set "PRO_SENTINEL=%EMBED_DIR%\.portable_pro_deps_done"
set "GET_PIP_PY=%EMBED_DIR%\get-pip.py"
set "CHATTERBOX_PACKAGE=chatterbox-tts==0.1.6"
set "TORCH_GPU_INDEX_URL=https://download.pytorch.org/whl/cu128"
set "TORCH_GPU_PACKAGES=torch==2.7.0 torchaudio==2.7.0"
set "TORCH_CPU_INDEX_URL=https://download.pytorch.org/whl/cpu"
set "TORCH_CPU_PACKAGES=torch==2.7.0 torchaudio==2.7.0"

set "DATA_DIR=%LOCAL_ENGINE_DATA_DIR%"
if not defined DATA_DIR set "DATA_DIR=%USERPROFILE%\.studio_voice_local"
set "PROMPTS_SRC=%~dp0assets\default_prompts"
set "PROMPTS_DST=%DATA_DIR%\default_prompts"

if not exist "%EMBED_PY%" (
  echo [ERROR] No se encontro Python embebido en "%EMBED_PY%".
  echo [ERROR] Reextrae el ZIP oficial y ejecuta de nuevo este launcher.
  goto :error_exit
)

if /i not "%LOCAL_ENGINE_RESPECT_CUDA_VISIBLE_DEVICES%"=="1" (
  if defined CUDA_VISIBLE_DEVICES (
    if /i not "%CUDA_VISIBLE_DEVICES%"=="0" (
      echo [INFO] Detectado CUDA_VISIBLE_DEVICES=%CUDA_VISIBLE_DEVICES% en el entorno.
      echo [INFO] Se forzara CUDA_VISIBLE_DEVICES=0 por estabilidad multi-GPU.
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

if not exist "%DATA_DIR%" mkdir "%DATA_DIR%" >nul 2>nul
if not exist "%DATA_DIR%\logs" mkdir "%DATA_DIR%\logs" >nul 2>nul
if not exist "%PROMPTS_DST%" mkdir "%PROMPTS_DST%" >nul 2>nul

if exist "%PROMPTS_SRC%\es_f1.flac" copy /y "%PROMPTS_SRC%\es_f1.flac" "%PROMPTS_DST%\es_f1.flac" >nul 2>nul
if exist "%PROMPTS_SRC%\en_f1.flac" copy /y "%PROMPTS_SRC%\en_f1.flac" "%PROMPTS_DST%\en_f1.flac" >nul 2>nul

if /i "%LOCAL_ENGINE_FORCE_SETUP%"=="1" (
  echo [INFO] LOCAL_ENGINE_FORCE_SETUP=1 detectado. Reinstalando dependencias...
  del /f /q "%BOOTSTRAP_SENTINEL%" >nul 2>nul
  del /f /q "%PRO_SENTINEL%" >nul 2>nul
)

if not exist "%BOOTSTRAP_SENTINEL%" (
  echo [INFO] Preparando runtime portable de Python...
  "%EMBED_PY%" -m pip --version >nul 2>nul
  if errorlevel 1 (
    echo [INFO] pip no disponible en runtime portable. Descargando bootstrap...
    if not exist "%GET_PIP_PY%" (
      powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -UseBasicParsing 'https://bootstrap.pypa.io/get-pip.py' -OutFile '%GET_PIP_PY%'"
      if errorlevel 1 (
        echo [ERROR] No se pudo descargar get-pip.py.
        goto :error_exit
      )
    )
    "%EMBED_PY%" "%GET_PIP_PY%"
    if errorlevel 1 (
      echo [ERROR] No se pudo inicializar pip en el runtime portable.
      goto :error_exit
    )
  )

  echo [INFO] Actualizando pip/tooling...
  "%EMBED_PY%" -m pip install --upgrade pip wheel "setuptools<81"
  if errorlevel 1 (
    echo [ERROR] Fallo al actualizar pip en runtime portable.
    goto :error_exit
  )

  echo [INFO] Instalando dependencias base...
  "%EMBED_PY%" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo [ERROR] Fallo instalando requirements.txt.
    goto :error_exit
  )

  if /i not "%LOCAL_ENGINE_SKIP_PRO_DEPS%"=="1" (
    if exist "requirements_pro.txt" (
      echo [INFO] Instalando dependencias Pro...
      "%EMBED_PY%" -m pip install -r requirements_pro.txt
      if errorlevel 1 (
        echo [WARN] No se pudieron instalar dependencias Pro completas.
      ) else (
        "%EMBED_PY%" -m pip install --no-deps %CHATTERBOX_PACKAGE%
        if errorlevel 1 (
          echo [WARN] No se pudo instalar %CHATTERBOX_PACKAGE%.
        ) else (
          echo [INFO] Dependencias Pro instaladas.>%PRO_SENTINEL%
        )
      )
    )
  )

  echo [INFO] Runtime portable listo.>%BOOTSTRAP_SENTINEL%
) else (
  echo [INFO] Runtime portable ya preparado. Saltando reinstalacion completa.
)

set "BASE_DEPS_OK=1"
"%EMBED_PY%" -c "import fastapi,uvicorn,requests,multipart,annotated_types" >nul 2>nul
if errorlevel 1 set "BASE_DEPS_OK=0"
if "!BASE_DEPS_OK!"=="0" (
  echo [INFO] Dependencias base incompletas. Reinstalando...
  "%EMBED_PY%" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo [ERROR] No se pudieron recuperar dependencias base.
    goto :error_exit
  )
)

if /i not "%LOCAL_ENGINE_SKIP_PRO_DEPS%"=="1" (
  if exist "requirements_pro.txt" (
    set "NEED_PRO_DEPS=0"
    if not exist "%PRO_SENTINEL%" set "NEED_PRO_DEPS=1"
    "%EMBED_PY%" -c "import pkg_resources, numpy, perth; from chatterbox.mtl_tts import ChatterboxMultilingualTTS" >nul 2>nul
    if errorlevel 1 set "NEED_PRO_DEPS=1"

    if "!NEED_PRO_DEPS!"=="1" (
      echo [INFO] Verificando/instalando dependencias Pro faltantes...
      "%EMBED_PY%" -m pip install -r requirements_pro.txt
      if errorlevel 1 (
        echo [WARN] Dependencias Pro incompletas. Se mantendra modo mock.
      ) else (
        "%EMBED_PY%" -m pip install --no-deps %CHATTERBOX_PACKAGE%
        if errorlevel 1 (
          echo [WARN] No se pudo instalar %CHATTERBOX_PACKAGE%. Se mantendra modo mock.
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
    set "TORCH_TARGET_INDEX_URL=%TORCH_GPU_INDEX_URL%"
    set "TORCH_TARGET_PACKAGES=%TORCH_GPU_PACKAGES%"
    set "TORCH_TARGET_LABEL=GPU CUDA 12.8"
    where nvidia-smi >nul 2>nul && set "HAS_NVIDIA=1"
    if "!HAS_NVIDIA!"=="0" (
      set "TORCH_TARGET_INDEX_URL=%TORCH_CPU_INDEX_URL%"
      set "TORCH_TARGET_PACKAGES=%TORCH_CPU_PACKAGES%"
      set "TORCH_TARGET_LABEL=CPU"
    )

    set "TORCH_MATRIX_OK=0"
    "%EMBED_PY%" -c "import sys,torch; expected_version='2.7.0'; expected_cuda='12.8' if '!HAS_NVIDIA!'=='1' else ''; version_ok=str(getattr(torch,'__version__','')).startswith(expected_version); cuda_build=str(getattr(getattr(torch,'version',None),'cuda',None) or ''); cuda_ok=(cuda_build==expected_cuda) if expected_cuda else (cuda_build==''); sys.exit(0 if version_ok and cuda_ok else 1)" >nul 2>nul
    if not errorlevel 1 set "TORCH_MATRIX_OK=1"

    if "!TORCH_MATRIX_OK!"=="0" (
      echo [INFO] Instalando/actualizando matriz oficial de torch para !TORCH_TARGET_LABEL!...
      "%EMBED_PY%" -m pip install --upgrade --index-url "!TORCH_TARGET_INDEX_URL!" !TORCH_TARGET_PACKAGES!
      if errorlevel 1 (
        echo [WARN] No se pudo instalar torch para !TORCH_TARGET_LABEL!.
        if "!HAS_NVIDIA!"=="1" (
          echo [WARN] Intentando fallback a CPU...
          "%EMBED_PY%" -m pip install --upgrade --index-url "%TORCH_CPU_INDEX_URL%" %TORCH_CPU_PACKAGES%
        )
      )
    ) else (
      echo [INFO] Matriz oficial de torch ya lista para !TORCH_TARGET_LABEL!.
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
    echo [INFO] Ya hay un motor local escuchando en 127.0.0.1:%ENGINE_PORT% ^(PID !PORT_PID!^).
    goto :success_exit
  )

  echo [ERROR] El puerto 127.0.0.1:%ENGINE_PORT% esta ocupado por otro proceso ^(PID !PORT_PID!^).
  echo [ERROR] Cierra ese proceso o cambia LOCAL_ENGINE_PORT y reintenta.
  goto :error_exit
)

set "LOCAL_ENGINE_DATA_DIR=%DATA_DIR%"
echo [INFO] Starting Studio Voice Local Engine (portable)...
"%EMBED_PY%" app.py
if errorlevel 1 (
  echo [ERROR] El proceso local finalizo con error.
  goto :error_exit
)

goto :success_exit

:error_exit
echo [INFO] Puedes copiar este log en pantalla y reportarlo en soporte.
echo [INFO] Si existe, adjunta tambien logs desde: "%DATA_DIR%\logs"
echo [INFO] En la web de Studio Voice pulsa "Reportar bug / soporte" y pega este error.
echo [INFO] Opcional facil: ejecuta "Exportar Diagnostico Studio Voice.bat" y adjunta el ZIP.
if /i not "%STUDIO_VOICE_KEEP_CONSOLE_OPEN_ON_ERROR%"=="0" (
  echo.
  echo [INFO] Pulsa una tecla para cerrar esta ventana...
  pause >nul
)
endlocal & exit /b 1

:success_exit
endlocal & exit /b 0

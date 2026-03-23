# Studio Voice Local Engine (Windows MVP)

Motor local para `Modo Pro` con API en localhost y control mediante ventana visible.

## Objetivo

1. Ejecutar inferencia de audio en la maquina del usuario.
2. Evitar enviar audio/texto a servidores para inferencia Pro.
3. Aportar confianza: al cerrar la ventana se detiene el servicio local.

## Caracteristicas del MVP

1. UI minima con estado, logs y token local.
2. API FastAPI en `http://127.0.0.1:57641`.
3. Seguridad basica:
   - token local obligatorio en endpoints privados.
   - validacion de `Origin` por allowlist.
4. Flujo de modelo:
   - `download` bajo demanda.
   - `load` / `unload`.
5. Backend de inferencia:
   - `auto` (default): intenta Chatterbox real y cae a `mock` si faltan dependencias.
   - `chatterbox`: fuerza backend real.
   - `mock`: audio sintetico para depuracion.
5. Endpoints:
   - `GET /health`
   - `GET /version`
   - `GET /capabilities`
   - `GET /events/poll`
   - `POST /models/download`
   - `GET /models/download/status`
   - `POST /models/load`
   - `POST /models/unload`
   - `POST /tts`
   - `POST /clone`

## Quickstart (desarrollo)

```powershell
.\local_engine_windows\run_local_engine.bat
```

## Build de release para `.exe` (Windows)

Desde `local_engine_windows`:

```powershell
.\build_windows.ps1
```

Opciones principales del script:

1. `-OneFile`: genera un solo `.exe` en `dist/StudioVoiceLocalEngine-OneFile.exe`.
2. `-PfxPath` + `-PfxPassword`: firma con certificado `.pfx`.
3. `-CertThumbprint`: firma con certificado de `Cert:\CurrentUser\My` (default).
4. `-MachineStore`: al usar `-CertThumbprint`, cambia a `Cert:\LocalMachine\My`.
5. `-SkipSign`: compila sin firma (solo para pruebas internas).
6. `-SkipDefenderScan`: omite escaneo local con Microsoft Defender.
7. `-ProductVersion`: sobreescribe la version visible del ejecutable.

Ejemplo (firmado con PFX + one-file):

```powershell
.\build_windows.ps1 -OneFile -PfxPath "C:\certs\studio_voice.pfx" -PfxPassword "<PASSWORD>"
```

Ejemplo (firmado por huella en store local):

```powershell
.\build_windows.ps1 -CertThumbprint "<THUMBPRINT_SHA1>"
```

Si el certificado esta en `LocalMachine\My`:

```powershell
.\build_windows.ps1 -CertThumbprint "<THUMBPRINT_SHA1>" -MachineStore
```

Cada build genera ademas:

1. Hash SHA-256 (`.sha256`) junto al ejecutable.
2. Manifest de release en `dist/*-release.json`.

## Reducir alertas de SmartScreen/antivirus

No existe una forma de eliminar al 100% los avisos de reputacion en la primera distribucion, pero este flujo reduce mucho la friccion:

1. Firma siempre cada release con el mismo certificado (Authenticode + timestamp).
2. Publica desde un dominio HTTPS estable y con historial.
3. Mantener nombre de archivo/producto/version coherentes entre releases.
4. Publica hash SHA-256 y changelog en cada version.
5. Si hay falso positivo, enviar el binario a Microsoft Security Intelligence como `Software developer`.
6. Si hay warning por URL en Safe Browsing, reportar revision de URL/listado.

Consejo practico:

1. Para primeras versiones publicas, `one-folder` suele dar menos friccion operativa para soporte.
2. Usa `-OneFile` solo cuando ya tengas pipeline de firma y reputacion estable.

Requisito recomendado para Modo Pro real:

1. Python `3.11` o `3.12`.
2. Con Python `3.14` el motor puede iniciar, pero quedara en `mock` por incompatibilidades de `torch/chatterbox`.

Alternativa manual:

```powershell
cd local_engine_windows
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

Nota de arranque:

1. En el primer arranque instala dependencias y puede tardar.
2. Los siguientes arranques reutilizan el entorno y son mucho mas rapidos.
3. Si quieres forzar reinstalacion:

```powershell
$env:LOCAL_ENGINE_FORCE_SETUP="1"
.\local_engine_windows\run_local_engine.bat
```

## Recuperacion rapida si se interrumpe el venv

Si durante `Creating virtual environment...` cancelaste el proceso o quedo colgado:

```powershell
Remove-Item -Recurse -Force .\local_engine_windows\.venv
.\local_engine_windows\run_local_engine.bat
```

Comprobacion de salud:

```powershell
Invoke-WebRequest http://127.0.0.1:57641/health
```

Si ves `No suitable Python runtime found`:

1. El launcher `py` no encuentra esa version concreta.
2. Ejecuta con `python.exe` directo (si lo tienes instalado):

```powershell
python -m venv .\local_engine_windows\.venv
.\local_engine_windows\.venv\Scripts\python.exe -m pip install -r .\local_engine_windows\requirements.txt
.\local_engine_windows\.venv\Scripts\python.exe .\local_engine_windows\app.py
```

Si aparece `Form data requires "python-multipart" to be installed`:

```powershell
.\local_engine_windows\.venv\Scripts\python.exe -m pip install python-multipart
```

Si sale `modo mock` con `No module named 'numpy'`:

1. Suele significar que `.venv` se creo con Python 3.14.
2. Recomendado: recrear `.venv` con Python 3.11 para habilitar clonacion real.

```powershell
Remove-Item -Recurse -Force .\local_engine_windows\.venv
py -3.11 -m venv .\local_engine_windows\.venv
.\local_engine_windows\.venv\Scripts\python.exe -m pip install --upgrade pip
.\local_engine_windows\.venv\Scripts\python.exe -m pip install -r .\local_engine_windows\requirements.txt
.\local_engine_windows\.venv\Scripts\python.exe -m pip install -r .\local_engine_windows\requirements_pro.txt
npm run local-engine
```

Si la descarga Pro se queda en `15%` y termina con error tipo `'NoneType' object is not callable`:

1. Esa fase no es descarga HTTP: es inicializacion del backend Chatterbox y cache del modelo.
2. Suele venir de incompatibilidad `perth/pkg_resources` con versiones nuevas de `setuptools`.
3. El script actualizado ya lo corrige automaticamente, pero puedes forzarlo asi:

```powershell
$env:LOCAL_ENGINE_FORCE_SETUP="1"
.\local_engine_windows\run_local_engine.bat
```

## Parametros avanzados de inferencia (Fase C)

`POST /tts` (JSON) y `POST /clone` (form-data) aceptan estos campos opcionales:

1. `cfg_weight` (float, rango `0.0-1.5`, default `0.5`)
2. `exaggeration` (float, rango `0.0-2.0`, default `0.5`)
3. `temperature` (float, rango `0.1-2.0`, default `0.8`)
4. `seed` (int, rango `0-2147483647`, opcional)

Si se envia `seed`, el motor fija la semilla de `torch` para ese request y mejora la reproducibilidad.

## Token local

1. Se genera en el primer arranque y se guarda en:
   - `%USERPROFILE%\.studio_voice_local\api_token.txt`
2. Copia el token desde la app local y pegalo en la web (Modo Pro).

## Configuracion por variables de entorno

1. `LOCAL_ENGINE_PORT` (default: `57641`)
2. `LOCAL_ENGINE_DATA_DIR` (default: `%USERPROFILE%\.studio_voice_local`)
3. `LOCAL_ENGINE_ALLOWED_ORIGINS` (CSV)
   - Ejemplo para Railway:
     `LOCAL_ENGINE_ALLOWED_ORIGINS=http://localhost:5173,https://tu-app.up.railway.app`
4. `LOCAL_ENGINE_ALLOWED_ORIGIN_REGEX` (regex)
   - Default recomendado ya incluido:
     - `*.railway.app`
     - `*.up.railway.app`
     - `localhost` y `127.0.0.1`
5. `SIMULATE_MODEL_DOWNLOAD`:
   - `0` (default): modo normal.
   - `1`: descarga simulada con archivos placeholder.
6. `LOCAL_ENGINE_INFERENCE_BACKEND`:
   - `auto` (default)
   - `chatterbox`
   - `mock`
7. `LOCAL_ENGINE_SKIP_PRO_DEPS`:
   - `1` para saltar instalacion de dependencias Pro en el `.bat`.

## Notas

1. Este MVP prioriza arquitectura, seguridad local y experiencia de producto.
2. Si `chatterbox-tts` y dependencias estan instaladas, el daemon usa inferencia real.
3. Si faltan dependencias, entra en `mock` y la UI web lo muestra como advertencia.

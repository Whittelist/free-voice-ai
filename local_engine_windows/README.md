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

Alternativa manual:

```powershell
cd local_engine_windows
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
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

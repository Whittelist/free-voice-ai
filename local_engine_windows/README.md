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
   - `download` resumible (simulado por defecto para desarrollo).
   - `load` / `unload`.
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
cd local_engine_windows
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

## Token local

1. Se genera en el primer arranque y se guarda en:
   - `%USERPROFILE%\.studio_voice_local\api_token.txt`
2. Copia el token desde la app local y pegalo en la web (Modo Pro).

## Configuracion por variables de entorno

1. `LOCAL_ENGINE_PORT` (default: `57641`)
2. `LOCAL_ENGINE_DATA_DIR` (default: `%USERPROFILE%\.studio_voice_local`)
3. `LOCAL_ENGINE_ALLOWED_ORIGINS` (CSV)
4. `SIMULATE_MODEL_DOWNLOAD`:
   - `1` (default): descarga simulada con archivos placeholder.
   - `0`: intenta descarga HTTP real desde URLs del manifiesto.

## Notas

1. Este MVP prioriza arquitectura, seguridad local y experiencia de producto.
2. La inferencia actual del daemon devuelve audio sintetico para validar flujo.
3. El siguiente paso es conectar runtime real de Chatterbox ONNX.


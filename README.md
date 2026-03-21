# Studio Voice AI

Aplicacion web para texto a voz con arquitectura dual:

1. `Modo Rapido` (browser-only): SpeechT5/MMS en WebGPU/WASM.
2. `Modo Pro` (local): motor instalable en localhost para mayor calidad y clonacion real por referencia.

## Documentacion principal

1. Plan vigente: [`plan_modo_pro_local.md`](./plan_modo_pro_local.md)
2. Alias legacy: [`plan_elemento_externo.md`](./plan_elemento_externo.md)
3. Plan anterior: [`implementation_plan.md`](./implementation_plan.md)

## Frontend (Vite + React)

```bash
npm install
npm run dev
```

Variables opcionales:

1. `VITE_ENABLE_PRO_MODE=true|false` (default: `true`)
2. `VITE_LOCAL_ENGINE_URL=http://127.0.0.1:57641`

## Motor local Windows (MVP)

Carpeta: [`local_engine_windows`](./local_engine_windows)

Quickstart:

```powershell
cd local_engine_windows
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Tambien puedes usar:

```powershell
.\local_engine_windows\run_local_engine.bat
```

## Seguridad local del motor

1. Bind a `127.0.0.1`.
2. Token local obligatorio en endpoints privados.
3. Validacion estricta de `Origin`.


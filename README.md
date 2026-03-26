# Studio Voice AI

Aplicacion web para texto a voz con arquitectura dual:

1. `Modo Rapido` (browser-only): SpeechT5/MMS en WebGPU/WASM.
2. `Modo Pro` (local): motor instalable en localhost para mayor calidad y clonacion real por referencia.

Estado de producto: **publico y funcional**, en **technical preview**.

## Alcance real de esta fase

Bajo estas condiciones, el flujo actual funciona bien y es el que estamos validando activamente:

1. Windows 10/11
2. Chrome/Edge
3. Web en Railway (HTTPS) + launcher local Windows (`ZIP + BAT`)

Fuera de ese entorno (macOS, Linux, Safari, Firefox, setups raros de drivers/GPU/antivirus), puede fallar.
No ocultamos eso: si falla, queremos reporte estructurado para corregirlo en siguientes iteraciones.

Ruta de soporte cuando algo no funciona:

1. Exporta diagnostico (`Export Studio Voice Diagnostics.bat`)
2. Abre `/support`
3. Pega `support_bundle.json` + pasos + error textual

## Documentacion principal

1. Plan vigente: [`plan_modo_pro_local.md`](./plan_modo_pro_local.md)
2. Alias legacy: [`plan_elemento_externo.md`](./plan_elemento_externo.md)
3. Plan anterior: [`implementation_plan.md`](./implementation_plan.md)
4. Runbook operativo Windows (sesion real): [`local_engine_windows/RUNBOOK_modo_pro_windows.md`](./local_engine_windows/RUNBOOK_modo_pro_windows.md)
5. Guia usuario Windows: [`docs/windows_user_guide.md`](./docs/windows_user_guide.md)
6. FAQ troubleshooting: [`docs/troubleshooting_faq.md`](./docs/troubleshooting_faq.md)
7. Runbook interno release/soporte: [`docs/runbook_internal.md`](./docs/runbook_internal.md)

## Frontend (Vite + React)

```bash
npm install
npm run dev
```

Variables opcionales:

1. `VITE_ENABLE_PRO_MODE=true|false` (default: `true`)
2. `VITE_LOCAL_ENGINE_URL=http://127.0.0.1:57641`
3. `VITE_LOCAL_ENGINE_WINDOWS_INSTALLER_URL` (URL del ZIP launcher Windows)
4. `VITE_LOCAL_ENGINE_WINDOWS_RELEASES_URL` (fallback a pagina de Releases si el ZIP no existe aun)
5. `VITE_PUBLIC_APP_ORIGIN` (origen web publico esperado)
6. En `Modo Pro`, la URL local debe ser `http://...` (no `https://`).

## Deploy en Railway

Este repo ya incluye configuracion para Railway:

1. [`railway.json`](./railway.json)
2. [`nixpacks.toml`](./nixpacks.toml)

Pasos:

1. Conecta el repo en Railway.
2. Despliega (build con `npm ci` + `npm run build`).
3. Arranque con `npm run start:railway` (usa `$PORT`).

Variables backend para soporte interno:

1. `DATABASE_URL`
2. `BUG_REPORTS_ADMIN_PASSWORD`
3. `BUG_REPORTS_SESSION_SECRET`
4. `PUBLIC_WEB_ORIGIN` (documental/operativa)

Si aparece error de build por `rolldown` en Railway:

1. Este repo ya fuerza Node 22 y optional deps en `nixpacks.toml`.
2. Haz **Redeploy** para que Railway reconstruya con la nueva imagen/capa.
3. Si Railway conserva cache vieja, usa `Deploy -> Clear Build Cache -> Redeploy`.

Notas:

1. Railway solo sirve frontend/control plane.
2. El `Modo Pro` sigue ejecutando inferencia en localhost del usuario.
3. Para pruebas reales de Modo Pro desde dominio Railway, configura en el motor local:
   - `LOCAL_ENGINE_ALLOWED_ORIGINS=http://localhost:5173,https://TU-DOMINIO-RAILWAY`
4. Soporte integrado en web:
   - Boton flotante abajo a la izquierda: `Hubo un error? Reportalo`
   - `POST /api/bug-reports`
   - `GET /api/admin/bug-reports`
   - `GET /api/admin/bug-reports/:id`
   - `POST /api/admin/bug-reports/:id/status`

## Motor local Windows

Carpeta: [`local_engine_windows`](./local_engine_windows)

Instalacion/launcher de un clic:

```powershell
.\local_engine_windows\install_local_engine.ps1
```

Packaging release ZIP (launcher portable para usuarios finales):

```powershell
powershell -ExecutionPolicy Bypass -File .\local_engine_windows\build_portable_release.ps1 -PublicWebUrl "https://TU-DOMINIO"
```

o desde npm:

```powershell
npm run local-engine:install
```

Arranque directo del daemon:

```powershell
.\local_engine_windows\run_local_engine.bat
```

o desde npm (Windows):

```powershell
npm run local-engine
```

Notas del runtime real:

1. La ruta prioritaria es `BAT/launcher + daemon local`, no el `.exe` congelado.
2. Python `3.11` es el baseline soportado para el runtime Pro.
3. El daemon clasifica el runtime como `real_gpu`, `real_cpu`, `mock` o `disabled_frozen`.
4. La TTS Pro usa referencias por defecto de `es/en` cuando no subes audio.
5. El texto largo se segmenta automaticamente en bloques de hasta `300` caracteres.

Build de release (`.exe`) legacy:

```powershell
.\local_engine_windows\build_windows.ps1
```

Para minimizar alertas de confianza en descarga, usa firma digital:

```powershell
.\local_engine_windows\build_windows.ps1 -OneFile -PfxPath "C:\certs\studio_voice.pfx" -PfxPassword "<PASSWORD>"
```

Guia completa de build/SmartScreen/antivirus:

1. [`local_engine_windows/README.md`](./local_engine_windows/README.md)
2. Binario publicado en repo: [`releases/StudioVoiceLocalEngine.exe`](./releases/StudioVoiceLocalEngine.exe)
3. Hash publicado: [`releases/StudioVoiceLocalEngine.exe.sha256`](./releases/StudioVoiceLocalEngine.exe.sha256)

Panel de soporte:

1. Publico: `/support`
2. Admin: `/support/admin`

Si se interrumpio la creacion del entorno virtual:

```powershell
Remove-Item -Recurse -Force .\local_engine_windows\.venv
npm run local-engine
```

## Seguridad local del motor

1. Bind a `127.0.0.1`.
2. Token local obligatorio en endpoints privados.
3. Validacion de `Origin` con allowlist/config persistente.

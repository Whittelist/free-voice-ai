# Runbook Modo Pro (Windows)

Bitacora operativa basada en una sesion real de validacion end-to-end de `Modo Pro` en Windows (marzo de 2026).

## Objetivo

1. Levantar frontend + daemon local sin ambiguedades.
2. Confirmar `real_gpu` en `/capabilities`.
3. Diagnosticar rapido errores tipicos (`Failed to fetch`, `MISSING_TOKEN`, `real_cpu` por entorno CUDA).

## Estado esperado (OK)

En `GET /capabilities` (con token) debes ver:

1. `inference_backend: chatterbox`
2. `runtime_class: real_gpu`
3. `quality_tier: pro_real`
4. `real_backend_device: cuda:0`
5. `real_backend_torch_info.cuda_available: true`

## Flujo recomendado de arranque

Terminal A (daemon):

```powershell
.\local_engine_windows\run_local_engine.bat
```

Terminal B (frontend):

```powershell
npm run dev -- --port 5174
```

Nota: si Vite mueve el puerto (por ejemplo de `5173` a `5174`), hay que permitir ese `Origin` en el daemon.

## Permitir Origin correcto

```powershell
powershell -ExecutionPolicy Bypass -File .\local_engine_windows\install_local_engine.ps1 -NoLaunch -AllowedOrigins @("http://localhost:5174","http://127.0.0.1:5174")
```

Reinicia luego el daemon (`run_local_engine.bat`).

## Validacion API minima

```powershell
$token = (Get-Content "$env:USERPROFILE\.studio_voice_local\api_token.txt" -Raw).Trim()

Invoke-WebRequest -UseBasicParsing http://127.0.0.1:57641/health | Select-Object -Expand Content

Invoke-WebRequest -UseBasicParsing `
  -Headers @{ Authorization = "Bearer $token" } `
  http://127.0.0.1:57641/capabilities | Select-Object -Expand Content
```

## Casos reales y solucion

### 1) `MISSING_TOKEN` en `/capabilities`

Sintoma:

1. `GET /health` funciona.
2. `GET /capabilities` devuelve `{"code":"MISSING_TOKEN"}`.

Causa:

1. Falta header `Authorization: Bearer <token>`.

Solucion:

1. Leer token de `%USERPROFILE%\.studio_voice_local\api_token.txt`.
2. Repetir request con header `Authorization`.

### 2) `Failed to fetch` desde la web

Sintoma:

1. En UI: `No se pudo conectar con el motor local (Failed to fetch)`.

Causas mas probables:

1. El daemon no esta arriba en ese momento.
2. Origin del frontend no permitido.
3. En HTTPS, permiso de acceso local no concedido en el navegador.

Checklist:

1. `Invoke-WebRequest -UseBasicParsing http://127.0.0.1:57641/health`
2. Confirmar `allowed_origins` en `/capabilities`.
3. En UI, pulsar `Permitir acceso local`.
4. En Chrome/Edge (sitio HTTPS), aceptar `Local Network Access`.

### 3) `real_cpu` inesperado con torch CUDA instalado

Sintoma:

1. `torch_version` es `2.6.0+cu124`.
2. Pero `/capabilities` muestra `runtime_class: real_cpu` y `cuda_available: false`.

Causa real observada:

1. `CUDA_VISIBLE_DEVICES=1` heredado en el entorno.
2. Ese indice no mapea a una GPU utilizable para el daemon.

Solucion:

```powershell
Remove-Item Env:LOCAL_ENGINE_RESPECT_CUDA_VISIBLE_DEVICES -ErrorAction SilentlyContinue
$env:CUDA_VISIBLE_DEVICES = "0"

Get-NetTCPConnection -LocalPort 57641 -State Listen -ErrorAction SilentlyContinue |
  ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }

.\local_engine_windows\run_local_engine.bat
```

Luego verificar `/capabilities` de nuevo.

### 4) `activate` no activa (solo imprime ruta)

Sintoma:

1. Ejecutar `"C:\...\Scripts\activate"` solo imprime texto.

Causa:

1. Ese comando no ejecuta el script en PowerShell.

Solucion:

```powershell
& ".\local_engine_windows\.venv\Scripts\Activate.ps1"
```

Nota: para usar el daemon no es obligatorio activar la venv manualmente.

### 5) Advertencia de PowerShell al usar `Invoke-WebRequest`

Sintoma:

1. Prompt de seguridad sobre parseo de script HTML.

Solucion:

1. Usar `-UseBasicParsing` en las comprobaciones locales.

## Preflight completo (health + capabilities + tts)

```powershell
$token = (Get-Content "$env:USERPROFILE\.studio_voice_local\api_token.txt" -Raw).Trim()

Invoke-WebRequest -UseBasicParsing http://127.0.0.1:57641/health | Select-Object -Expand Content

Invoke-WebRequest -UseBasicParsing `
  -Headers @{ Authorization = "Bearer $token"; Origin = "http://localhost:5174" } `
  http://127.0.0.1:57641/capabilities | Select-Object -Expand Content

$body = @{
  text = "Prueba rapida local"
  language = "es"
  quality_profile = "pro_multilingual_balanced"
  use_default_reference = $true
} | ConvertTo-Json

Invoke-WebRequest -UseBasicParsing -Method Post `
  -Uri http://127.0.0.1:57641/tts `
  -Headers @{ Authorization = "Bearer $token"; Origin = "http://localhost:5174"; "Content-Type" = "application/json" } `
  -Body $body | Select-Object StatusCode, RawContentLength
```

Si esta ultima llamada devuelve `StatusCode=200`, el pipeline local esta operativo.

## Referencias rapidas

1. Launcher/daemon: [`run_local_engine.bat`](./run_local_engine.bat)
2. Instalador/config local: [`install_local_engine.ps1`](./install_local_engine.ps1)
3. API/engine: [`daemon.py`](./daemon.py)
4. UI Pro: [`../src/App.tsx`](../src/App.tsx)

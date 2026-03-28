# Studio Voice Local Engine (Windows)

Motor local para `Modo Pro` con API en localhost y control mediante ventana visible.

Estado de esta fase:

1. Flujo principal soportado y validado: `Windows + Chrome/Edge + ZIP launcher`.
2. No pretendemos cubrir todos los entornos en esta etapa.
3. Si hay fallo fuera del entorno soportado, priorizamos captura de logs y correccion iterativa.

## Objetivo

1. Ejecutar inferencia de audio en la maquina del usuario.
2. Evitar enviar audio/texto a servidores para inferencia Pro.
3. Aportar confianza: al cerrar la ventana se detiene el servicio local.

## Caracteristicas actuales

1. UI minima con estado, logs y token local.
2. API FastAPI en `http://127.0.0.1:57641`.
3. Seguridad basica:
   - token local obligatorio en endpoints privados.
   - validacion de `Origin` por allowlist.
4. Flujo de modelo:
   - `prepare` bajo demanda para precalentar el backend real de Chatterbox.
   - `load` / `unload`.
5. Backend de inferencia:
   - `auto` (default): intenta Chatterbox real y clasifica el runtime como `real_gpu`, `real_cpu`, `mock` o `disabled_frozen`.
   - `chatterbox`: fuerza backend real.
   - `mock`: audio sintetico para depuracion.
6. TTS/Clonacion:
   - TTS usa referencia por defecto para `es` y `en` cuando no subes audio.
   - El texto largo se segmenta en bloques de hasta `300` caracteres y luego se cose.
   - La referencia de usuario se normaliza a `24 kHz` mono y se limita a `30` segundos.
7. Endpoints:
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

Recomendacion para clonacion:

1. El repo oficial usa muestras cortas y limpias; `3-10` segundos suele funcionar bien.
2. Si la referencia esta en otro idioma que el texto de salida, conviene probar `cfg_weight=0.0`.
3. El motor normaliza el audio de referencia a `24 kHz` mono.
4. Limites duros: `20 MB` y `30` segundos tras normalizar.

## Quickstart

```powershell
.\install_local_engine.ps1
```

## Flujo publico recomendado (`ZIP + launcher portable`)

1. Build del ZIP de release:

```powershell
powershell -ExecutionPolicy Bypass -File .\build_portable_release.ps1 -PublicWebUrl "https://TU-DOMINIO"
```

2. Publica `studio-voice-local-windows-preview.zip` en GitHub Releases.
3. Usuario final ejecuta:
   - `Abrir Studio Voice Connector.bat`
4. Diagnostico para soporte:
   - Boton `Exportar Diagnostico` en el Connector
   - o `powershell -ExecutionPolicy Bypass -File .\export_diagnostics.ps1` (avanzado)

El launcher portable:

1. Usa Python embebido (no depende del Python del sistema).
2. Persiste estado en `%USERPROFILE%\.studio_voice_local`.
3. Escribe logs en `%USERPROFILE%\.studio_voice_local\logs`.

Runbook operativo (casos reales de debugging, marzo 2026):

1. [`RUNBOOK_modo_pro_windows.md`](./RUNBOOK_modo_pro_windows.md)

El script anterior:

1. Escribe una config persistente en `%USERPROFILE%\.studio_voice_local\config.json`.
2. Crea un acceso directo al launcher.
3. Arranca `run_local_engine.bat`.

Arranque directo del daemon:

```powershell
.\run_local_engine.bat
```

## Build de release para `.exe` (legacy)

El `.exe` congelado ya no es la referencia principal del runtime Pro. La ruta prioritaria es `launcher + daemon local`.

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

## Si Windows bloquea con "Control Inteligente de Aplicaciones"

Mensaje tipico:

1. "se bloqueo porque no se puede confirmar quien lo escribio y no es una aplicacion con la que estemos familiarizados"

Causa:

1. Smart App Control (`Windows 11`) esta en modo `On`.
2. El `.exe` no esta firmado, o la firma no es valida/confiable para Microsoft.

Comprobacion rapida:

```powershell
Get-MpComputerStatus | Select-Object SmartAppControlState
Get-AuthenticodeSignature .\dist\StudioVoiceLocalEngine\StudioVoiceLocalEngine.exe | Format-List Status,StatusMessage,SignerCertificate
```

Solucion para distribucion real:

1. Firmar el ejecutable con certificado de firma de codigo **RSA** emitido por CA confiable.
2. Incluir timestamp RFC3161.
3. Publicar siempre con el mismo publisher para construir reputacion.

Solucion temporal para desarrollo local:

1. Desactivar Smart App Control desde `Seguridad de Windows > Control de aplicaciones y navegador > Configuracion de Smart App Control`.
2. Nota: volver a activarlo puede requerir reset/reinstalacion de Windows.

Requisito recomendado para Modo Pro real:

1. Python `3.11`.
2. Este runtime fija `3.11` como baseline. Si el entorno se crea con otra version, el launcher lo recrea.

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
.\local_engine_windows\.venv\Scripts\python.exe -m pip install --no-deps chatterbox-tts==0.1.6
.\local_engine_windows\.venv\Scripts\python.exe -m pip install --upgrade --index-url https://download.pytorch.org/whl/cu124 torch==2.6.0 torchaudio==2.6.0
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

Si al abrir el `.exe` aparece `Unable to configure formatter 'default'`:

1. Es un fallo de configuracion de logging de `uvicorn` en algunos binarios empaquetados.
2. Solucion: recompilar con el `build_windows.ps1` actualizado (ya fuerza `log_config=None` al arrancar servidor local).
3. Borra builds viejos y genera uno nuevo:

```powershell
Remove-Item -Recurse -Force .\local_engine_windows\build,.\local_engine_windows\dist
.\local_engine_windows\build_windows.ps1 -SkipSign -SkipDefenderScan
```

4. Verifica que ejecutas el nuevo binario y no una copia antigua en `Downloads`.

Si en Modo Pro aparece `status 500` al validar backend real y el detalle menciona `os error 1455` o `archivo de paginacion`:

1. Es falta de memoria virtual de Windows (pagefile) para cargar el modelo.
2. Cierra apps pesadas (editores, navegador con muchas pestañas, juegos, etc.) y reinicia.
3. Aumenta la memoria virtual en `Configuracion avanzada del sistema > Rendimiento > Memoria virtual`.
4. Recomendado para este motor: al menos `65536 MB` (64 GB) si tienes espacio en disco.

Comportamiento actual:

1. Si el backend real no puede arrancar, la UI distingue explicitamente `GPU real`, `CPU real`, `mock` o `disabled_frozen`.
2. `mock` ya no debe interpretarse como paridad con la demo ni como clonacion real.

## Parametros avanzados de inferencia (Fase C)

`POST /tts` (JSON) y `POST /clone` (form-data) aceptan estos campos opcionales:

1. `use_default_reference` (`POST /tts` solo, bool, default `true`)
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

Importante:
- `run_local_engine.bat` solo modifica dependencias dentro de `.\.venv\` (proyecto local).
- `run_portable_engine.bat` solo modifica dependencias dentro de `.\runtime\python311\` (runtime embebido del ZIP).
- No se desinstalan paquetes del Python global del sistema.

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
7. `LOCAL_ENGINE_GPU_DEVICE_POLICY`:
   - `auto` (default): selecciona automaticamente la GPU CUDA con mas VRAM.
   - `max_vram`: igual que `auto`.
   - `first`: fuerza `cuda:0`.
8. `LOCAL_ENGINE_CUDA_DEVICE_INDEX`:
   - vacio (default): usa politica automatica.
   - numero entero (`0`, `1`, ...): fuerza `cuda:<index>` si existe.
   - si el indice no existe, el motor registra warning y vuelve a `auto`.
9. `LOCAL_ENGINE_MAX_REFERENCE_AUDIO_BYTES`:
   - Limite duro para el audio de referencia en `POST /clone`.
   - Default: `20971520` (`20 MB`).
10. `LOCAL_ENGINE_MAX_REFERENCE_AUDIO_SECONDS`:
   - Duracion maxima del fragmento limpio que usa el motor tras normalizar la referencia.
   - Default: `30.0`.
11. `LOCAL_ENGINE_SKIP_PRO_DEPS`:
   - Solo debug interno.
   - En launcher publico se ignora para mantener instalacion determinista.
12. `LOCAL_ENGINE_SKIP_TORCH_CUDA_AUTOINSTALL`:
   - Solo debug interno.
   - En launcher publico se ignora para mantener instalacion determinista.
   - `0`/vacio (comportamiento forzado): asegura la matriz oficial de `torch==2.6.0` + `torchaudio==2.6.0`.
   - Si detecta NVIDIA, usa `cu124`.
   - Si no hay NVIDIA o el build oficial no soporta la GPU actual, el daemon se anuncia como `real_cpu`.
   - `1`: desactiva esa instalacion automatica.
13. `LOCAL_ENGINE_RESPECT_CUDA_VISIBLE_DEVICES`:
   - `0`/vacio (default): el motor fuerza `CUDA_VISIBLE_DEVICES=0` por estabilidad en entornos multi-GPU (evita crashes al tocar GPUs legacy).
   - `1`: respeta exactamente el valor heredado de `CUDA_VISIBLE_DEVICES`.
14. `LOCAL_ENGINE_PIN_FIRST_CUDA_DEVICE`:
   - `1`/vacio (default): si no hay `CUDA_VISIBLE_DEVICES`, fija `0` por estabilidad.
   - `0`: no fuerza `CUDA_VISIBLE_DEVICES` cuando no viene definido.
15. `LOCAL_ENGINE_ALLOW_FROZEN_CUDA`:
   - `0`/vacio (default): en `.exe` empaquetado se desactiva CUDA por estabilidad.
   - `1`: fuerza uso de CUDA tambien en `.exe` (puede crashear segun driver/GPU).
16. `LOCAL_ENGINE_ALLOW_FROZEN_REAL_BACKEND`:
   - `0`/vacio (default): en `.exe` empaquetado se desactiva el backend real y se usa `mock` para evitar crashes nativos (`c10.dll`).
   - `1`: fuerza backend real en `.exe` (experimental/inestable).

Diagnostico de hardware para bug fixing:

1. El motor registra en logs:
   - version de `torch`
   - build CUDA de `torch`
   - si `torch.cuda.is_available()`
   - numero de GPUs CUDA detectadas
   - nombre/VRAM/capability por GPU
   - dispositivo final elegido y motivo (`reason`)
2. `GET /capabilities` ahora incluye:
   - `real_backend_torch_info`
   - `real_backend_cuda_devices`
   - `real_backend_cuda_index`
   - `real_backend_device_reason`

## Notas

1. Este MVP prioriza arquitectura, seguridad local y experiencia de producto.
2. Si `chatterbox-tts` y dependencias estan instaladas, el daemon usa inferencia real de Chatterbox.
3. Harness de comparacion con upstream:

```powershell
.\.venv\Scripts\python.exe .\compare_upstream.py --text "Hola mundo" --language es
```

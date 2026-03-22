# Plan + Informe Fase A (Ejecutada): WebGPU en Navegador vs Ventana Local

Fecha: 22 de marzo de 2026
Documento objetivo: dejar cerrado el analisis para retomar implementacion otro dia.

## 1) Resumen ejecutivo

1. La comparacion "modelo pesado en navegador (WebGPU) vs ventana local" si compensa en arquitectura y fiabilidad operativa.
2. El cuello principal actual no es la app web, sino que el motor local esta corriendo con `torch` CPU-only (`2.6.0+cpu`), por eso aun no exprime GPU.
3. Para cargas pesadas, el navegador arrastra dos riesgos: descarga inicial multi-GB y dependencia de WebGPU (experimental + posibles fallbacks).
4. La ventana local elimina esas limitaciones web y permite control total del entorno, pero el salto real de rendimiento llegara al activar CUDA en el runtime local.
5. Fase A queda entregada con datos reales medidos + proyeccion cuantificada.

## 2) Alcance de Fase A (lo ejecutado)

1. Revision tecnica de estado real del proyecto.
2. Benchmark real del backend local actual (`chatterbox` en CPU) para `tts` y `clone`.
3. Analisis de tamanos de modelos y tiempos de primera descarga.
4. Proyeccion numerica de mejora al pasar de CPU a GPU en la ventana local.
5. Entrega de conclusiones y plan de continuacion (sin ejecutar Fase B/C).

## 3) Entorno medido (tu maquina)

1. `capabilities` del motor local:
   - `inference_backend: chatterbox`
   - `real_backend_device: cpu`
   - `gpu_available: false` (desde el runtime actual)
2. PyTorch instalado en `.venv`:
   - `torch 2.6.0+cpu`
   - `torch.cuda.is_available() = False`
3. GPU detectada por sistema:
   - `NVIDIA GeForce RTX 5070 (12 GB)`
   - `NVIDIA GeForce GTX 1060 6GB`
4. Conclusion tecnica:
   - Hay GPU fisica disponible, pero el entorno actual no la usa por wheel CPU-only.

## 4) Datos medidos (benchmark real Fase A)

### 4.1 Serie larga (muestras representativas)
| Caso | Endpoint | Idioma | Palabras | Audio (s) | Tiempo total (s) | RTF |
|---|---|---:|---:|---:|---:|---:|
| Warmup corto | `tts` | es | 20 | 7.04 | 44.13 | 6.27 |
| Medio | `tts` | es | 150 | 40.00 | 319.58 | 7.99 |
| Medio | `tts` | en | 150 | 40.00 | 307.47 | 7.69 |
| Largo | `tts` | es | 300 | 27.16 | 249.71 | 9.19 |
| Largo | `tts` | en | 300 | 40.00 | 356.80 | 8.92 |
| Medio | `clone` | es | 150 | 40.00 | 293.10 | 7.33 |
| Medio | `clone` | en | 150 | 40.00 | 289.29 | 7.23 |
| Largo | `clone` | es | 300 | 33.20 | 284.87 | 8.58 |
| Largo | `clone` | en | 300 | 40.00 | 343.68 | 8.59 |

Promedios:
1. `tts`: RTF medio `8.01x`
2. `clone`: RTF medio `7.93x`

### 4.2 Serie corta de control
| Caso | Endpoint | Audio (s) | Tiempo total (s) | RTF |
|---|---:|---:|---:|---:|
| Control corto | `tts` | 5.76 | 33.83 | 5.87 |
| Control corto | `clone` | 5.20 | 30.10 | 5.79 |

Interpretacion:
1. Estado actual CPU: generar 1 minuto de audio equivale aprox. a `6-9` minutos de computo.
2. Sin GPU activa, la experiencia de clonacion larga seguira percibiendose lenta aunque el flujo sea estable.

## 5) Descarga/cache: comparacion estructural

### 5.1 Tamano de artefactos relevantes
1. `onnx-community/chatterbox-multilingual-ONNX/onnx`: **4.98 GB**
2. `ResembleAI/chatterbox` repo completo: **9.61 GB**
3. `Xenova/mms-tts-spa/onnx`: **211 MB**
4. `Xenova/mms-tts-eng/onnx`: **211 MB**
5. `Xenova/speecht5_tts/onnx`: **3.16 GB**

### 5.2 Tiempo teorico de descarga (solo red)
| Modelo | 25 Mbps | 50 Mbps | 100 Mbps | 300 Mbps | 600 Mbps |
|---|---:|---:|---:|---:|---:|
| Chatterbox multilingual ONNX (4.98 GB) | 28.5 min | 14.3 min | 7.1 min | 2.4 min | 1.2 min |
| SpeechT5 ONNX (3.16 GB) | 18.1 min | 9.0 min | 4.5 min | 1.5 min | 0.8 min |
| MMS idioma unico (211 MB) | 1.2 min | 0.6 min | 0.3 min | 0.1 min | ~0.0 min |

Lectura practica:
1. En navegador, los modelos pesados penalizan mucho la primera experiencia.
2. En ventana local, la cache es mas controlable y persistente, y no depende de politicas del navegador.

## 6) Diferencia "WebGPU navegador" vs "ventana local"

1. Navegador:
   - Ventaja: cero instalacion.
   - Riesgo: WebGPU experimental, fallback posible a WASM, limites de memoria/cache de navegador.
2. Ventana local:
   - Ventaja: control total del runtime, logs ricos, cache persistente, posibilidad real de CUDA.
   - Coste: instalacion inicial y mantenimiento de entorno.
3. Conclusion:
   - Para modelo ligero, el navegador es suficiente.
   - Para clonacion/modelo pesado, la ventana local es la via correcta de producto.

## 7) Proyeccion de ganancia al activar CUDA (escenarios)

Base observada: `RTF ~8x` (CPU actual).

| Escenario hipotetico | RTF estimado | 1 min de audio | 2 min de audio |
|---|---:|---:|---:|
| CPU actual | 8.0x | 480 s | 960 s |
| GPU con speedup 2x | 4.0x | 240 s | 480 s |
| GPU con speedup 4x | 2.0x | 120 s | 240 s |
| GPU con speedup 6x | 1.33x | 80 s | 160 s |

Nota:
1. Esta tabla es proyeccion matematica sobre la baseline medida, no benchmark final CUDA.
2. La siguiente validacion real sera repetir exactamente los mismos casos tras habilitar `torch` con CUDA.

## 8) Decision de producto tras Fase A

1. Mantener estrategia dual:
   - `Modo rapido` para entrada inmediata.
   - `Modo Pro local` para calidad y clonacion seria.
2. Prioridad tecnica inmediata para retorno:
   - Habilitar CUDA real en el motor local.
3. Prioridad UX inmediata para retorno:
   - Telemetria en vivo de inferencia (`sampling %`) via polling para eliminar sensacion de bloqueo.

## 9) Continuacion planificada (estado actualizado)

1. Fase B (ejecutada el 22 de marzo de 2026):
   - `events/poll` + `request_id` + logs/progreso por fase en web y ventana.
2. Fase C (ejecutada el 22 de marzo de 2026):
   - Panel avanzado de calidad: `cfg_weight`, `exaggeration`, `temperature`, `seed`.
3. Mantener "calidad primero":
   - No introducir control de velocidad artificial en esta fase.

## 10) Supuestos y limites de esta entrega

1. La comparativa pesada web vs ventana se basa en:
   - Datos reales de backend local medido.
   - Tamanos oficiales de modelos en repositorios.
2. No se ejecuto benchmark automatico de navegador WebGPU end-to-end dentro de este entorno de terminal.
3. La decision sigue siendo valida porque el bloqueo principal detectado es inequivoco: runtime local en CPU-only.

## 11) Fuentes

1. Chatterbox oficial (README/model zoo/tips):
   https://raw.githubusercontent.com/resemble-ai/chatterbox/master/README.md
2. Transformers.js (CPU por defecto en browser, WebGPU opcional/experimental):
   https://raw.githubusercontent.com/huggingface/transformers.js/main/README.md
3. Chatterbox multilingual ONNX (tamano carpeta y archivos):
   https://huggingface.co/onnx-community/chatterbox-multilingual-ONNX/tree/main/onnx
4. ResembleAI/chatterbox (tamano repo y pesos):
   https://huggingface.co/ResembleAI/chatterbox/tree/main
5. MMS ES ONNX (tamano):
   https://huggingface.co/Xenova/mms-tts-spa/tree/main/onnx
6. MMS EN ONNX (tamano):
   https://huggingface.co/Xenova/mms-tts-eng/tree/main/onnx
7. SpeechT5 ONNX (tamano):
   https://huggingface.co/Xenova/speecht5_tts/tree/main/onnx

## 12) Estado de cierre de fase

1. Fase A: **completada** (informe listo para retomar).
2. Fase B: **completada** (telemetria de inferencia y polling en vivo operativos).
3. Fase C: **completada** (panel avanzado conectado con backend de inferencia).

## 13) Informe de ejecucion Fase B (22 de marzo de 2026)

1. Backend (`local_engine_windows/daemon.py`):
   - Se agrego `request_id` opcional en `TTSRequest`.
   - Se implemento buffer de eventos en memoria con cursor incremental (`events`, `events_cursor`).
   - Se implementaron helpers: `_normalize_request_id`, `_emit_event`, `_emit_sampling_progress`, `_clear_sampling_progress`, `poll_events`.
   - Se agrego hook de progreso de sampling sobre `tqdm` de Chatterbox (`_sampling_hook_context`) para emitir porcentaje durante inferencia.
   - `tts` y `clone` ahora emiten fases: `start`, `initializing_backend`, `preparing_reference` (clone), `sampling`, `serializing_audio`, `completed`, `failed`.
   - Se agrego endpoint autenticado `GET /events/poll` con `cursor`, `request_id`, `limit`.
   - `POST /tts` y `POST /clone` aceptan/normalizan `request_id` y devuelven header `X-Request-Id`.

2. Frontend (`src/localEngineClient.ts`):
   - Se extiende `SpeechRequest` con `request_id`.
   - Se agregan tipos `EngineEvent` y `EventPollResponse`.
   - Se implementa `pollEvents(baseUrl, token, { cursor, request_id, limit })`.
   - `clone` incluye `request_id` en `FormData` cuando existe.

3. Frontend (`src/App.tsx`):
   - `generatePro` crea `requestId` por solicitud.
   - Se inicia polling en vivo contra `/events/poll` cada ~450 ms durante TTS/clone.
   - Se reflejan fases y progreso en consola (`addLog`) y barra de progreso (`setProgress`).
   - Se hace flush final de eventos al terminar para evitar perder mensajes de cierre.

4. Documentacion:
   - `local_engine_windows/README.md` actualizado con el endpoint `GET /events/poll`.

5. Validaciones ejecutadas:
   - `python -m py_compile local_engine_windows/daemon.py local_engine_windows/app.py` OK.
   - `npm run lint` OK.
   - `npm run build` OK.
   - Smoke test local con `TestClient` (backend en `mock`) verificando:
     - correlacion por `request_id`,
     - fases `start/sampling/completed`,
     - respuesta con header `X-Request-Id`.

## 14) Informe de ejecucion Fase C (22 de marzo de 2026)

1. Backend (`local_engine_windows/daemon.py`):
   - `POST /tts` y `POST /clone` aceptan parametros opcionales: `cfg_weight`, `exaggeration`, `temperature`, `seed`.
   - Validacion de rangos y errores tipados (`INVALID_GENERATION_PARAM`) para evitar requests invalidos.
   - Integracion real con `ChatterboxMultilingualTTS.generate(...)` pasando esos parametros.
   - Soporte de semilla por request (`seed`) aplicando `torch.manual_seed` de forma acotada al request.
   - Trazabilidad ampliada: los eventos/logs incluyen los parametros efectivos usados en inferencia.

2. Frontend cliente (`src/localEngineClient.ts`):
   - `SpeechRequest` y `CloneRequest` extienden payload con los parametros avanzados.
   - `/clone` envía esos parametros en `FormData` cuando estan presentes.

3. Frontend UI (`src/App.tsx`, `src/index.css`):
   - Nuevo panel "Ajustes avanzados Pro" con controles para `cfg_weight`, `exaggeration`, `temperature` y `seed`.
   - Boton para restablecer valores recomendados.
   - Validacion previa en cliente y logging de parametros activos por request.

4. Resultado de producto:
   - Fase C queda cerrada: el usuario puede ajustar calidad y reproducibilidad directamente desde la UI Pro sin tocar codigo.

# Plan Modo Pro Local: TTS y Clonacion de Maxima Calidad

Fecha: 21 de marzo de 2026

## 1) Resumen ejecutivo

Este proyecto se ejecutara con arquitectura dual:

1. `Modo Rapido` (browser-only): inferencia en navegador para arranque inmediato.
2. `Modo Pro` (motor local instalable): inferencia pesada en hardware del usuario para maxima calidad y clonacion real.

Railway se mantiene como `control plane` (frontend, auth, configuracion y producto), no como plano de inferencia pesada.

## 2) Decisiones cerradas para MVP

1. Plataforma inicial: **Windows first**.
2. Stack del motor local: **Python + FastAPI**.
3. Modelo pro inicial: **perfil unico multilingual (ES/EN)**.
4. Descarga de modelos: **bajo demanda**.
5. Conexion web -> motor: **localhost directo**.
6. Seguridad local: **token local + Origin estricto**.
7. UX de confianza: **app visible; cerrar ventana = parar motor y conexion**.
8. Railway: **sin relay de inferencia en MVP**.

## 3) Estado actual y gap

Estado actual del frontend:

1. Motor browser con SpeechT5/MMS.
2. Clonacion predefinida por perfiles fijos.
3. Sin clonacion real por audio de referencia de usuario.

Gap a cerrar:

1. Integrar flujo `Modo Pro` con deteccion de motor local.
2. Añadir subida de audio de referencia para `POST /clone`.
3. Gestionar ciclo completo de modelo (download/load/status).

## 4) Arquitectura objetivo

## 4.1 Frontend (Railway)

1. Selector `Modo Rapido / Modo Pro`.
2. En `Modo Pro`, deteccion de motor local (`GET /health`).
3. Estados visibles: `no_instalado`, `detenido`, `descargando`, `listo`, `error`.
4. Fallback robusto a `Modo Rapido` si el motor local no esta activo.

## 4.2 Motor local instalable (Windows)

1. App con ventana minima (estado, logs, iniciar/parar).
2. Daemon FastAPI embebido en `127.0.0.1`.
3. Politica de ciclo de vida: cerrar ventana => detener servidor local.
4. Cache local de modelo y descarga resumible.

## 4.3 API local MVP

Endpoints requeridos:

1. `GET /health`
2. `GET /version`
3. `GET /capabilities`
4. `POST /models/download`
5. `GET /models/download/status`
6. `POST /models/load`
7. `POST /tts`
8. `POST /clone`
9. `POST /models/unload`

Errores tipados requeridos:

1. `MODEL_NOT_DOWNLOADED`
2. `MODEL_LOADING`
3. `GPU_UNAVAILABLE`
4. `INVALID_REFERENCE_AUDIO`

## 5) Seguridad y privacidad local

1. Bind solo a `127.0.0.1`.
2. `Authorization: Bearer <token_local>` obligatorio para endpoints privados.
3. Validacion estricta de `Origin` (dominio Railway + localhost dev).
4. Sin exposicion de endpoints administrativos fuera de loopback.
5. Sin envio de audio/texto a servidor para inferencia pro.

## 6) Plan de implementacion

## Fase A: Documentacion y trazabilidad

1. Documento principal: `plan_modo_pro_local.md`.
2. Referencias internas actualizadas desde planes legacy.

## Fase B: Frontend Modo Pro

1. Selector de modo.
2. Cliente API para motor local.
3. Pantalla de estado del motor.
4. Flujo download/load/status.
5. Subida de referencia y llamada a `/clone`.
6. Fallback a modo browser-only.

## Fase C: Motor local Windows

1. Daemon FastAPI con endpoints MVP.
2. Descarga resumible y cache por perfil.
3. Token local y Origin allowlist.
4. UI minima visible para confianza y control.

## 7) Plan de pruebas

1. Documentacion: todos los enlaces internos apuntan a `plan_modo_pro_local.md`.
2. Flujo Pro: instalacion limpia -> deteccion web -> descarga -> load -> primera clonacion.
3. Seguridad:
   - sin token => `401`
   - origin no permitido => `403`
   - sin acceso fuera de loopback
4. Confiabilidad UX:
   - cerrar app local detiene API
   - reabrir app restaura conexion sin reiniciar web
5. Fallback:
   - si falla motor local, la app sigue funcionando en modo rapido

## 8) Riesgos principales y mitigacion

1. Modelo pesado:
   - mitigar con descarga bajo demanda + perfil unico inicial.
2. Variabilidad de hardware:
   - detectar capacidades y emitir diagnostico claro.
3. Restricciones navegador->localhost:
   - flujo explicito de permisos y errores de conexion legibles.

## 9) Fuentes de referencia

1. Chatterbox oficial: https://github.com/resemble-ai/chatterbox
2. Chatterbox Turbo ONNX: https://huggingface.co/ResembleAI/chatterbox-turbo-ONNX
3. Chatterbox ONNX community: https://huggingface.co/onnx-community/chatterbox-ONNX
4. Chatterbox multilingual ONNX: https://huggingface.co/onnx-community/chatterbox-multilingual-ONNX
5. ONNX Runtime Web: https://onnxruntime.ai/docs/get-started/with-javascript/web.html
6. ONNX Runtime WebGPU: https://onnxruntime.ai/docs/tutorials/web/ep-webgpu.html
7. Transformers.js docs: https://huggingface.co/docs/transformers.js
8. Chrome Local Network Access: https://developer.chrome.com/blog/local-network-access


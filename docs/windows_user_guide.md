# Guia Rapida Usuario Windows (Modo Pro)

Estado del producto: **publico y funcional**, en **preview tecnica**.

## Expectativa correcta para esta version

Esto no es una promesa de compatibilidad universal con cualquier PC.
Es un lanzamiento tecnico publico que estamos endureciendo por iteraciones.

En este entorno nos funciona bien:

1. Windows 10/11
2. Chrome/Edge
3. Launcher local (`ZIP + BAT`) + web HTTPS

Si estas fuera de ese entorno, puede fallar. Si falla, no pasa nada: envia diagnostico y lo tratamos.

Compatibilidad soportada v1:

1. Windows 10/11
2. Chrome o Edge
3. Launcher local (`ZIP + BAT`)

No soportado oficialmente en v1:

1. Safari / Firefox
2. macOS / Linux
3. `.exe` legacy como ruta principal

## Flujo recomendado

1. Entra en la web publica (Railway con HTTPS).
2. Descarga `studio-voice-local-windows-preview.zip`.
3. Extrae el ZIP.
4. Ejecuta `Install Studio Voice Local Engine.bat`.
5. El instalador movera automaticamente el motor a una ruta corta en `%LOCALAPPDATA%` (normal y esperado).
6. Acepta permiso local del navegador si Chrome/Edge lo pide.
7. Pulsa `Comprobar motor` en la web.
8. Pulsa `Preparar modo Pro`.
9. Genera audio.

## Que significa cada estado

1. `GPU real`: inferencia real en GPU local.
2. `CPU real`: inferencia real, pero degradada por falta de GPU utilizable.
3. `modo compatible/mock`: no es clonacion real.
4. `permiso local bloqueado`: Chrome/Edge no dejo acceso HTTPS -> localhost.
5. `origin bloqueado`: el dominio web no esta permitido por el daemon local.

## Soporte rapido

1. Exporta diagnostico con `Export Studio Voice Diagnostics.bat`.
2. Ve a `/support` en la web.
3. Pega el contenido del `support_bundle.json`.
4. Anade pasos exactos, error textual y entorno (Windows/navegador/GPU).

Mensaje recomendado al usuario final:

1. "Bajo estas condiciones, funciona bien."
2. "Si no te funciona en tu equipo, reportalo con logs y lo resolvemos."

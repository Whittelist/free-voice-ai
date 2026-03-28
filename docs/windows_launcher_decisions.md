# Decisiones del Launcher Windows (por que y para que)

Este documento explica cambios tecnicos del launcher `ZIP + BAT` para que el equipo pueda comunicarlos en la web publica sin ambiguedad.

## Problemas reales detectados

1. `WinError 206` en Windows (ruta demasiado larga) al instalar dependencias Pro desde rutas profundas como `Descargas\...`.
2. `ModuleNotFoundError: tkinter` en el runtime portable (Python embebido no siempre incluye Tk).
3. Instalaciones que parecian "cerrarse sin pasar nada" cuando el daemon no llegaba a `/health`.

## Cambios implementados

1. **Instalacion en ruta corta automatica**
   - `Install Studio Voice Local Engine.bat` ahora copia el launcher a:
   - `%LOCALAPPDATA%\StudioVoiceLocal\engine`
   - Desde ahi ejecuta `install_local_engine.ps1`.
   - Objetivo: reducir longitud de rutas y evitar `WinError 206` para usuarios que ejecutan desde `Descargas`.

2. **Reejecucion desde instalacion local**
   - `run_portable_engine.bat` detecta si existe instalacion local en ruta corta.
   - Si existe y el launcher se ejecuto desde otra carpeta, se reejecuta automaticamente desde la ruta corta.
   - Objetivo: mantener ejecucion estable y evitar reinstalaciones en rutas largas por error.

3. **Fallback headless cuando falta tkinter**
   - Si `import tkinter` falla en runtime portable, el launcher arranca `daemon.py` en modo headless.
   - Objetivo: no bloquear el motor local por dependencia de UI en runtimes embebidos.

4. **Fail-fast en instalacion cuando no hay health**
   - `install_local_engine.ps1` ahora falla de forma explicita si el daemon no confirma `/health` a tiempo.
   - Tambien informa si el proceso launcher se cerro prematuramente.
   - Objetivo: evitar cierres silenciosos y mejorar el diagnostico.

5. **Unblock automatico de archivos descargados**
   - `Install Studio Voice Local Engine.bat` ejecuta `Unblock-File` en origen y en ruta activa.
   - Objetivo: reducir friccion por `Zone.Identifier`/MOTW en equipos con politicas `RemoteSigned`.

6. **Log de bootstrap del instalador**
   - El instalador escribe trazas tempranas en `%USERPROFILE%\.studio_voice_local\logs\install-bootstrap-*.log`.
   - Objetivo: diagnosticar casos donde "no se abre" o "se cierra instantaneamente".

## Impacto en experiencia de usuario

1. El usuario puede descargar en `Descargas` y ejecutar `Install Studio Voice Local Engine.bat`.
2. El flujo se autoajusta a una ruta corta interna para mejorar compatibilidad.
3. Si hay error real, se muestra de forma visible y con ruta de logs.

## Que comunicar en la web

Mensaje recomendado:

1. "El launcher se instala automaticamente en una ruta local optimizada de Windows para evitar errores de rutas largas."
2. "Puedes ejecutar el instalador desde Descargas; el sistema se autoajusta."
3. "Si falla, usa el boton de soporte y adjunta logs/diagnostico."

## Rutas de soporte relevantes

1. Config/token: `%USERPROFILE%\.studio_voice_local\`
2. Logs: `%USERPROFILE%\.studio_voice_local\logs`
3. Diagnostico: `Export Studio Voice Diagnostics.bat`

## Limites conocidos (fase technical preview)

1. Soporte oficial v1: Windows 10/11 + Chrome/Edge.
2. Safari/Firefox/macOS/Linux no estan en alcance de soporte oficial inicial.
3. El objetivo es robustez iterativa basada en reportes reales, no promesa de cero bugs en v1.

# Auditoria de tecnicas recomendadas (instalador Windows)

Objetivo: validar si estamos aplicando tecnicas robustas para que el instalador funcione en escenarios reales (descarga en `Descargas`, doble clic, entornos heterogeneos).

## Fuentes base consultadas

1. Python embeddable package (oficial):
   - https://docs.python.org/3/using/windows.html#the-embeddable-package
2. Windows MAX_PATH / rutas largas (oficial):
   - https://learn.microsoft.com/en-us/windows/win32/fileio/maximum-file-path-limitation
3. Execution Policy en PowerShell (oficial):
   - https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_execution_policies
4. Unblock-File / Zone.Identifier (oficial):
   - https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.utility/unblock-file

## Checklist de hardening

1. Tecnica: evitar rutas largas de usuario moviendo instalacion a ruta corta.
   - Estado: **APLICADO**
   - Implementacion: `Install Studio Voice Local Engine.bat` copia automaticamente a `%LOCALAPPDATA%\StudioVoiceLocal\engine`.
   - Motivo: reduce riesgo de `WinError 206`.

2. Tecnica: no depender de `tkinter` en runtime embebido.
   - Estado: **APLICADO**
   - Implementacion: `run_portable_engine.bat` hace fallback a `daemon.py` (headless) si falla `import tkinter`.
   - Motivo: el embeddable package es minimo y no incluye Tcl/Tk.

3. Tecnica: no depender de politica global de PowerShell del usuario.
   - Estado: **APLICADO**
   - Implementacion: scripts lanzados con `-ExecutionPolicy Bypass`.
   - Motivo: evita bloqueos por `Restricted/RemoteSigned` en equipos de usuarios.

4. Tecnica: tratar archivos descargados con marca de internet (MOTW / Zone.Identifier).
   - Estado: **APLICADO**
   - Implementacion: `Install Studio Voice Local Engine.bat` ejecuta `Unblock-File` recursivo en origen y ruta activa.
   - Motivo: reduce friccion por bloqueos de archivos descargados.

5. Tecnica: fallar de forma explicita si el daemon no levanta.
   - Estado: **APLICADO**
   - Implementacion: `install_local_engine.ps1` valida `/health`; si falla devuelve error claro y no deja falso positivo.
   - Motivo: evita "se cerro y no paso nada".

6. Tecnica: logging persistente desde bootstrap.
   - Estado: **APLICADO**
   - Implementacion: `Install Studio Voice Local Engine.bat` escribe log de bootstrap en `%USERPROFILE%\.studio_voice_local\logs`.
   - Motivo: soporte reproducible sin depender de captura manual.

7. Tecnica: ejecutar desde instalacion conocida/estable.
   - Estado: **APLICADO**
   - Implementacion: `run_portable_engine.bat` reejecuta desde `%LOCALAPPDATA%\StudioVoiceLocal\engine` si detecta instalacion local.
   - Motivo: coherencia de entorno y menor riesgo por rutas arbitrarias.

8. Tecnica: vendoring de dependencias en embeddable (en lugar de `pip install` en primer arranque).
   - Estado: **PARCIAL / PENDIENTE**
   - Situacion actual: instalamos deps en primer arranque.
   - Riesgo: tiempo largo de bootstrap y errores de red/antivirus/permisos.
   - Recomendacion: empaquetar wheelhouse offline y resolver localmente.

9. Tecnica: firma de codigo y reputacion de instalador.
   - Estado: **PENDIENTE**
   - Situacion actual: `ZIP + BAT` sin firma.
   - Riesgo: mas friccion SmartScreen/AV en equipos de usuarios.
   - Recomendacion: fase siguiente de hardening (code signing + timestamp).

10. Tecnica: verificacion de integridad antes de instalar.
   - Estado: **PARCIAL**
   - Situacion actual: generamos `checksums.sha256`, pero no verificamos automaticamente antes de instalar.
   - Recomendacion: agregar check previo en instalador wrapper.

## Conclusiones operativas

1. Para el problema actual ("descargar en Descargas y ejecutar"), ya aplicamos mitigaciones clave:
   - ruta corta automatica,
   - unblock automatico,
   - fallback headless,
   - fail-fast con logs.
2. Para endurecimiento siguiente (v2), las prioridades son:
   - vendoring offline de dependencias,
   - verificacion automatica de checksums,
   - firma de artefactos.

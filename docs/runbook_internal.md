# Runbook Interno: Railway + ZIP Launcher

## Variables de entorno

Frontend/build:

1. `VITE_PUBLIC_APP_ORIGIN`
2. `VITE_LOCAL_ENGINE_WINDOWS_INSTALLER_URL`

Backend Railway:

1. `DATABASE_URL`
2. `BUG_REPORTS_ADMIN_PASSWORD`
3. `BUG_REPORTS_SESSION_SECRET`
4. `PUBLIC_WEB_ORIGIN` (documental)

Launcher/package:

1. `STUDIO_VOICE_PUBLIC_WEB_URL`
2. `STUDIO_VOICE_ALLOWED_ORIGINS` (opcional)

## Flujo de release

1. Build web: `npm run build`.
2. Build ZIP Windows:
   `powershell -ExecutionPolicy Bypass -File .\local_engine_windows\build_portable_release.ps1 -PublicWebUrl "https://TU-DOMINIO"`
3. Publica ZIP en GitHub Releases como:
   `studio-voice-local-windows-preview.zip`.
4. Deploy web a Railway.
5. Verifica que `VITE_LOCAL_ENGINE_WINDOWS_INSTALLER_URL` apunta a:
   `https://github.com/Whittelist/free-voice-ai/releases/latest/download/studio-voice-local-windows-preview.zip`

## Validacion minima post-deploy

1. `/` carga correctamente.
2. `/support` permite crear bug report.
3. `/support/admin` permite login y listado.
4. API:
   `POST /api/bug-reports`
   `GET /api/admin/bug-reports`
   `POST /api/admin/bug-reports/:id/status`

## Clasificacion operativa de tickets

1. `launcher`:
   instalacion/runtime/arranque local.
2. `web`:
   permisos HTTPS->localhost, UI, token, origin.
3. `other`:
   casos raros.

Estados:

1. `new`
2. `reviewing`
3. `resolved`

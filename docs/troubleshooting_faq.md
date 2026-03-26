# FAQ / Troubleshooting (Modo Pro)

## `MISSING_TOKEN`

Causa: se llamo a `/capabilities` o `/tts` sin token local.

Accion:

1. Lee el token en `%USERPROFILE%\.studio_voice_local\api_token.txt`.
2. Pegalo en el campo token de la web.

## `ORIGIN_NOT_ALLOWED`

Causa: el dominio de la web no esta en `allowed_origins`.

Accion:

1. Reejecuta `Install Studio Voice Local Engine.bat`.
2. Verifica `config.json` en `%USERPROFILE%\.studio_voice_local\config.json`.
3. Debe incluir el dominio publico y `localhost`.

## `Failed to fetch` desde web HTTPS

Causa frecuente: bloqueo de acceso local (Private Network Access).

Accion:

1. Usa Chrome/Edge.
2. Permite acceso local cuando el navegador lo pida.
3. Pulsa `Permitir acceso local` y luego `Comprobar motor`.

## Sale `CPU real` en lugar de `GPU real`

Causa: drivers/CUDA/torch no compatibles con la GPU o runtime.

Accion:

1. Comprueba `/capabilities` y `real_backend_torch_info`.
2. Reinstala o fuerza setup (`LOCAL_ENGINE_FORCE_SETUP=1`).
3. Si persiste, reporta bug con `support_bundle.json`.

## Puerto ocupado

Sintoma: el launcher indica que `127.0.0.1:57641` esta ocupado.

Accion:

1. Cierra la instancia existente del daemon.
2. O cambia `LOCAL_ENGINE_PORT`.

## Runtime corrupto

Accion:

1. Ejecuta el launcher con `LOCAL_ENGINE_FORCE_SETUP=1`.
2. Si no recupera, borra la carpeta del runtime portable y relanza.
3. Exporta diagnostico y reporta en `/support`.

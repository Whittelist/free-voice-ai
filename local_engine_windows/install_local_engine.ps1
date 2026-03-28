param(
  [string[]]$AllowedOrigins = @(),
  [string]$AllowedOriginRegex = '^https://[a-z0-9-]+(\.up)?\.railway\.app$|^http://localhost(:\d+)?$|^http://127\.0\.0\.1(:\d+)?$',
  [string]$LauncherBat = "run_local_engine.bat",
  [string]$PublicWebUrl = "",
  [int]$WaitForHealthSeconds = 45,
  [string]$EngineUrl = "http://127.0.0.1:57641",
  [switch]$OpenWeb,
  [switch]$AllowUnhealthyLaunch,
  [switch]$NoLaunch,
  [switch]$NoDesktopShortcut
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$dataDir = Join-Path $env:USERPROFILE ".studio_voice_local"
$configPath = Join-Path $dataDir "config.json"
$defaultOrigins = @(
  "http://localhost:5173",
  "http://127.0.0.1:5173"
)

$envOrigins = @()
if ($env:STUDIO_VOICE_ALLOWED_ORIGINS) {
  $envOrigins = $env:STUDIO_VOICE_ALLOWED_ORIGINS.Split(",") | ForEach-Object { $_.Trim() } | Where-Object { $_ }
}

$normalizedAllowedOrigins = @(
  $AllowedOrigins |
    ForEach-Object { $_ -split "," } |
    ForEach-Object { $_.Trim() }
) | Where-Object { $_ }

$resolvedOrigins = @($defaultOrigins + $envOrigins + $normalizedAllowedOrigins) |
  Where-Object { $_ -and $_.Trim() } |
  Select-Object -Unique

New-Item -ItemType Directory -Path $dataDir -Force | Out-Null

$config = [ordered]@{
  allowed_origins = $resolvedOrigins
  allowed_origin_regex = $AllowedOriginRegex
  launcher_bat = $LauncherBat
  public_web_url = $PublicWebUrl
  installed_at_utc = (Get-Date).ToUniversalTime().ToString("o")
}
$config | ConvertTo-Json | Set-Content -Path $configPath -Encoding UTF8

Write-Host "[INFO] Configuracion persistente escrita en $configPath"
Write-Host "[INFO] Origins permitidos: $($resolvedOrigins -join ', ')"

if (-not $NoDesktopShortcut) {
  $desktopPath = [Environment]::GetFolderPath("Desktop")
  $shortcutPath = Join-Path $desktopPath "Studio Voice Local Engine.lnk"
  $launcherPath = Join-Path $PSScriptRoot $LauncherBat
  if (-not (Test-Path $launcherPath)) {
    throw "No existe el launcher solicitado: $launcherPath"
  }
  $shell = New-Object -ComObject WScript.Shell
  $shortcut = $shell.CreateShortcut($shortcutPath)
  $shortcut.TargetPath = $launcherPath
  $shortcut.WorkingDirectory = $PSScriptRoot
  $shortcut.Description = "Studio Voice Local Engine"
  $shortcut.Save()
  Write-Host "[INFO] Acceso directo creado en $shortcutPath"
}

if (-not $NoLaunch) {
  $launcherPath = Join-Path $PSScriptRoot $LauncherBat
  if (-not (Test-Path $launcherPath)) {
    throw "No existe el launcher solicitado: $launcherPath"
  }
  Write-Host "[INFO] Lanzando el daemon local..."
  $launcherProcess = Start-Process -FilePath $launcherPath -WorkingDirectory $PSScriptRoot -PassThru
  Write-Host "[INFO] Esperando health en $EngineUrl/health (max ${WaitForHealthSeconds}s)..."
  Write-Host "[INFO] Si falla, revisa logs en $dataDir\\logs"

  $deadline = (Get-Date).AddSeconds([Math]::Max(5, $WaitForHealthSeconds))
  $healthy = $false
  $launcherExited = $false
  $launcherExitCode = $null
  while ((Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 700
    try {
      if ($launcherProcess.HasExited) {
        $launcherExited = $true
        $launcherExitCode = $launcherProcess.ExitCode
        break
      }
    } catch {
      # If we cannot inspect process state, continue health checks.
    }

    try {
      $health = Invoke-RestMethod -UseBasicParsing -Uri "$EngineUrl/health" -Method Get -TimeoutSec 3
      if ($health.status -eq "ok") {
        $healthy = $true
        break
      }
    } catch {
      # keep retrying
    }
  }

  if ($healthy) {
    Write-Host "[INFO] Health OK en $EngineUrl/health"
    $tokenPath = Join-Path $dataDir "api_token.txt"
    if (Test-Path $tokenPath) {
      $token = (Get-Content -Raw $tokenPath).Trim()
      if ($token) {
        Write-Host "[INFO] Token local: $token"
      }
    }
  } else {
    $message = "El daemon no confirmo health en $WaitForHealthSeconds segundos."
    if ($launcherExited) {
      $message += " El launcher se cerro (exit code: $launcherExitCode)."
    }
    $message += " Revisa la ventana del launcher y logs en $dataDir\\logs."
    if ($AllowUnhealthyLaunch) {
      Write-Warning $message
    } else {
      throw $message
    }
  }
} else {
  Write-Host "[INFO] Instalacion lista. Ejecuta $LauncherBat cuando quieras iniciar el daemon."
}

if ($OpenWeb -and -not [string]::IsNullOrWhiteSpace($PublicWebUrl)) {
  if ($PublicWebUrl -match '^https?://') {
    Write-Host "[INFO] Abriendo web publica: $PublicWebUrl"
    Start-Process -FilePath $PublicWebUrl | Out-Null
  } else {
    Write-Warning "PUBLIC_WEB_URL ignorada porque no es una URL http(s) valida: $PublicWebUrl"
  }
}

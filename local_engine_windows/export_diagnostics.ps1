param(
  [string]$OutputDir = "",
  [string]$EngineUrl = "http://127.0.0.1:57641",
  [int]$LogTailLines = 300
)

$ErrorActionPreference = "Stop"

$dataDir = Join-Path $env:USERPROFILE ".studio_voice_local"
if ([string]::IsNullOrWhiteSpace($OutputDir)) {
  $OutputDir = $dataDir
}
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

$configPath = Join-Path $dataDir "config.json"
$tokenPath = Join-Path $dataDir "api_token.txt"
$logsDir = Join-Path $dataDir "logs"
$timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMdd-HHmmss")
$bundlePath = Join-Path $OutputDir "support_bundle_$timestamp.json"
$zipPath = Join-Path $OutputDir "support_bundle_$timestamp.zip"

$config = $null
if (Test-Path $configPath) {
  try {
    $config = Get-Content -Raw $configPath | ConvertFrom-Json
  } catch {
    $config = @{ parse_error = "config_json_invalid"; raw = (Get-Content -Raw $configPath) }
  }
}

$token = $null
if (Test-Path $tokenPath) {
  $token = (Get-Content -Raw $tokenPath).Trim()
}

$health = $null
$capabilities = $null
$engineError = $null

try {
  $health = Invoke-RestMethod -UseBasicParsing -Uri "$EngineUrl/health" -Method Get -TimeoutSec 5
  if ($token) {
    $headers = @{ Authorization = "Bearer $token" }
    $capabilities = Invoke-RestMethod -UseBasicParsing -Uri "$EngineUrl/capabilities" -Method Get -Headers $headers -TimeoutSec 10
  } else {
    $engineError = "No se encontro token local para consultar /capabilities."
  }
} catch {
  $engineError = $_.Exception.Message
}

$latestLogs = @()
$logFiles = @()
if (Test-Path $logsDir) {
  $logFiles = Get-ChildItem -Path $logsDir -Filter "*.log" -File | Sort-Object LastWriteTime -Descending
  foreach ($file in $logFiles | Select-Object -First 5) {
    $tail = Get-Content -Path $file.FullName -Tail $LogTailLines
    $latestLogs += [ordered]@{
      file = $file.Name
      last_write_time_utc = $file.LastWriteTimeUtc.ToString("o")
      tail = $tail
    }
  }
}

$launcherVersion = "unknown"
$initPath = Join-Path $PSScriptRoot "__init__.py"
if (Test-Path $initPath) {
  $initRaw = Get-Content -Raw $initPath
  $m = [regex]::Match($initRaw, "__version__\s*=\s*""([^""]+)""")
  if ($m.Success) {
    $launcherVersion = $m.Groups[1].Value
  }
}

$bundle = [ordered]@{
  generated_at_utc = (Get-Date).ToUniversalTime().ToString("o")
  host = $env:COMPUTERNAME
  os = (Get-CimInstance Win32_OperatingSystem | Select-Object Caption, Version, BuildNumber)
  launcher_version = $launcherVersion
  expected_public_web_url = if ($config -and $config.public_web_url) { $config.public_web_url } else { $null }
  engine_url = $EngineUrl
  engine_health = $health
  capabilities = $capabilities
  runtime_class = if ($capabilities) { $capabilities.runtime_class } else { $null }
  quality_tier = if ($capabilities) { $capabilities.quality_tier } else { $null }
  device = if ($capabilities) { $capabilities.real_backend_device } else { $null }
  torch_info = if ($capabilities) { $capabilities.real_backend_torch_info } else { $null }
  allowed_origins = if ($capabilities) { $capabilities.allowed_origins } else { $null }
  config = $config
  engine_error = $engineError
  logs = $latestLogs
}

$bundle | ConvertTo-Json -Depth 15 | Set-Content -Path $bundlePath -Encoding UTF8

$tmpZipDir = Join-Path $OutputDir "support_bundle_tmp_$timestamp"
New-Item -ItemType Directory -Path $tmpZipDir -Force | Out-Null
Copy-Item -Path $bundlePath -Destination (Join-Path $tmpZipDir "support_bundle.json") -Force

if ($logFiles.Count -gt 0) {
  $zipLogsDir = Join-Path $tmpZipDir "logs"
  New-Item -ItemType Directory -Path $zipLogsDir -Force | Out-Null
  foreach ($file in $logFiles | Select-Object -First 5) {
    Copy-Item -Path $file.FullName -Destination (Join-Path $zipLogsDir $file.Name) -Force
  }
}

if (Test-Path $zipPath) {
  Remove-Item -Path $zipPath -Force
}
Compress-Archive -Path (Join-Path $tmpZipDir "*") -DestinationPath $zipPath -Force
Remove-Item -Path $tmpZipDir -Recurse -Force

Write-Host "[INFO] JSON: $bundlePath"
Write-Host "[INFO] ZIP:  $zipPath"

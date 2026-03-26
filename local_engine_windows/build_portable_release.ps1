param(
  [string]$OutputDir = "",
  [string]$PublicWebUrl = "",
  [string]$PythonEmbedVersion = "3.11.9",
  [switch]$SkipPromptDownload
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Get-LocalEngineVersion {
  $initPath = Join-Path $PSScriptRoot "__init__.py"
  if (-not (Test-Path $initPath)) {
    return "0.1.0"
  }
  $raw = Get-Content -Raw $initPath
  $match = [regex]::Match($raw, "__version__\s*=\s*""([^""]+)""")
  if ($match.Success) {
    return $match.Groups[1].Value
  }
  return "0.1.0"
}

if ([string]::IsNullOrWhiteSpace($OutputDir)) {
  $OutputDir = Join-Path (Split-Path $PSScriptRoot -Parent) "releases"
}
if ([string]::IsNullOrWhiteSpace($PublicWebUrl)) {
  $PublicWebUrl = $env:VITE_PUBLIC_APP_ORIGIN
}
if ([string]::IsNullOrWhiteSpace($PublicWebUrl)) {
  $PublicWebUrl = "https://your-domain.example.com"
}

$version = Get-LocalEngineVersion
$packageName = "studio-voice-local-windows-preview"
$buildRoot = Join-Path $PSScriptRoot "build\portable_release"
$cacheDir = Join-Path $buildRoot "cache"
$stagingRoot = Join-Path $buildRoot $packageName
$runtimeDir = Join-Path $stagingRoot "runtime\python311"
$assetsPromptDir = Join-Path $stagingRoot "assets\default_prompts"
$pythonZipName = "python-$PythonEmbedVersion-embed-amd64.zip"
$pythonZipPath = Join-Path $cacheDir $pythonZipName
$pythonUrl = "https://www.python.org/ftp/python/$PythonEmbedVersion/$pythonZipName"

New-Item -ItemType Directory -Path $cacheDir -Force | Out-Null
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
if (Test-Path $stagingRoot) {
  Remove-Item -Path $stagingRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null

if (-not (Test-Path $pythonZipPath)) {
  Write-Host "[INFO] Descargando Python embeddable: $pythonUrl"
  Invoke-WebRequest -UseBasicParsing -Uri $pythonUrl -OutFile $pythonZipPath
} else {
  Write-Host "[INFO] Reutilizando cache: $pythonZipPath"
}

Write-Host "[INFO] Extrayendo Python embeddable..."
Expand-Archive -Path $pythonZipPath -DestinationPath $runtimeDir -Force

$pthPath = Join-Path $runtimeDir "python311._pth"
$pthContent = @"
python311.zip
.
Lib
Lib\site-packages
import site
"@
Set-Content -Path $pthPath -Value $pthContent -Encoding ASCII
New-Item -ItemType Directory -Path (Join-Path $runtimeDir "Lib\site-packages") -Force | Out-Null

$filesToCopy = @(
  "app.py",
  "daemon.py",
  "__init__.py",
  "requirements.txt",
  "requirements_pro.txt",
  "run_portable_engine.bat",
  "install_local_engine.ps1",
  "export_diagnostics.ps1",
  "Install Studio Voice Local Engine.bat",
  "Export Studio Voice Diagnostics.bat"
)

foreach ($file in $filesToCopy) {
  $src = Join-Path $PSScriptRoot $file
  if (-not (Test-Path $src)) {
    throw "Falta archivo requerido para release: $file"
  }
  Copy-Item -Path $src -Destination (Join-Path $stagingRoot $file) -Force
}

New-Item -ItemType Directory -Path $assetsPromptDir -Force | Out-Null
if (-not $SkipPromptDownload) {
  $promptSources = @(
    @{ Name = "es_f1.flac"; Url = "https://storage.googleapis.com/chatterbox-demo-samples/mtl_prompts/es_f1.flac" },
    @{ Name = "en_f1.flac"; Url = "https://storage.googleapis.com/chatterbox-demo-samples/mtl_prompts/en_f1.flac" }
  )
  foreach ($prompt in $promptSources) {
    $target = Join-Path $assetsPromptDir $prompt.Name
    Write-Host "[INFO] Descargando prompt por defecto: $($prompt.Name)"
    Invoke-WebRequest -UseBasicParsing -Uri $prompt.Url -OutFile $target
  }
}

$installBatPath = Join-Path $stagingRoot "Install Studio Voice Local Engine.bat"
$installContent = Get-Content -Raw $installBatPath
$installContent = $installContent.Replace("https://your-domain.example.com", $PublicWebUrl)
Set-Content -Path $installBatPath -Value $installContent -Encoding ASCII

$manifest = [ordered]@{
  package_name = $packageName
  version = $version
  generated_at_utc = (Get-Date).ToUniversalTime().ToString("o")
  public_web_url = $PublicWebUrl
  python_embeddable_version = $PythonEmbedVersion
  entrypoints = @(
    "Install Studio Voice Local Engine.bat",
    "run_portable_engine.bat",
    "Export Studio Voice Diagnostics.bat"
  )
}
$manifest | ConvertTo-Json -Depth 6 | Set-Content -Path (Join-Path $stagingRoot "manifest.json") -Encoding UTF8

$checksumLines = @()
$stagingPrefix = ($stagingRoot.TrimEnd('\') + '\')
Get-ChildItem -Path $stagingRoot -Recurse -File | ForEach-Object {
  $hash = Get-FileHash -Path $_.FullName -Algorithm SHA256
  if ($_.FullName.StartsWith($stagingPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    $relativePath = $_.FullName.Substring($stagingPrefix.Length).Replace("\", "/")
  } else {
    $relativePath = $_.Name
  }
  $checksumLines += "$($hash.Hash) *$relativePath"
}
Set-Content -Path (Join-Path $stagingRoot "checksums.sha256") -Value $checksumLines -Encoding ASCII

$zipPath = Join-Path $OutputDir "$packageName.zip"
if (Test-Path $zipPath) {
  Remove-Item -Path $zipPath -Force
}
Compress-Archive -Path (Join-Path $stagingRoot "*") -DestinationPath $zipPath -Force

Write-Host "[INFO] ZIP generado: $zipPath"
Write-Host "[INFO] Manifest: $(Join-Path $stagingRoot 'manifest.json')"
Write-Host "[INFO] Checksums: $(Join-Path $stagingRoot 'checksums.sha256')"

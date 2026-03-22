param(
  [switch]$OneFile
)

$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

if (-not (Test-Path ".venv\\Scripts\\python.exe")) {
  python -m venv .venv
}

$py = ".venv\\Scripts\\python.exe"

& $py -m pip install --upgrade pip
& $py -m pip install -r requirements.txt pyinstaller

if ($OneFile) {
  & $py -m PyInstaller `
    --name "StudioVoiceLocalEngine-OneFile" `
    --noconfirm `
    --windowed `
    --onefile `
    --clean `
    app.py
  Write-Host "Build completed. Output: dist/StudioVoiceLocalEngine-OneFile.exe"
} else {
  & $py -m PyInstaller `
    --name "StudioVoiceLocalEngine" `
    --noconfirm `
    --windowed `
    --clean `
    app.py
  Write-Host "Build completed. Output: dist/StudioVoiceLocalEngine (folder)"
}

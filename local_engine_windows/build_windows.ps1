$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

if (-not (Test-Path ".venv\Scripts\python.exe")) {
  python -m venv .venv
}

. .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller

pyinstaller `
  --name "StudioVoiceLocalEngine" `
  --noconfirm `
  --windowed `
  --clean `
  app.py

Write-Host "Build completed. Output: dist/StudioVoiceLocalEngine"


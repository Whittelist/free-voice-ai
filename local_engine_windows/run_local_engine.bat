@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [INFO] Creating virtual environment...
  python -m venv .venv
)

echo [INFO] Activating environment...
call ".venv\Scripts\activate.bat"

echo [INFO] Installing dependencies...
python -m pip install -r requirements.txt

echo [INFO] Starting Studio Voice Local Engine...
python app.py

endlocal


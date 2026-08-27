@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo O programa ainda nao foi instalado. Execute INSTALAR.bat primeiro.
  pause
  exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" -m live_splitter

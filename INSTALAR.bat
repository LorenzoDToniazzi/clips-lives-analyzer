@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install_windows.ps1"
if errorlevel 1 (
  echo.
  echo A instalacao encontrou um erro. Leia a mensagem acima.
  pause
  exit /b 1
)
echo.
echo Instalacao concluida.
pause

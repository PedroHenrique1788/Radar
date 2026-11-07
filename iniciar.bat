@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Execute instalar.bat primeiro.
  pause
  exit /b 1
)
.venv\Scripts\python.exe -m radar
if errorlevel 1 pause

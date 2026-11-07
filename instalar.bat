@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>&1
if errorlevel 1 (
  echo Instale Python 3.11 ou 3.12 de python.org, incluindo o Python Launcher e Tcl/Tk.
  pause
  exit /b 1
)
py -3.12 -m venv .venv
if errorlevel 1 py -3.11 -m venv .venv
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
  pause
  exit /b 1
)
where ffmpeg >nul 2>&1
if errorlevel 1 echo AVISO: instale FFmpeg e adicione a pasta bin ao PATH antes de iniciar.
echo Instalacao concluida. Execute iniciar.bat.
pause

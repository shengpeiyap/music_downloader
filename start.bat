@echo off
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
  echo Python 3.10 or newer is required. Install Python from https://www.python.org/downloads/ and try again.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Preparing MusicDesk for first use...
  py -3 -m venv .venv
  if errorlevel 1 goto :error
)

if not exist ".venv\ffmpeg-ready" (
  echo Installing the audio converter. This downloads FFmpeg automatically and may take a few minutes.
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 goto :error
  type nul > ".venv\ffmpeg-ready"
)

start "" http://127.0.0.1:8765
".venv\Scripts\python.exe" app.py
exit /b 0

:error
echo Setup failed. Check your internet connection and Python installation, then run start.bat again.
pause
exit /b 1

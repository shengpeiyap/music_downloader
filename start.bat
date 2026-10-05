@echo off
cd /d "%~dp0"

:: 强制控制台使用 UTF-8 编码，防止日文/中文文件名在控制台输出时报错崩溃
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

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
  echo Installing audio converter and tools...
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
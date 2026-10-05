@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Create the project environment first by running start.bat.
  exit /b 1
)

".venv\Scripts\python.exe" -m pip install -r requirements-build.txt
if errorlevel 1 goto :error

".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onedir --windowed ^
  --name MusicDesk --icon icon.ico --add-data "index.html;." --add-data "icon.ico;." ^
  --collect-all imageio_ffmpeg --collect-all PIL --collect-all mutagen ^
  --collect-all musicbrainzngs --collect-all webview launcher.py
if errorlevel 1 goto :error

".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --console ^
  --name yt-dlp --collect-all yt_dlp yt_dlp_launcher.py
if errorlevel 1 goto :error

".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --console ^
  --name spotdl --collect-all spotdl --collect-all pykakasi spotdl_launcher.py
if errorlevel 1 goto :error

copy /y "dist\yt-dlp.exe" "dist\MusicDesk\yt-dlp.exe" >nul
copy /y "dist\spotdl.exe" "dist\MusicDesk\spotdl.exe" >nul
if errorlevel 1 goto :error

powershell -NoProfile -Command "Compress-Archive -Path 'dist\MusicDesk\*' -DestinationPath 'dist\MusicDesk-portable.zip' -CompressionLevel Fastest -Force"
if errorlevel 1 goto :error

echo.
echo Build complete: dist\MusicDesk\MusicDesk.exe
echo Portable package: dist\MusicDesk-portable.zip
exit /b 0

:error
echo Build failed. Review the error above.
exit /b 1

# MusicDesk

A local music metadata viewer and audio format converter.

## Features

- Read public title, publisher, and thumbnail metadata from Spotify track and YouTube Music / YouTube video share links.
- Convert local audio to MP3, M4A, FLAC, WAV, or OGG.
- Read, edit, and export local audio tags, including embedded lyrics and album artwork.
- Does not download copyrighted audio from streaming services. Convert only files you own or are authorized to process.
- Uploaded audio is processed in a temporary local folder and removed after conversion.

## Windows quick start

Install Python 3.10 or newer, then double-click `start.bat`. On first launch it creates a project-local Python environment and installs the audio conversion package. That package includes an FFmpeg executable, so you do not need to find an FFmpeg download or edit PATH. First-time setup needs an internet connection. Later launches reuse the installed files.

The app opens at <http://127.0.0.1:8765>. Metadata lookup needs an internet connection; audio conversion runs locally.

## Portable Windows app

To build a desktop package, run `build_windows.bat` after the first `start.bat` setup. It creates `dist\MusicDesk-portable.zip`; extract it and open `MusicDesk.exe`. The executable opens a native window when the Microsoft Edge WebView2 runtime is available, and falls back to the default browser otherwise. The package includes the app icon, yt-dlp, SpotDL, and FFmpeg. Building requires an internet connection to install the packaging tools.

`icon.ico` is also used as the website favicon. The app still needs an internet connection for public music metadata and lyrics.

In the native desktop window, downloading or converting a file opens the Windows Save As dialog. It starts in the Downloads folder, and you can choose another location. If the app falls back to your browser, the browser controls the download location.

## macOS / Linux

Install Python 3.10 or newer, then run:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

The bundled FFmpeg package is selected automatically on supported platforms. An FFmpeg executable already on PATH is used as a fallback.

## Tests

```sh
python -m unittest -v
```

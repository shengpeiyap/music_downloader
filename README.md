# MusicDesk

A local music metadata viewer and audio format converter.

## Features

- Read public title, publisher, and thumbnail metadata from Spotify track and YouTube Music / YouTube video share links.
- Convert local audio to MP3, M4A, FLAC, WAV, or OGG.
- Does not download copyrighted audio from streaming services. Convert only files you own or are authorized to process.
- Uploaded audio is processed in a temporary local folder and removed after conversion.

## Windows quick start

Install Python 3.10 or newer, then double-click `start.bat`. On first launch it creates a project-local Python environment and installs the audio conversion package. That package includes an FFmpeg executable, so you do not need to find an FFmpeg download or edit PATH. First-time setup needs an internet connection. Later launches reuse the installed files.

The app opens at <http://127.0.0.1:8765>. Metadata lookup needs an internet connection; audio conversion runs locally.

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

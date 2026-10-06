# MusicDesk

A local music metadata viewer and audio format converter.

## Features

- Read public title, publisher, and thumbnail metadata from Spotify track and YouTube Music / YouTube video share links.
- Convert local audio to MP3, M4A, FLAC, WAV, or OGG.
- Read, edit, and export local audio tags, including embedded lyrics and album artwork.
- Search public track metadata by `artist - title` or title alone in the tag editor.
- Drag audio into the custom tag editor or local player; manage playlist entries and playback without browser-native controls.
- Does not download copyrighted audio from streaming services. Convert only files you own or are authorized to process.
- Uploaded audio is processed in a temporary local folder and removed after conversion.

## Windows quick start

Install Python 3.10 or newer, then double-click `start.bat`. On first launch it creates a project-local Python environment and installs the audio conversion package. That package includes an FFmpeg executable, so you do not need to find an FFmpeg download or edit PATH. First-time setup needs an internet connection. Later launches reuse the installed files.

The app opens at <http://127.0.0.1:8765>. Metadata lookup needs an internet connection; audio conversion runs locally.

## Portable Windows app

To build a desktop package, run `build_windows.bat` after the first `start.bat` setup. It creates `dist\MusicDesk-portable.zip`; extract it and open `MusicDesk.exe`. The executable opens a native window when the Microsoft Edge WebView2 runtime is available, and falls back to the default browser otherwise. The package includes the app icon, yt-dlp, SpotDL, and FFmpeg. Building requires an internet connection to install the packaging tools.

`icon.ico` is also used as the website favicon. The app still needs an internet connection for public music metadata and lyrics.

In the native desktop window, downloading or converting a file opens the Windows Save As dialog. It starts in the Downloads folder, and you can choose another location. If the app falls back to your browser, the browser controls the download location.

## Android preview

The `android` directory contains an Android Studio WebView project. Open that directory in Android Studio and build the `app` debug variant. The Android preview supports selecting individual audio files or recursively importing a folder, with Library and Now Playing views, song/artist/album/folder/favorites filters, a draggable queue sheet, a mini-player, and sequential/repeat-one/repeat-all/shuffle playback. Selected folder permissions and URIs are persisted, so the app rescans the saved folders on launch. Folder scans send lightweight tag data to the WebView; embedded artwork is decoded and resized only for the track being played to keep large libraries within memory limits. Folder import reads title, artist, album, and embedded cover where Android can decode them; embedded lyrics remain available for files selected through the file picker. Folder-imported audio is copied to the app cache only when played; removing a track does not remove the user's original file. Metadata lookup, network lyrics, downloads, format conversion, and custom tag export still require the desktop Python API. In Android they remain locked until the saved API connection is verified, and are re-locked if the connection or pairing token stops working.

The Android build requires JDK 17 and Android SDK Platform 36. The project bundles the current `index.html` and default cover during the Gradle build, so they do not need to be copied by hand. Embedded tag and lyric reading uses the existing jsmediatags CDN script and therefore needs an internet connection on first load; playback itself stays on the phone.

To use online metadata lookup, downloads, format conversion, or custom tag export in Android, connect the phone and computer to the same trusted Wi-Fi network and start the desktop API with `start_lan.bat` (or run `python app.py --lan`). The desktop terminal shows its LAN address and a one-run pairing token. Enter the computer's LAN address (not `127.0.0.1`, which points to the phone itself) and token in the Android app's Online tab, then tap **Connect**. The LAN-mode app page remains available at `http://127.0.0.1:8765` on the computer itself; remote devices only receive authenticated API access. Keep the desktop window open while using these features. The token changes each run unless you explicitly supply one with `--token`. Windows Firewall may ask to allow Python on your private network. Android saves returned files through the system folder picker. Do not expose this HTTP service to public networks.

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

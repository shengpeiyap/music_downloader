# MusicDesk

> A local-first music library and player with metadata, lyrics, audio conversion, and tagging tools for Windows and Android.
>
> [简体中文](README.zh-CN.md) · English

[![CI](https://github.com/shengpeiyap/music_downloader/actions/workflows/ci.yml/badge.svg)](https://github.com/shengpeiyap/music_downloader/actions/workflows/ci.yml)
[![Latest release](https://img.shields.io/github/v/release/shengpeiyap/music_downloader)](https://github.com/shengpeiyap/music_downloader/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

MusicDesk brings local playback, metadata lookup, lyric handling, audio conversion, and tag editing into one application. The Windows desktop app uses a Python service and web UI. The Android app uses a native shell and WebView, with Chaquopy for selected Python components. Online features depend on network access and third-party availability.

**Project status:** early-stage and under active development. Features and interfaces may change. Check the release notes before upgrading, and report reproducible issues with the steps and environment details requested in the issue templates.

## Features

- Local music library and player with search, favorites, playback queue, playback modes, and lyrics display.
- Metadata and lyric lookup from public data sources, plus public information from supported YouTube and Spotify links.
- Audio conversion to MP3, WAV, FLAC, OGG, or M4A; metadata, cover, and lyric editing; audio export.
- Desktop downloads through yt-dlp and SpotDL. Android capabilities and formats depend on local dependencies or an explicitly connected desktop service.
- Android folder import and playback, with optional LAN access to selected desktop processing features.

Metadata, embedded artwork, and synchronized lyrics are not supported uniformly across every media container. Third-party services, network policies, and format changes can affect lookup and downloads.

## Downloads

Get builds from [GitHub Releases](https://github.com/shengpeiyap/music_downloader/releases). The assets and limitations listed in each release are authoritative. Debug builds are for testing and are not production releases.

## Run from source

### Windows desktop

Requires Python 3.12 or newer. From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

Then open <http://127.0.0.1:8765>. You can also use the provided `start.bat` launcher.

### Android

Requires JDK 17, Android SDK Platform 36, and Python 3.14 for the Chaquopy build. From the repository root:

```powershell
cd android
.\gradlew.bat assembleDebug
```

For release builds and signing, follow the Android project documentation and release notes. Never commit a personal signing key or password.

## LAN access and privacy

The desktop service binds to the local loopback interface by default. LAN mode is intended for a trusted private Wi-Fi network and requires an access token. Do not expose the service port to the public internet or an untrusted network. Verify the device address and pairing token before connecting.

Local audio is processed on the device. Online lookup, download, and lyric features contact their respective third-party services when requested. When Android is connected to the desktop over LAN, the desktop handles the selected processing request. Review the privacy policies and terms of the services you use.

## Tests

Install dependencies from `requirements.txt` and use Node.js 20, then run from the repository root:

```powershell
python -m unittest test_app -v
python -m unittest discover -s android/app/src/test/python -v
node tests/test_android_search_fallback.js
node tests/test_android_processing_route.js
node tests/test_android_ui_gates.js
node tests/test_library_sort.js
```

GitHub Actions also compiles the Android Java app. To build it locally, run `gradlew.bat assembleDebug` from `android`. Test counts are intentionally omitted here because they change as coverage evolves; see the current CI run for results.

## Contributing

Bug reports and improvements are welcome. Please read the [contribution guide](CONTRIBUTING.md), [code of conduct](CODE_OF_CONDUCT.md), and [security policy](SECURITY.md). Do not disclose vulnerabilities in a public issue.

## Third-party components and licensing

MusicDesk source code is licensed under the [MIT License](LICENSE). Python, Android, and media-processing dependencies have their own licenses; bundled third-party binaries remain subject to their respective terms. Review those licenses and notices before redistributing or modifying a release package. MusicDesk is not affiliated with YouTube, Spotify, MusicBrainz, LRCLIB, or other third-party services.

## Copyright and acceptable use

Only process audio you own or are authorized to use, and follow local law and third-party service terms. MusicDesk does not grant rights to third-party content and cannot guarantee that external sources remain available.

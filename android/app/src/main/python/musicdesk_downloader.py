from __future__ import annotations

import base64
import json
import re
import shutil
import threading
import time
import unicodedata
import urllib.parse
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

import mutagen
import yt_dlp


_MB_LOCK = threading.Lock()
_MB_LAST_REQUEST = 0.0
_USER_AGENT = "MusicDesk/0.1 (https://github.com/shengpeiyap/music_downloader)"


def _validate_source(source: str) -> str:
    source = (source or "").strip()
    if not (source.startswith("https://") or source.startswith("http://") or source.startswith("ytsearch1:")):
        raise ValueError("只支持 HTTP(S) 音乐链接或 yt-dlp 关键词搜索。")
    return source


def _first_entry(info):
    if info and "entries" in info:
        return next((entry for entry in info["entries"] if entry), None)
    return info


def _artist(info):
    value = info.get("artist") or info.get("artists") or info.get("creator") or info.get("uploader") or info.get("channel")
    if isinstance(value, (list, tuple)):
        value = "; ".join(str(item) for item in value if item)
    return str(value or "")


def _image_mime(data: bytes):
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _download_thumbnail(url: str, destination: Path):
    if not url or not url.startswith(("https://", "http://")):
        return None
    try:
        request = Request(url, headers={"User-Agent": "MusicDesk/0.1"})
        with urlopen(request, timeout=20) as response:
            data = response.read(12 * 1024 * 1024 + 1)
        mime = _image_mime(data)
        if not mime or len(data) > 12 * 1024 * 1024:
            return None
        suffix = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}[mime]
        cover_path = destination / ("cover" + suffix)
        cover_path.write_bytes(data)
        return data, mime, cover_path
    except (OSError, URLError, ValueError):
        return None


def _metadata_cover(value: str, destination: Path):
    if not isinstance(value, str) or not value:
        return None
    if value.startswith("data:"):
        header, separator, encoded = value.partition(",")
        if not separator or not header.endswith(";base64"):
            return None
        try:
            data = base64.b64decode(encoded, validate=True)
        except (ValueError, base64.binascii.Error):
            return None
        mime = _image_mime(data)
        if not mime or len(data) > 12 * 1024 * 1024:
            return None
        cover_path = destination / ("cover.jpg" if mime == "image/jpeg" else "cover.png")
        cover_path.write_bytes(data)
        return data, mime, cover_path
    return _download_thumbnail(value, destination)


def _combine_metadata(info: dict, supplied_json: str):
    supplied = json.loads(supplied_json or "{}")
    if not isinstance(supplied, dict):
        supplied = {}
    result = dict(info)
    for key, source_keys in {
        "title": ("title",),
        "artist": ("artist",),
        "album": ("album",),
        "album_artist": ("albumartist", "album_artist"),
        "release_year": ("year", "release_year"),
        "lyrics": ("lyrics",),
    }.items():
        value = next((supplied.get(source_key) for source_key in source_keys if supplied.get(source_key)), None)
        if value:
            result[key] = value
    return result, supplied.get("cover") or supplied.get("thumbnail") or info.get("thumbnail") or ""


def _set_text_tag(tags, key, value):
    if value:
        tags[key] = [str(value)]


def _write_metadata(audio_path: Path, info: dict, cover):
    """Write yt-dlp fields and optional JPEG/PNG cover using Mutagen."""
    audio = mutagen.File(str(audio_path), easy=False)
    if audio is None:
        return False

    from mutagen.flac import FLAC, Picture
    from mutagen.id3 import APIC, TALB, TDRC, TIT2, TPE1, TPE2
    from mutagen.mp3 import MP3
    from mutagen.mp4 import MP4, MP4Cover

    title = info.get("track") or info.get("title") or audio_path.stem
    artist = _artist(info)
    album = info.get("album") or info.get("series") or ""
    album_artist = info.get("album_artist") or info.get("album_artists") or artist
    if isinstance(album_artist, (list, tuple)):
        album_artist = "; ".join(str(item) for item in album_artist if item)
    year = info.get("release_year") or info.get("release_date") or info.get("upload_date") or ""
    year = str(year)[:4] if year else ""
    lyrics = info.get("lyrics") or ""
    image, mime, _cover_path = cover if cover else (None, None, None)

    if isinstance(audio, MP3):
        if audio.tags is None:
            audio.add_tags()
        tags = audio.tags
        for frame in ("TIT2", "TPE1", "TALB", "TPE2", "TDRC", "APIC", "USLT"):
            tags.delall(frame)
        tags.add(TIT2(encoding=3, text=str(title)))
        if artist: tags.add(TPE1(encoding=3, text=artist))
        if album: tags.add(TALB(encoding=3, text=str(album)))
        if album_artist: tags.add(TPE2(encoding=3, text=str(album_artist)))
        if year: tags.add(TDRC(encoding=3, text=year))
        if lyrics:
            from mutagen.id3 import USLT
            tags.add(USLT(encoding=3, text=str(lyrics)))
        if image: tags.add(APIC(encoding=3, mime=mime, type=3, desc="Cover", data=image))
    elif isinstance(audio, MP4):
        if audio.tags is None:
            audio.add_tags()
        tags = audio.tags
        _set_text_tag(tags, "\xa9nam", title)
        _set_text_tag(tags, "\xa9ART", artist)
        _set_text_tag(tags, "\xa9alb", album)
        _set_text_tag(tags, "aART", album_artist)
        _set_text_tag(tags, "\xa9day", year)
        _set_text_tag(tags, "\xa9lyr", lyrics)
        if image and mime in {"image/jpeg", "image/png"}:
            image_format = MP4Cover.FORMAT_JPEG if mime == "image/jpeg" else MP4Cover.FORMAT_PNG
            tags["covr"] = [MP4Cover(image, imageformat=image_format)]
    elif isinstance(audio, FLAC):
        _set_text_tag(audio, "title", title)
        _set_text_tag(audio, "artist", artist)
        _set_text_tag(audio, "album", album)
        _set_text_tag(audio, "albumartist", album_artist)
        _set_text_tag(audio, "date", year)
        _set_text_tag(audio, "lyrics", lyrics)
        if image:
            picture = Picture()
            picture.data = image
            picture.type = 3
            picture.mime = mime
            picture.desc = "Cover"
            audio.clear_pictures()
            audio.add_picture(picture)
    elif hasattr(audio, "tags") and audio.tags is not None:
        # Ogg Vorbis/Opus comments and other Mutagen comment-based containers.
        tags = audio.tags
        _set_text_tag(tags, "title", title)
        _set_text_tag(tags, "artist", artist)
        _set_text_tag(tags, "album", album)
        _set_text_tag(tags, "albumartist", album_artist)
        _set_text_tag(tags, "date", year)
        _set_text_tag(tags, "lyrics", lyrics)
        if image:
            picture = Picture()
            picture.data = image
            picture.type = 3
            picture.mime = mime
            picture.desc = "Cover"
            tags["metadata_block_picture"] = [base64.b64encode(picture.write()).decode("ascii")]
    else:
        return False
    audio.save()
    return True


def package_audio_file(source_path: str, output_path: str, metadata_json: str, cover_path: str = ""):
    """Copy an audio file and write its tags locally without changing its codec/container."""
    source = Path(source_path)
    output = Path(output_path)
    if not source.is_file() or source.stat().st_size == 0:
        raise ValueError("所选音频文件为空或无法读取。")
    info = json.loads(metadata_json or "{}")
    if not isinstance(info, dict):
        raise ValueError("标签数据格式无效。")
    cover = None
    if cover_path:
        cover_file = Path(cover_path)
        if cover_file.is_file():
            data = cover_file.read_bytes()
            mime = "image/png" if cover_file.suffix.lower() == ".png" else "image/jpeg"
            cover = (data, mime, str(cover_file))
    shutil.copyfile(source, output)
    try:
        if not _write_metadata(output, info, cover):
            raise ValueError("此音频格式暂不支持写入标签。")
    except Exception:
        output.unlink(missing_ok=True)
        raise
    return str(output)


def read_local_audio_tags(source_path: str):
    audio = mutagen.File(str(source_path), easy=True)
    if audio is None:
        raise ValueError("无法识别此音频格式的标签。")
    def first(*keys):
        for key in keys:
            values = audio.get(key)
            if values:
                return str(values[0])
        return ""
    return json.dumps({
        "title": first("title"), "artist": first("artist"), "album": first("album"),
        "albumartist": first("albumartist", "album artist"), "year": first("date", "year"),
        "lyrics": first("lyrics", "unsyncedlyrics"),
    }, ensure_ascii=False)


def _json_request(url: str, timeout: int = 12):
    request = Request(url, headers={"User-Agent": _USER_AGENT, "Accept": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _musicbrainz_json(url: str):
    global _MB_LAST_REQUEST
    # MusicBrainz requires no more than one request per second per client/IP.
    with _MB_LOCK:
        delay = 1.05 - (time.monotonic() - _MB_LAST_REQUEST)
        if delay > 0:
            time.sleep(delay)
        try:
            return _json_request(url)
        finally:
            _MB_LAST_REQUEST = time.monotonic()


def _split_metadata_query(query: str):
    query = " ".join((query or "").split())
    match = re.match(r"^(.+?)\s+[-–—]\s+(.+)$", query)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return "", query


def _musicbrainz_artist_credit(credit):
    parts = []
    for item in credit or []:
        if isinstance(item, str):
            parts.append(item)
            continue
        if not isinstance(item, dict):
            continue
        artist = item.get("artist") or {}
        name = item.get("name") or artist.get("name") or ""
        if name:
            parts.append(str(name))
        if item.get("joinphrase") and parts:
            parts[-1] += str(item["joinphrase"])
    return "".join(parts).strip()


def _normalize_match(value: str):
    folded = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return "".join(character for character in folded if character.isalnum())


def search_musicbrainz(query: str) -> str:
    """Find title, artist, album, year, and cover directly from MusicBrainz."""
    artist, title = _split_metadata_query(query)
    if not title:
        raise ValueError("请输入“作者 - 标题”或歌曲标题。")
    escape = lambda value: value.replace("\\", "\\\\").replace('"', r'\"')
    terms = [f'recording:"{escape(title)}"']
    if artist:
        terms.append(f'artist:"{escape(artist)}"')
    params = urllib.parse.urlencode({"query": " AND ".join(terms), "fmt": "json", "limit": 15})
    data = _musicbrainz_json("https://musicbrainz.org/ws/2/recording/?" + params)
    recordings = data.get("recordings", []) if isinstance(data, dict) else []
    if not recordings:
        raise ValueError("MusicBrainz 没有找到匹配曲目；可以试试“作者 - 标题”格式。")

    wanted_title = _normalize_match(title)
    wanted_artist = _normalize_match(artist)
    recordings.sort(key=lambda item: (
        _normalize_match(item.get("title")) == wanted_title,
        bool(wanted_artist and wanted_artist in _normalize_match(_musicbrainz_artist_credit(item.get("artist-credit")))),
        int(item.get("score") or 0),
    ), reverse=True)
    selected = recordings[0]
    found_title = selected.get("title") or title
    found_artist = _musicbrainz_artist_credit(selected.get("artist-credit")) or artist
    releases = selected.get("releases") or []
    releases = [release for release in releases if isinstance(release, dict)]
    releases.sort(key=lambda release: (
        (release.get("release-group") or {}).get("primary-type") == "Album",
        not any(kind.casefold() in {"live", "remix"} for kind in (release.get("release-group") or {}).get("secondary-types", [])),
        bool(release.get("date")),
    ), reverse=True)
    album = ""
    year = ""
    cover = None
    for release in releases:
        album = release.get("title") or album
        year = str(release.get("date") or "")[:4] or year
        release_id = release.get("id")
        if release_id:
            cover = f"https://coverartarchive.org/release/{release_id}/front-500"
            break
    return json.dumps({
        "title": found_title,
        "artist": found_artist or "未知艺人",
        "album": album,
        "albumartist": found_artist,
        "year": year,
        "cover": cover,
        "provider": "MusicBrainz",
        "url": "",
        "keyword_search": True,
    }, ensure_ascii=False)


def _lyrics_normalize(value: str):
    return _normalize_match(value)


def lookup_lyrics(title: str, artist: str = "") -> str:
    """Look up synced or plain lyrics directly from LRCLIB without the PC API."""
    title = (title or "").strip()
    artist = (artist or "").strip()
    if not title:
        raise ValueError("请先读取歌曲信息。")
    clean_artist = "" if artist.casefold() in {"未知艺人", "unknown artist"} or _lyrics_normalize(artist) == _lyrics_normalize(title) else artist
    params = {"track_name": title}
    if clean_artist:
        params["artist_name"] = clean_artist
    try:
        data = _json_request("https://lrclib.net/api/get?" + urllib.parse.urlencode(params), timeout=8)
        lyrics = (data.get("syncedLyrics") or data.get("plainLyrics") or "").strip()
        if lyrics:
            return json.dumps({"lyrics": lyrics, "provider": "LRCLIB"}, ensure_ascii=False)
    except Exception:
        pass

    query = " ".join(part for part in (clean_artist, title) if part)
    try:
        results = _json_request("https://lrclib.net/api/search?" + urllib.parse.urlencode({"q": query}), timeout=8)
    except Exception as error:
        raise ValueError("LRCLIB 暂时无法访问；请稍后重试或连接电脑服务。") from error
    if not isinstance(results, list):
        results = []
    normalized_title = _lyrics_normalize(title)
    candidates = [item for item in results if _lyrics_normalize(item.get("trackName")) == normalized_title]
    if not candidates:
        candidates = [item for item in results if normalized_title and normalized_title in _lyrics_normalize(item.get("trackName"))]
    if clean_artist:
        matched = [item for item in candidates if _lyrics_normalize(clean_artist) in _lyrics_normalize(item.get("artistName"))]
        if matched:
            candidates = matched
    if not candidates:
        raise ValueError("公开歌词库中没有找到这首歌的歌词。")
    best = max(candidates, key=lambda item: (
        bool(item.get("syncedLyrics")),
        bool(item.get("plainLyrics")),
        bool(item.get("albumName")),
    ))
    lyrics = (best.get("syncedLyrics") or best.get("plainLyrics") or "").strip()
    if not lyrics:
        raise ValueError("公开歌词库中没有找到这首歌的歌词。")
    return json.dumps({"lyrics": lyrics, "provider": "LRCLIB"}, ensure_ascii=False)


def _resolve_info(source: str, download: bool):
    options = {"noplaylist": True, "quiet": True, "no_warnings": True, "cachedir": False}
    if not download:
        options["skip_download"] = True
    with yt_dlp.YoutubeDL(options) as downloader:
        info = _first_entry(downloader.extract_info(source, download=download))
    return info


def extract_metadata(source: str) -> str:
    """Resolve one public track or search result without downloading audio."""
    source = _validate_source(source)
    info = _resolve_info(source, download=False)
    if not info:
        raise RuntimeError("没有找到可用的曲目资料。")
    return json.dumps({
        "title": info.get("track") or info.get("title") or "未知曲目",
        "artist": _artist(info) or "未知艺人",
        "url": info.get("webpage_url") or info.get("original_url") or "",
        "thumbnail": info.get("thumbnail") or "",
        "duration": info.get("duration") or 0,
        "provider": "yt-dlp",
    }, ensure_ascii=False)


def download_audio(source: str, work_dir: str) -> str:
    """Backward-compatible entry point using only source-provided metadata."""
    return download_audio_with_metadata(source, work_dir, "{}")


def download_audio_with_metadata(source: str, work_dir: str, supplied_metadata_json: str) -> str:
    """Download one item and embed available title/artist/album/cover tags."""
    source = _validate_source(source)
    destination = Path(work_dir).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    options = {
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "outtmpl": str(destination / "%(title).120s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": False,
        "cachedir": False,
        "restrictfilenames": False,
        "writethumbnail": True,
    }

    with yt_dlp.YoutubeDL(options) as downloader:
        info = _first_entry(downloader.extract_info(source, download=True))
        if not info:
            raise RuntimeError("没有找到可下载的音频。")
        candidates = [Path(item["filepath"]) for item in info.get("requested_downloads", []) if item.get("filepath")]
        if not candidates:
            candidates = [Path(downloader.prepare_filename(info))]
        audio_path = next((item for item in candidates if item.is_file() and item.stat().st_size), None)
        if audio_path is None:
            audio_path = next((item for item in destination.iterdir() if item.is_file() and not item.name.endswith(".part") and item.name not in {"cover.jpg", "cover.png"}), None)
        if audio_path is None:
            raise RuntimeError("下载结束，但没有找到生成的音频文件。")

    tag_info, cover_source = _combine_metadata(info, supplied_metadata_json)
    # MusicBrainz/CAA entries may return a valid-looking URL even when no front
    # cover exists. If that request fails, try the source's yt-dlp thumbnail.
    cover_candidates = [cover_source, info.get("thumbnail") or ""]
    cover = None
    attempted = set()
    for candidate in cover_candidates:
        candidate = str(candidate or "")
        if not candidate or candidate in attempted:
            continue
        attempted.add(candidate)
        cover = _metadata_cover(candidate, destination)
        if cover:
            break
    if not cover:
        for thumbnail_path in sorted(destination.iterdir()):
            if thumbnail_path == audio_path or thumbnail_path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
                continue
            try:
                image = thumbnail_path.read_bytes()
            except OSError:
                continue
            mime = _image_mime(image)
            if mime and len(image) <= 12 * 1024 * 1024:
                cover = (image, mime, thumbnail_path)
                break
    try:
        tagged = _write_metadata(audio_path, tag_info, cover)
    except Exception:
        # Preserve a valid downloaded audio file if a container rejects optional tags.
        tagged = False
    title = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", "_", str(tag_info.get("title") or audio_path.stem)).strip()
    tag_metadata = {
        "title": tag_info.get("track") or tag_info.get("title") or title,
        "artist": _artist(tag_info),
        "album": tag_info.get("album") or tag_info.get("series") or "",
        "album_artist": tag_info.get("album_artist") or tag_info.get("album_artists") or _artist(tag_info),
        "release_year": tag_info.get("release_year") or tag_info.get("release_date") or tag_info.get("upload_date") or "",
        "lyrics": tag_info.get("lyrics") or "",
    }
    return json.dumps({
        "path": str(audio_path), "title": title, "metadata_embedded": tagged,
        "cover_embedded": bool(tagged and cover), "cover_path": str(cover[2]) if cover else "",
        "tag_metadata": tag_metadata,
    }, ensure_ascii=False)

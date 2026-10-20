from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

import mutagen
import yt_dlp


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
    return None


def _download_thumbnail(url: str, destination: Path):
    if not url or not url.startswith("https://"):
        return None
    try:
        request = Request(url, headers={"User-Agent": "MusicDesk/0.1"})
        with urlopen(request, timeout=20) as response:
            data = response.read(12 * 1024 * 1024 + 1)
        mime = _image_mime(data)
        if not mime or len(data) > 12 * 1024 * 1024:
            return None
        suffix = ".jpg" if mime == "image/jpeg" else ".png"
        cover_path = destination / ("cover" + suffix)
        cover_path.write_bytes(data)
        return data, mime, cover_path
    except (OSError, URLError, ValueError):
        return None


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
        if image:
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

    cover = _download_thumbnail(str(info.get("thumbnail") or ""), destination)
    try:
        tagged = _write_metadata(audio_path, info, cover)
    except Exception:
        # Preserve a valid downloaded audio file if a container rejects optional tags.
        tagged = False
    title = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", "_", str(info.get("title") or audio_path.stem)).strip()
    return json.dumps({"path": str(audio_path), "title": title, "metadata_embedded": tagged, "cover_embedded": bool(tagged and cover)}, ensure_ascii=False)

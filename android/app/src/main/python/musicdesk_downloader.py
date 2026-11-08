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

from musicdesk_core.lyrics import normalize_lyrics, parse_lrc_timestamps as _parse_lrc_timestamps
from musicdesk_core.metadata import build_musicbrainz_search_query, split_artist_title

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
        "track_number": ("track_num", "tracknumber", "track_number"),
        "disc_number": ("disc_num", "discnumber", "disc_number"),
        "genre": ("genre",),
        "composer": ("composer",),
    }.items():
        value = next((supplied.get(source_key) for source_key in source_keys if supplied.get(source_key)), None)
        if value:
            result[key] = value
    if result.get("lyrics"):
        result["lyrics"] = normalize_lyrics(str(result["lyrics"]), str(supplied.get("lyrics_format") or "auto"))
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
    from mutagen.id3 import APIC, TALB, TCOM, TCON, TDRC, TIT2, TPE1, TPE2, TPOS, TRCK
    from mutagen.mp3 import MP3
    from mutagen.mp4 import MP4, MP4Cover
    from mutagen.wave import WAVE

    title = info.get("track") or info.get("title") or audio_path.stem
    artist = _artist(info)
    album = info.get("album") or info.get("series") or ""
    album_artist = info.get("album_artist") or info.get("album_artists") or artist
    if isinstance(album_artist, (list, tuple)):
        album_artist = "; ".join(str(item) for item in album_artist if item)
    year = info.get("release_year") or info.get("release_date") or info.get("upload_date") or ""
    year = str(year)[:4] if year else ""
    lyrics = info.get("lyrics") or ""
    track_number = info.get("track_number") or ""
    disc_number = info.get("disc_number") or ""
    genre = info.get("genre") or ""
    composer = info.get("composer") or ""
    image, mime, _cover_path = cover if cover else (None, None, None)

    if isinstance(audio, MP3):
        if audio.tags is None:
            audio.add_tags()
        tags = audio.tags
        for frame in ("TIT2", "TPE1", "TALB", "TPE2", "TDRC", "TRCK", "TPOS", "TCON", "TCOM", "APIC", "USLT", "SYLT"):
            tags.delall(frame)
        tags.add(TIT2(encoding=3, text=str(title)))
        if artist: tags.add(TPE1(encoding=3, text=artist))
        if album: tags.add(TALB(encoding=3, text=str(album)))
        if album_artist: tags.add(TPE2(encoding=3, text=str(album_artist)))
        if year: tags.add(TDRC(encoding=3, text=year))
        if track_number: tags.add(TRCK(encoding=3, text=str(track_number)))
        if disc_number: tags.add(TPOS(encoding=3, text=str(disc_number)))
        if genre: tags.add(TCON(encoding=3, text=str(genre)))
        if composer: tags.add(TCOM(encoding=3, text=str(composer)))
        if lyrics:
            from mutagen.id3 import SYLT, USLT
            tags.add(USLT(encoding=3, text=str(lyrics)))
            synced = _parse_lrc_timestamps(str(lyrics))
            if synced:
                tags.add(SYLT(encoding=3, lang="eng", format=2, type=1, desc="", text=synced))
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
        _set_text_tag(tags, "\xa9gen", genre)
        _set_text_tag(tags, "\xa9wrt", composer)
        if track_number: tags["trkn"] = [(int(str(track_number).split("/")[0]), int(str(track_number).split("/")[1]) if "/" in str(track_number) else 0)]
        if disc_number: tags["disk"] = [(int(str(disc_number).split("/")[0]), int(str(disc_number).split("/")[1]) if "/" in str(disc_number) else 0)]
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
        _set_text_tag(audio, "tracknumber", track_number)
        _set_text_tag(audio, "discnumber", disc_number)
        _set_text_tag(audio, "genre", genre)
        _set_text_tag(audio, "composer", composer)
        _set_text_tag(audio, "lyrics", lyrics)
        if image:
            picture = Picture()
            picture.data = image
            picture.type = 3
            picture.mime = mime
            picture.desc = "Cover"
            audio.clear_pictures()
            audio.add_picture(picture)
    elif isinstance(audio, WAVE):
        if audio.tags is None:
            audio.add_tags()
        tags = audio.tags
        for frame in ("TIT2", "TPE1", "TALB", "TPE2", "TDRC", "TRCK", "TPOS", "TCON", "TCOM", "APIC", "USLT", "SYLT"):
            tags.delall(frame)
        tags.add(TIT2(encoding=3, text=str(title)))
        if artist: tags.add(TPE1(encoding=3, text=artist))
        if album: tags.add(TALB(encoding=3, text=str(album)))
        if album_artist: tags.add(TPE2(encoding=3, text=str(album_artist)))
        if year: tags.add(TDRC(encoding=3, text=year))
        if track_number: tags.add(TRCK(encoding=3, text=str(track_number)))
        if disc_number: tags.add(TPOS(encoding=3, text=str(disc_number)))
        if genre: tags.add(TCON(encoding=3, text=str(genre)))
        if composer: tags.add(TCOM(encoding=3, text=str(composer)))
        if lyrics:
            from mutagen.id3 import SYLT, USLT
            tags.add(USLT(encoding=3, text=str(lyrics)))
            synced = _parse_lrc_timestamps(str(lyrics))
            if synced:
                tags.add(SYLT(encoding=3, lang="eng", format=2, type=1, desc="", text=synced))
        if image: tags.add(APIC(encoding=3, mime=mime, type=3, desc="Cover", data=image))
    elif hasattr(audio, "tags") and audio.tags is not None:
        # Ogg Vorbis/Opus comments and other Mutagen comment-based containers.
        tags = audio.tags
        _set_text_tag(tags, "title", title)
        _set_text_tag(tags, "artist", artist)
        _set_text_tag(tags, "album", album)
        _set_text_tag(tags, "albumartist", album_artist)
        _set_text_tag(tags, "date", year)
        _set_text_tag(tags, "tracknumber", track_number)
        _set_text_tag(tags, "discnumber", disc_number)
        _set_text_tag(tags, "genre", genre)
        _set_text_tag(tags, "composer", composer)
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
    # The page sends short keys (track_num, disc_num, ...) and a lyrics_format; map and
    # normalize them here, before any output file is created.
    info, _supplied_cover = _combine_metadata(info, metadata_json)
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


def _read_embedded_lyrics(source_path: str) -> str:
    """Read lyrics that the easy tag interface hides (ID3 USLT/SYLT, MP4 ©lyr, Vorbis, ASF)."""
    try:
        raw = mutagen.File(str(source_path))
    except Exception:
        return ""
    tags = getattr(raw, "tags", None)
    if not tags:
        return ""
    def text_of(value):
        if isinstance(value, (list, tuple)):
            value = value[0] if value else ""
        return str(getattr(value, "text", value) or "")
    # ID3: unsynchronised lyrics are stored under keys such as "USLT::eng".
    for key in list(tags.keys()):
        if str(key).startswith("USLT"):
            text = text_of(tags[key])
            if text.strip():
                return text
    for key in list(tags.keys()):
        if str(key).startswith("SYLT"):
            frame = tags[key]
            lines = []
            for text, millis in getattr(frame, "text", []) or []:
                minutes, rest = divmod(int(millis), 60000)
                lines.append(f"[{minutes:02d}:{rest / 1000:05.2f}]{text}")
            if lines:
                return "\n".join(lines)
    for key in ("\xa9lyr", "lyrics", "LYRICS", "unsyncedlyrics", "UNSYNCEDLYRICS", "WM/Lyrics"):
        if key in tags:
            text = text_of(tags[key])
            if text.strip():
                return text
    return ""


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
        "lyrics": normalize_lyrics(first("lyrics", "unsyncedlyrics") or _read_embedded_lyrics(source_path)),
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
    return split_artist_title(query)


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
    query = build_musicbrainz_search_query(title, artist)
    params = urllib.parse.urlencode({"query": query, "fmt": "json", "limit": 15})
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


def _lyrics_title_variants(title: str):
    """Produce likely recording titles from video-style yt-dlp titles."""
    title = " ".join((title or "").split())
    variants = []

    def add(value):
        value = " ".join((value or "").strip().split()).strip(" -–—:：|")
        if value and _lyrics_normalize(value) not in {_lyrics_normalize(item) for item in variants}:
            variants.append(value)

    add(title)
    for left, right in (("「", "」"), ("『", "』"), ("《", "》"), ("“", "”"), ('"', '"'), ("'", "'")):
        start = title.find(left)
        end = title.find(right, start + len(left)) if start >= 0 else -1
        if start >= 0 and end > start + len(left):
            add(title[start + len(left):end])

    without_video_suffix = re.sub(
        r"\s*(?:[-|｜:：]\s*)?(?:(?:official|オフィシャル)\s*)?(?:music\s*video|video|mv|audio|lyric(?:s)?(?:\s*video)?|ミュージックビデオ|公式(?:\s*動画)?)\s*$",
        "",
        title,
        flags=re.IGNORECASE,
    )
    add(without_video_suffix)
    return variants


def _lyrics_artist_variants(artist: str):
    artist = " ".join((artist or "").split()).strip()
    if not artist or artist.casefold() in {"未知艺人", "unknown artist"}:
        return []
    variants = [artist]
    for part in re.split(r"\s*[,;|]\s*", artist):
        part = re.sub(r"\s*[-–—]\s*(?:topic|official channel)$", "", part, flags=re.IGNORECASE).strip()
        if part and _lyrics_normalize(part) not in {_lyrics_normalize(item) for item in variants}:
            variants.append(part)
    return variants


def lookup_lyrics(title: str, artist: str = "") -> str:
    """Look up synced or plain lyrics directly from LRCLIB without the PC API."""
    title = (title or "").strip()
    artist = (artist or "").strip()
    if not title:
        raise ValueError("请先读取歌曲信息。")
    title_variants = _lyrics_title_variants(title)
    artist_variants = [item for item in _lyrics_artist_variants(artist)
                       if _lyrics_normalize(item) != _lyrics_normalize(title)]
    clean_artist = artist_variants[0] if artist_variants else ""

    def lyrics_result(data):
        if not isinstance(data, dict):
            return ""
        synced = (data.get("syncedLyrics") or "").strip()
        lyrics = (synced or data.get("plainLyrics") or "").strip()
        if lyrics:
            return json.dumps({"lyrics": lyrics, "synced_lyrics": synced, "provider": "LRCLIB"}, ensure_ascii=False)
        return ""

    # First retain the original exact lookup, then try a quoted/cleaned song
    # title with the primary performer (e.g. a YouTube MV title and channel).
    exact_pairs = [(title, clean_artist)]
    if len(title_variants) > 1:
        primary_artist = artist_variants[1] if len(artist_variants) > 1 else clean_artist
        exact_pairs.extend((variant, primary_artist) for variant in title_variants[1:])
    for candidate_title, candidate_artist in exact_pairs:
        params = {"track_name": candidate_title}
        if candidate_artist:
            params["artist_name"] = candidate_artist
        try:
            result = lyrics_result(_json_request(
                "https://lrclib.net/api/get?" + urllib.parse.urlencode(params), timeout=8
            ))
            if result:
                return result
        except Exception:
            continue

    search_pairs = [(clean_artist, title)] if clean_artist else []
    search_pairs.extend((artist_variants[1], variant) for variant in title_variants[1:] if len(artist_variants) > 1)
    search_pairs.extend(("", variant) for variant in title_variants)
    search_queries = list(dict.fromkeys(
        " ".join(part for part in pair if part).strip() for pair in search_pairs
    ))
    normalized_titles = {_lyrics_normalize(item) for item in title_variants}
    candidates = []
    search_succeeded = False
    search_error = None
    for search_query in search_queries:
        try:
            results = _json_request(
                "https://lrclib.net/api/search?" + urllib.parse.urlencode({"q": search_query}), timeout=8
            )
            search_succeeded = True
        except Exception as error:
            search_error = error
            continue
        if not isinstance(results, list):
            continue
        candidates = [item for item in results if _lyrics_normalize(item.get("trackName")) in normalized_titles]
        if not candidates:
            candidates = [item for item in results if any(
                normalized and normalized in _lyrics_normalize(item.get("trackName"))
                for normalized in normalized_titles
            )]
        if candidates:
            break
    if not candidates and not search_succeeded and search_error:
        raise ValueError("LRCLIB 暂时无法访问；请稍后重试或连接电脑服务。") from search_error
    if clean_artist and candidates:
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
    synced_lyrics = (best.get("syncedLyrics") or "").strip()
    lyrics = (synced_lyrics or best.get("plainLyrics") or "").strip()
    if not lyrics:
        raise ValueError("公开歌词库中没有找到这首歌的歌词。")
    return json.dumps({"lyrics": lyrics, "synced_lyrics": synced_lyrics, "provider": "LRCLIB"}, ensure_ascii=False)


_BOT_CHECK = re.compile(r"confirm you.{0,3}re not a bot|sign in to confirm|not a bot", re.I)
# YouTube sometimes asks shared or mobile-network IPs to prove they are not a bot. Other player
# clients are often not challenged, so retry with them before giving up.
_YOUTUBE_CLIENT_FALLBACKS = (None, ["android_vr"], ["tv"], ["web_embedded"], ["mweb"])
BOT_CHECK_MESSAGE = ("YouTube 暂时要求验证身份（移动网络或共享网络上常见）。"
                     "请换一个 Wi‑Fi 或稍后重试，也可以连接电脑后再下载。")


def _run_with_client_fallbacks(options: dict, action):
    """Run action(options) and, on a bot check, retry with other YouTube player clients."""
    last_error = None
    for clients in _YOUTUBE_CLIENT_FALLBACKS:
        attempt = dict(options)
        if clients:
            attempt["extractor_args"] = {"youtube": {"player_client": clients}}
        try:
            return action(attempt)
        except Exception as error:
            if not _BOT_CHECK.search(str(error)):
                raise
            last_error = error
    raise RuntimeError(BOT_CHECK_MESSAGE) from last_error


def _resolve_info(source: str, download: bool):
    options = {"noplaylist": True, "quiet": True, "no_warnings": True, "cachedir": False}
    if not download:
        options["skip_download"] = True

    def action(attempt):
        with yt_dlp.YoutubeDL(attempt) as downloader:
            return _first_entry(downloader.extract_info(source, download=download))
    return _run_with_client_fallbacks(options, action)


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

    def action(attempt):
        with yt_dlp.YoutubeDL(attempt) as downloader:
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
            return info, audio_path

    info, audio_path = _run_with_client_fallbacks(options, action)

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

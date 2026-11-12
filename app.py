"""Local music metadata lookup and personal-audio converter with Player, Lyrics View & Custom Tag Editor integration."""
from __future__ import annotations

import base64
import json
import argparse
import importlib.util
import html as html_module
import hmac
import ipaddress
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import zipfile
import urllib.error
import urllib.parse
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from email.parser import BytesParser
from email.policy import default
from io import BytesIO

from PIL import Image
import musicbrainzngs
from desktop_media import resolve_selected_audio, serve_local_audio
from musicdesk_core import batch as batch_queue
from musicdesk_core import (
    SAFE_NAME,
    build_audio_trim_args,
    build_conversion_args,
    build_musicbrainz_search_query,
    limit_filename_length,
    make_tag_export_filename,
    describe_embedded_lyrics,
    normalize_lyrics,
    parse_metadata_search_query,
    parse_lrc_timestamps,
    parse_share_url,
    quote_musicbrainz_phrase,
    shift_lrc_timestamps,
)

musicbrainzngs.set_useragent("MusicDesk", "1.0", "https://github.com/musicdesk")

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
FORMATS = {"mp3": "audio/mpeg", "wav": "audio/wav", "flac": "audio/flac", "ogg": "audio/ogg", "m4a": "audio/mp4"}
MAX_UPLOAD = 150 * 1024 * 1024
MUSICDESK_API_VERSION = 1
MAX_API_JSON = 8192
MAX_COVER_BYTES = 8 * 1024 * 1024
SAFE_THUMBNAIL_HOSTS = {
    "i.ytimg.com", "img.youtube.com", "yt3.ggpht.com", "yt3.googleusercontent.com",
    "i.scdn.co", "coverartarchive.org",
}
MUSICDESK_API_CAPABILITIES = (
    "metadata", "search_metadata", "lyrics_text", "download", "convert",
    "parse_local_tag", "package_custom_tag", "playlist_batch",
)


def get_env_with_utf8() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    try:
        import imageio_ffmpeg
        ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
        if ffmpeg_bin and Path(ffmpeg_bin).is_file():
            ffmpeg_dir = str(Path(ffmpeg_bin).parent)
            env["PATH"] = ffmpeg_dir + os.pathsep + env.get("PATH", "")
    except Exception:
        pass
    return env


def load_music_tag(path: str):
    """Load metadata support on demand so the web app still starts on lean installs."""
    try:
        import music_tag
    except ImportError as exc:
        raise RuntimeError("音频标签功能缺少 music-tag 依赖，请重新安装 requirements.txt 中的依赖。") from exc
    return music_tag.load_file(path)


def read_music_metadata(path: str, filename: str) -> dict:
    audio = load_music_tag(path)
    def get_tag(name: str) -> str:
        # music-tag coerces some fields to int and raises on values such as "3/12" (FLAC/OGG).
        try:
            return str(audio[name]) if audio[name] else ""
        except (KeyError, ValueError, TypeError):
            return ""

    cover = None
    try:
        artwork = audio["artwork"]
        if artwork and artwork.values:
            image = artwork.first
            cover = f"data:{image.mime or 'image/jpeg'};base64," + base64.b64encode(image.data).decode("ascii")
    except (KeyError, IndexError, ValueError):
        # music-tag raises KeyError for an M4A that has no 'covr' atom; a missing cover is fine.
        cover = None

    def raw_vorbis_number(key: str) -> str:
        try:
            import mutagen
            easy = mutagen.File(path, easy=True)
            values = easy.get(key) if easy is not None else None
            return str(values[0]) if values else ""
        except Exception:
            return ""

    def number_with_total(number_key: str, total_key: str) -> str:
        number = get_tag(number_key)
        total = get_tag(total_key)
        if not number:
            # "3/12" style values are kept verbatim by FLAC/OGG; read them straight from the file.
            combined = raw_vorbis_number(number_key)
            if combined:
                return combined
        if number in {"", "0"}:
            return ""
        return f"{number}/{total}" if total not in {"", "0"} else number

    return {
        "filename": filename,
        "title": get_tag("title"),
        "artist": get_tag("artist"),
        "album": get_tag("album"),
        "albumartist": get_tag("albumartist"),
        "year": get_tag("year"),
        "track_num": number_with_total("tracknumber", "totaltracks"),
        "disc_num": number_with_total("discnumber", "totaldiscs"),
        "genre": get_tag("genre"),
        "composer": get_tag("composer"),
        "lyrics": normalize_lyrics(get_tag("lyrics")),
        "lyrics_fields": describe_embedded_lyrics(path),
        "cover": cover,
    }


def search_ytdlp_metadata(query: str) -> dict:
    """Use yt-dlp's search result as a metadata fallback when public catalogs miss."""
    search_url = "ytsearch1:" + " ".join(query.split())
    command = find_executable("yt-dlp") + get_ytdlp_js_runtime_args() + [
        "--dump-json", "--no-warnings", "--no-playlist", search_url,
    ]
    process = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=get_env_with_utf8(),
        shell=False,
        timeout=45,
    )
    if process.returncode != 0 or not process.stdout.strip():
        details = (process.stderr or process.stdout or "").strip().splitlines()
        detail = " ".join(details[-2:])[-400:]
        raise ValueError(detail or "yt-dlp 没有找到匹配的视频。")

    try:
        info = json.loads(process.stdout.splitlines()[0])
    except (json.JSONDecodeError, IndexError) as exc:
        raise ValueError("yt-dlp 返回了无法读取的搜索结果。") from exc

    title = str(info.get("track") or info.get("title") or "").strip()
    artist = str(info.get("artist") or info.get("creator") or info.get("uploader") or info.get("channel") or "").strip()
    url = str(info.get("webpage_url") or "").strip()
    if not url:
        video_id = str(info.get("id") or "").strip()
        extractor = str(info.get("extractor_key") or info.get("ie_key") or "").lower()
        if video_id and ("youtube" in extractor or not extractor):
            url = f"https://www.youtube.com/watch?v={urllib.parse.quote(video_id)}"
    if not title or not url:
        raise ValueError("yt-dlp 搜索结果缺少歌曲标题或可用链接。")

    release_date = str(info.get("release_date") or info.get("upload_date") or "")
    year = release_date[:4] if len(release_date) >= 4 else str(info.get("release_year") or "")
    thumbnail = str(info.get("thumbnail") or "").strip()
    thumbnails = info.get("thumbnails")
    if not thumbnail and isinstance(thumbnails, list):
        candidates = [item for item in thumbnails if isinstance(item, dict) and item.get("url")]
        if candidates:
            best = max(candidates, key=lambda item: (item.get("width") or 0) * (item.get("height") or 0))
            thumbnail = str(best["url"]).strip()
    if not thumbnail:
        video_id = str(info.get("id") or "").strip()
        if video_id and ("youtube" in str(info.get("extractor_key") or info.get("ie_key") or "").lower()
                         or urllib.parse.urlparse(url).hostname in {"youtube.com", "www.youtube.com", "youtu.be"}):
            thumbnail = f"https://i.ytimg.com/vi/{urllib.parse.quote(video_id)}/hqdefault.jpg"
    thumbnail = thumbnail or None
    return {
        "title": title,
        "artist": artist or "未知艺人",
        "album": str(info.get("album") or ""),
        "albumartist": artist or "未知艺人",
        "year": year,
        "lyrics": "",
        "cover": thumbnail,
        "thumbnail": thumbnail,
        "url": url,
        "preview_url": url if urllib.parse.urlparse(url).hostname in {"youtube.com", "www.youtube.com", "youtu.be", "m.youtube.com"} else "",
        "provider": "yt-dlp",
    }


def lookup_metadata_by_keyword(query: str, album_hint: str = "") -> dict:
    artist, title = parse_metadata_search_query(query)
    if not title:
        raise ValueError("请输入“作者 - 标题”或歌曲标题。")

    metadata = (lookup_musicbrainz_metadata(title, artist, album_hint) if album_hint
                else lookup_musicbrainz_metadata(title, artist))
    lyric_track = search_lrc_track(title, artist)
    found_artist = metadata.get("artist") or artist
    if found_artist in {"未知艺人", "Unknown Artist", title} and lyric_track:
        found_artist = lyric_track.get("artistName") or found_artist
    if not any(metadata.get(field) for field in ("album", "year", "cover_url")) and not lyric_track:
        fallback = search_ytdlp_metadata(query)
        fallback["lyrics"] = fetch_lrc_lyrics(fallback["title"], fallback["artist"])
        return fallback
    if artist == "未知艺人" and found_artist in {"未知艺人", title}:
        fallback = search_ytdlp_metadata(query)
        fallback["lyrics"] = fetch_lrc_lyrics(fallback["title"], fallback["artist"])
        return fallback

    cover = None
    cover_url = metadata.get("cover_url")
    if cover_url:
        parsed = urllib.parse.urlparse(cover_url)
        if parsed.scheme == "https" and parsed.hostname == "coverartarchive.org":
            try:
                request = urllib.request.Request(cover_url, headers={"User-Agent": "MusicDesk/1.0"})
                with urllib.request.urlopen(request, timeout=6) as response:
                    image_data = response.read(8 * 1024 * 1024 + 1)
                    content_type = response.headers.get_content_type()
                if len(image_data) <= 8 * 1024 * 1024 and content_type.startswith("image/"):
                    cover = f"data:{content_type};base64," + base64.b64encode(image_data).decode("ascii")
            except Exception:
                pass

    return {
        "title": title,
        "artist": found_artist,
        "album": metadata.get("album") or (lyric_track or {}).get("albumName", ""),
        "albumartist": found_artist,
        "year": metadata.get("year", ""),
        "lyrics": ((lyric_track or {}).get("syncedLyrics") or (lyric_track or {}).get("plainLyrics")
                   or fetch_lrc_lyrics(title, found_artist)),
        "cover": cover,
        "provider": "MusicBrainz",
    }


def list_playlist_entries(url: str) -> dict:
    """List a YouTube / YouTube Music playlist without downloading anything."""
    playlist_url = batch_queue.parse_playlist_url(url)["url"]
    command = find_executable("yt-dlp") + get_ytdlp_js_runtime_args() + [
        "--flat-playlist", "--dump-json", "--no-warnings",
        "--playlist-end", str(batch_queue.MAX_BATCH_TRACKS), playlist_url,
    ]
    process = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=get_env_with_utf8(), shell=False, timeout=120,
    )
    entries, title = [], ""
    for line in process.stdout.splitlines():
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        title = title or str(raw.get("playlist_title") or "")
        entry = batch_queue.clean_playlist_entry(raw)
        if entry:
            entries.append(entry)
    if not entries:
        details = (process.stderr or "").strip().splitlines()
        raise ValueError(" ".join(details[-2:])[-300:] or "没有读取到可下载的曲目（播放列表可能是私有的或为空）。")
    return {"title": title, "entries": entries}


def process_batch_track(track: dict, options: dict, dest_dir: Path) -> Path:
    """Download one playlist entry, tag it, and move the finished file into dest_dir."""
    video_url = parse_share_url(f"https://www.youtube.com/watch?v={track['id']}")["url"]
    title, artist = track["title"], track["artist"]
    export_format, bitrate = options["format"], options["bitrate"]
    with tempfile.TemporaryDirectory(prefix="musicdesk-batch-dl-") as temp_dir:
        downloaded_file, _source = fetch_media_stream(video_url, title, artist, "ytdlp", temp_dir)
        cover_path = Path(temp_dir) / "cover.jpg"
        try:
            cover_path.write_bytes(crop_yt_padding_smart(fetch_thumbnail(validate_thumbnail_url(track["thumbnail"]))))
        except Exception:
            cover_path.write_bytes(b"")
        try:  # lyrics are a bonus: never fail a track because the lyric service is down
            lyrics = fetch_lrc_lyrics(title, artist) or ""
        except Exception:
            lyrics = ""
        meta = {"title": title, "artist": artist, "album": "", "albumartist": artist, "year": ""}
        final = process_and_export_media(
            source_path=downloaded_file, meta_info=meta, cover_path=cover_path,
            export_format=export_format, output_dir=Path(temp_dir) / "out", bitrate=bitrate, lyrics_text=lyrics,
        )
        target = batch_queue.unique_name(dest_dir, final.name)
        shutil.move(str(final), str(target))
        if options.get("download_lrc") and lyrics:
            sidecar = target.with_suffix(".lrc")
            sidecar.write_bytes(normalize_lyrics(lyrics).encode("utf-8-sig"))
        return target


def search_metadata_candidates(query: str, limit: int = 8) -> list[dict]:
    """Other MusicBrainz recordings that match a keyword search, so the person can pick one."""
    artist, title = parse_metadata_search_query(query)
    if not title:
        raise ValueError("请输入“作者 - 标题”或歌曲标题。")
    clean_artist = "" if artist in {"未知艺人", "Unknown Artist"} or artist.strip() == title.strip() else artist.strip()
    result = musicbrainzngs.search_recordings(query=build_musicbrainz_search_query(title, clean_artist), limit=25)
    candidates, seen = [], set()
    for recording in result.get("recording-list", []):
        credit = recording.get("artist-credit", [])
        names = [part.get("artist", {}).get("name", "") if isinstance(part, dict) else "" for part in credit]
        artist_name = ", ".join(name for name in names if name)
        releases = [rel for rel in recording.get("release-list", []) if isinstance(rel, dict)]
        releases.sort(key=lambda rel: (
            (rel.get("release-group") or {}).get("type", "").lower() == "album",
            bool(rel.get("date")),
        ), reverse=True)
        release = releases[0] if releases else {}
        item = {
            "id": recording.get("id", ""),
            "title": recording.get("title", ""),
            "artist": artist_name,
            "album": release.get("title", ""),
            "year": str(release.get("date", ""))[:4],
            "duration": int(recording.get("length") or 0) // 1000,
            "disambiguation": recording.get("disambiguation", ""),
        }
        key = (item["title"].casefold(), item["artist"].casefold(), item["album"].casefold())
        if not item["title"] or key in seen:
            continue
        seen.add(key)
        candidates.append(item)
        if len(candidates) >= limit:
            break
    return candidates


def build_download_query(url: str, title: str, artist: str, keyword_search: bool) -> str:
    url = (url or "").strip()
    if url or not keyword_search:
        return url
    artist = (artist or "").strip()
    title = (title or "").strip()
    query = f"{artist} - {title}" if artist else title
    if not query:
        raise ValueError("请先搜索一首歌曲，或提供有效的分享链接。")
    return "musicdesk-query:" + query


def validate_download_source(source: str) -> str:
    """Allow only supported share URLs or MusicDesk's internal keyword query."""
    if not isinstance(source, str) or len(source) > 2048 or any(ord(char) < 32 for char in source):
        raise ValueError("下载来源无效。")
    source = source.strip()
    if source.startswith("musicdesk-query:"):
        query = source.removeprefix("musicdesk-query:").strip()
        if not query or len(query) > 512 or query.startswith("-"):
            raise ValueError("歌曲搜索词无效。")
        return "musicdesk-query:" + query
    if source.startswith("ytsearch1:"):
        query = source.removeprefix("ytsearch1:").strip()
        if not query or len(query) > 512 or query.startswith("-"):
            raise ValueError("歌曲搜索词无效。")
        return "ytsearch1:" + query
    return parse_share_url(source)["url"]


def validate_thumbnail_url(url: str) -> str:
    """Restrict user-supplied artwork URLs to known public artwork hosts."""
    if not url:
        return ""
    if not isinstance(url, str) or len(url) > 2048 or any(ord(char) < 32 for char in url):
        raise ValueError("封面地址无效。")
    try:
        parsed = urllib.parse.urlsplit(url.strip())
        host = (parsed.hostname or "").lower().rstrip(".")
        port = parsed.port
    except ValueError as exc:
        raise ValueError("封面地址无效。") from exc
    allowed_host = host in SAFE_THUMBNAIL_HOSTS
    if (parsed.scheme != "https" or not allowed_host or parsed.username or parsed.password
            or port not in (None, 443) or not parsed.path.startswith("/")):
        raise ValueError("封面地址必须来自受支持的 HTTPS 图片来源。")
    return urllib.parse.urlunsplit(parsed)


class SafeThumbnailRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_thumbnail_url(urllib.parse.urljoin(req.full_url, newurl))
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_thumbnail(url: str) -> bytes:
    safe_url = validate_thumbnail_url(url)
    request = urllib.request.Request(safe_url, headers={"User-Agent": "Mozilla/5.0"})
    opener = urllib.request.build_opener(SafeThumbnailRedirectHandler())
    with opener.open(request, timeout=10) as response:
        if not response.headers.get_content_type().startswith("image/"):
            raise ValueError("封面来源没有返回图片。")
        image_data = response.read(MAX_COVER_BYTES + 1)
    if len(image_data) > MAX_COVER_BYTES:
        raise ValueError("封面图片超过大小限制。")
    return image_data


def multipart_fields(content_type: str, raw: bytes) -> dict:
    message = BytesParser(policy=default).parsebytes(
        b"Content-Type: " + content_type.encode("ascii", "replace") + b"\r\nMIME-Version: 1.0\r\n\r\n" + raw
    )
    return {part.get_param("name", header="content-disposition"): part for part in message.iter_parts()}


def multipart_text(fields: dict, name: str) -> str:
    part = fields.get(name)
    if not part:
        return ""
    payload = part.get_payload(decode=True)
    if payload is None:
        return ""
    return payload.decode(part.get_content_charset() or "utf-8", errors="replace").strip()


def acquire_custom_audio_source(
    audio_bytes: bytes | None,
    original_filename: str,
    title: str,
    artist: str,
    preferred_engine: str,
    work_dir: Path,
) -> tuple[Path, str]:
    if audio_bytes is not None:
        input_path = work_dir / f"input{Path(original_filename).suffix}"
        input_path.write_bytes(audio_bytes)
        return input_path, original_filename
    if not title.strip():
        raise ValueError("请提供本地音频，或先搜索并填写歌曲标题。")
    search_url = build_download_query("", title, artist, True)
    downloaded, _ = fetch_media_stream(search_url, title, artist, preferred_engine, work_dir)
    return downloaded, make_tag_export_filename(artist, title, "", "mp3")


def find_ffmpeg_exe() -> str | None:
    try:
        import imageio_ffmpeg
        bundled = imageio_ffmpeg.get_ffmpeg_exe()
        if Path(bundled).is_file():
            return bundled
    except (ImportError, OSError, RuntimeError):
        pass
    return shutil.which("ffmpeg")


find_ffmpeg = find_ffmpeg_exe


def crop_yt_padding_smart(img_bytes: bytes) -> bytes:
    if not img_bytes:
        return img_bytes
    try:
        img = Image.open(BytesIO(img_bytes)).convert("RGB")
        w, h = img.size

        min_dim = min(w, h)
        left = (w - min_dim) // 2
        top = (h - min_dim) // 2
        img_sq = img.crop((left, top, left + min_dim, top + min_dim))

        sq_w, sq_h = img_sq.size
        pixels = img_sq.load()
        bg_color = pixels[0, 0]

        def is_similar(c1, c2, tol=25):
            return sum(abs(a - b) for a, b in zip(c1, c2)) < tol

        top_b, bottom_b, left_b, right_b = 0, sq_h, 0, sq_w

        for y in range(sq_h // 2):
            if not all(is_similar(pixels[x, y], bg_color) for x in range(0, sq_w, 5)):
                top_b = y
                break

        for y in range(sq_h - 1, sq_h // 2, -1):
            if not all(is_similar(pixels[x, y], bg_color) for x in range(0, sq_w, 5)):
                bottom_b = y + 1
                break

        for x in range(sq_w // 2):
            if not all(is_similar(pixels[x, y], bg_color) for y in range(0, sq_h, 5)):
                left_b = x
                break

        for x in range(sq_w - 1, sq_w // 2, -1):
            if not all(is_similar(pixels[x, y], bg_color) for y in range(0, sq_h, 5)):
                right_b = x + 1
                break

        if (right_b - left_b > 50) and (bottom_b - top_b > 50):
            img_final = img_sq.crop((left_b, top_b, right_b, bottom_b))
        else:
            img_final = img_sq

        output = BytesIO()
        img_final.save(output, format="JPEG", quality=95)
        return output.getvalue()
    except Exception as e:
        print(f"[MusicDesk 智能裁剪提示]: {e}")
        return img_bytes


def fetch_lrc_lyrics(title: str, artist: str) -> str:
    if not title or title == "未知标题":
        return ""
    try:
        clean_artist = "" if artist in {"未知艺人", "Unknown Artist"} else artist.strip()
        query = f"track_name={urllib.parse.quote(title)}"
        if clean_artist:
            query += f"&artist_name={urllib.parse.quote(clean_artist)}"

        url = f"https://lrclib.net/api/get?{query}"
        req = urllib.request.Request(url, headers={"User-Agent": "MusicDesk/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            synced = data.get("syncedLyrics", "")
            if synced:
                print(f"[MusicDesk 歌词成功] 成功检索到 LRC 同步歌词")
                return synced
            plain = data.get("plainLyrics", "")
            if plain:
                return plain
    except Exception:
        pass

    result = search_lrc_track(title, artist)
    if result:
        lyrics = result.get("syncedLyrics") or result.get("plainLyrics") or ""
        if lyrics:
            print("[MusicDesk 歌词成功] 通过曲名检索找到歌词")
        return lyrics
    return ""


def search_lrc_track(title: str, artist: str) -> dict | None:
    if not title:
        return None
    clean_artist = "" if artist in {"未知艺人", "Unknown Artist"} or artist.strip() == title.strip() else artist.strip()
    query = " ".join(part for part in (clean_artist, title.strip()) if part)
    search_url = "https://lrclib.net/api/search?" + urllib.parse.urlencode({"q": query})
    request = urllib.request.Request(search_url, headers={"User-Agent": "MusicDesk/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=6) as response:
            results = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None

    if not isinstance(results, list):
        return None
    normalize = lambda value: re.sub(r"[^\w]", "", str(value or "").casefold())
    wanted_title = normalize(title)
    wanted_artist = normalize(clean_artist)
    candidates = [item for item in results if normalize(item.get("trackName")) == wanted_title]
    if not candidates:
        candidates = [item for item in results if wanted_title and wanted_title in normalize(item.get("trackName"))]
    if not candidates:
        return None
    if wanted_artist:
        artist_matches = [item for item in candidates if wanted_artist in normalize(item.get("artistName"))]
        if artist_matches:
            candidates = artist_matches
    return max(candidates, key=lambda item: (bool(item.get("syncedLyrics")), bool(item.get("plainLyrics")), bool(item.get("albumName"))))


def find_executable(name: str) -> list[str]:
    python_exe = Path(sys.executable)
    exe_name = f"{name}.exe" if os.name == "nt" else name
    local_path = python_exe.parent / exe_name

    # pip-generated Windows console launchers embed the venv's original path.
    # Calling the installed module keeps source installs working after the folder moves.
    module_name = {"yt-dlp": "yt_dlp", "spotdl": "spotdl"}.get(name)
    if module_name and not getattr(sys, "frozen", False):
        try:
            if importlib.util.find_spec(module_name):
                return [sys.executable, "-m", module_name]
        except (ImportError, ValueError):
            pass

    if local_path.exists():
        return [str(local_path)]

    which_path = shutil.which(name)
    if which_path:
        return [which_path]

    if name == "yt-dlp":
        return [sys.executable, "-m", "yt_dlp"]
    return [name]


def get_ytdlp_js_runtime_args() -> list[str]:
    """Enable a supported JS runtime explicitly for YouTube challenge solving."""
    runtime_names = (("deno", "deno"), ("node", "node"), ("quickjs", "qjs"))
    app_dir = Path(sys.executable).resolve().parent
    for runtime, executable in runtime_names:
        runtime_path = next(
            (str(candidate) for candidate in (app_dir / f"{executable}.exe", app_dir / executable) if candidate.is_file()),
            None,
        ) or shutil.which(executable)
        if runtime_path:
            return ["--js-runtimes", f"{runtime}:{runtime_path}"]
    return []


def log_downloader_failure(engine: str, proc: subprocess.CompletedProcess[str]) -> None:
    """Expose a short actionable error in the server console without dumping huge logs."""
    details = (proc.stderr or proc.stdout or "").strip()
    if details:
        lines = [line.strip() for line in details.splitlines() if line.strip()]
        print(f"[{engine} 失败详情] " + " | ".join(lines[-4:])[-1200:])
    else:
        print(f"[{engine} 失败详情] 进程退出码：{proc.returncode}，没有提供错误输出。")
    sys.stdout.flush()


def fetch_youtube_rich_metadata(url: str) -> dict:
    meta = {"title": "", "artist": "", "album": "", "year": "", "thumbnail": None}
    try:
        cmd = find_executable("yt-dlp") + ["--dump-json", "--no-playlist", url]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=get_env_with_utf8(),
            shell=False,
            timeout=45,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            info = json.loads(proc.stdout)
            meta["title"] = info.get("track") or info.get("title") or ""
            meta["artist"] = info.get("artist") or info.get("uploader") or info.get("channel") or ""
            meta["album"] = info.get("album") or ""
            
            release_date = str(info.get("release_date") or info.get("upload_date") or "")
            if len(release_date) >= 4:
                meta["year"] = release_date[:4]
            elif info.get("release_year"):
                meta["year"] = str(info.get("release_year"))

            meta["thumbnail"] = info.get("thumbnail")
    except Exception as e:
        print(f"[MusicDesk YouTube 元数据抓取提示]: {e}")

    return meta


def fetch_with_ytdlp(url: str, title: str, artist: str, base_dir: Path) -> tuple[Path | None, str]:
    target_url = url.strip()
    if "spotify.com" in target_url:
        clean_title = re.sub(r"\s*-\s*Topic$", "", title, flags=re.IGNORECASE).strip()
        clean_artist = "" if artist in {"未知艺人", "Unknown Artist"} or artist.strip() == clean_title else artist.strip()
        
        if clean_artist:
            search_query = f"{clean_artist} {clean_title}".strip()
        else:
            search_query = f"{clean_title}".strip()

        if not search_query or search_query == "Official Audio":
            search_query = "music"

        target_url = f"ytsearch1:{search_query}"
        print(f"[yt-dlp 引擎] 检索关键词: {search_query}")

    cmd = find_executable("yt-dlp") + get_ytdlp_js_runtime_args() + [
        "-x",
        "--audio-format", "mp3",
        "--no-playlist",
        "--print", "after_move:filepath",
        "--print", "webpage_url",
        "-o", str(base_dir / "ytdlp_%(id)s.%(ext)s"),
        "--", target_url
    ]
    print(f"[MusicDesk 调度] 尝试 [yt-dlp] 抓取音频...")
    sys.stdout.flush()
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=get_env_with_utf8(),
        shell=False,
        timeout=300,
    )
    
    source_url = ""
    if proc.returncode == 0 and proc.stdout.strip():
        lines = [line.strip() for line in proc.stdout.strip().splitlines() if line.strip()]
        for line in lines:
            if line.startswith("http://") or line.startswith("https://"):
                source_url = line

    mp3_files = list(base_dir.glob("ytdlp_*.mp3"))
    if mp3_files:
        latest = max(mp3_files, key=lambda p: p.stat().st_mtime)
        
        if not source_url:
            video_id = latest.stem.replace("ytdlp_", "")
            source_url = f"https://www.youtube.com/watch?v={video_id}"

        print(f"[MusicDesk 成功] yt-dlp 成功提取: {latest.name}")
        print(f"[MusicDesk 音频来源] {source_url}")
        sys.stdout.flush()
        return latest, source_url
    
    log_downloader_failure("yt-dlp", proc)
    failure_text = f"{proc.stderr or ''}\n{proc.stdout or ''}".lower()
    if any(marker in failure_text for marker in ("javascript runtime", "js runtime", "javascript challenge")):
        raise RuntimeError(
            "YouTube 下载需要 Deno 或 Node.js 来处理 JavaScript 验证。请更新便携版，"
            "或在电脑安装 Deno/Node.js 后重启 MusicDesk。"
        )
    print(f"[yt-dlp 抓取失败]")
    sys.stdout.flush()
    return None, ""


def fetch_with_spotdl(url: str, base_dir: Path) -> tuple[Path | None, str]:
    print(f"[MusicDesk 调度] 尝试 [spotdl] 下载...")
    sys.stdout.flush()
    cmd = find_executable("spotdl") + ["download", url.strip()]

    proc = subprocess.run(
        cmd,
        cwd=str(base_dir),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=get_env_with_utf8(),
        shell=False,
        timeout=300,
    )
    
    if proc.returncode == 0:
        mp3_files = list(base_dir.glob("*.mp3"))
        if mp3_files:
            latest = max(mp3_files, key=lambda p: p.stat().st_mtime)
            print(f"[MusicDesk 音频来源] {url}")
            sys.stdout.flush()
            return latest, url

    log_downloader_failure("spotdl", proc)
    print(f"[spotdl 下载未成功]")
    sys.stdout.flush()
    return None, ""


def fetch_media_stream(url: str, title: str = "", artist: str = "", preferred_engine: str = "ytdlp", temp_dir: str | Path | None = None) -> tuple[Path, str]:
    base_dir = Path(temp_dir) if temp_dir else Path(tempfile.gettempdir())

    if url.startswith("musicdesk-query:"):
        query = url.removeprefix("musicdesk-query:").strip()
        if not query:
            raise ValueError("搜索词不能为空。")
        search_engines = {
            "ytdlp": lambda: fetch_with_ytdlp("ytsearch1:" + query, title, artist, base_dir),
            "spotdl": lambda: fetch_with_spotdl(query, base_dir),
        }
        first_engine = preferred_engine if preferred_engine in search_engines else "ytdlp"
        for engine in (first_engine, "spotdl" if first_engine == "ytdlp" else "ytdlp"):
            res_file, source_url = search_engines[engine]()
            if res_file and res_file.is_file():
                return res_file, "" if source_url == query else source_url
        raise ValueError("没有找到可下载的匹配音频，请尝试调整关键词。")

    engines = {"ytdlp": lambda: fetch_with_ytdlp(url, title, artist, base_dir)}
    if "spotify.com" in url.lower():
        engines["spotdl"] = lambda: fetch_with_spotdl(url, base_dir)

    valid_engine = preferred_engine if preferred_engine in engines else "ytdlp"
    priority_order = [valid_engine] + [name for name in engines if name != valid_engine]

    for eng_name in priority_order:
        res_file, source_url = engines[eng_name]()
        if res_file and res_file.is_file():
            return res_file, source_url

    raise ValueError("所有配置的下载引擎均无法匹配或提取该歌曲。")


def process_and_export_media(
    source_path: str | Path,
    meta_info: dict,
    cover_path: str | Path,
    export_format: str,
    output_dir: str | Path,
    *,
    cleanup_source: bool = True,
    bitrate: str = "192",
    lyrics_text: str = "",
    track_num: str = "",
    genre: str = "",
    composer: str = "",
    disc_num: str = "",
) -> Path:
    source = Path(source_path)
    cover = Path(cover_path)
    fmt = str(export_format).strip().lower().lstrip(".")
    if not source.is_file():
        raise ValueError("Cached media file does not exist")

    ffmpeg = find_ffmpeg_exe()
    if not ffmpeg:
        raise ValueError("FFmpeg is not installed or available on PATH")

    title = meta_info.get("title", "未知标题").strip()
    artist = meta_info.get("artist", "未知艺人").strip()
    albumartist = meta_info.get("albumartist", "").strip() or artist
    album = meta_info.get("album", "").strip()
    year = meta_info.get("year", "").strip()
    track_num = meta_info.get("track_num", "").strip()

    destination_dir = Path(output_dir)
    destination_dir.mkdir(parents=True, exist_ok=True)
    base = SAFE_NAME.sub("_", f"{artist} - {title}").strip(" .") or "audio"
    if fmt not in FORMATS:
        raise ValueError("不支持的音频格式。")
    bitrate_value = str(bitrate).strip()
    if bitrate_value not in {"128", "192", "256", "320"}:
        bitrate_value = "192"
    destination = destination_dir / limit_filename_length(f"{base}.{fmt}")

    with tempfile.TemporaryDirectory(prefix="musicdesk-export-", dir=destination_dir) as work:
        staged = Path(work) / f"export.{fmt}"
        codec_args = {
            "mp3": ["-c:a", "libmp3lame", "-b:a", f"{bitrate_value}k"],
            "m4a": ["-c:a", "aac", "-b:a", f"{bitrate_value}k"],
            "ogg": ["-c:a", "libvorbis", "-b:a", f"{bitrate_value}k"],
            "flac": ["-c:a", "flac"],
            "wav": ["-c:a", "pcm_s16le"],
        }[fmt]
        proc = subprocess.run(
            [ffmpeg, "-nostdin", "-v", "error", "-y", "-i", str(source), "-map", "0:a:0", "-vn", *codec_args, str(staged)],
            capture_output=True, timeout=300, env=get_env_with_utf8()
        )
        if proc.returncode or not staged.is_file():
            detail = proc.stderr.decode("utf-8", errors="replace").strip() if proc.stderr else ""
            raise ValueError("FFmpeg 处理音频失败" + (f"：{detail[-500:]}" if detail else ""))

        lyrics_text = normalize_lyrics(lyrics_text or fetch_lrc_lyrics(title, artist), str(meta_info.get("lyrics_format") or "auto"))
        try:
            from mutagen.id3 import APIC, TALB, TCOM, TCON, TDRC, TIT2, TPE1, TPE2, TRCK, TPOS, USLT
            if fmt == "mp3":
                from mutagen.id3 import ID3
                tags = ID3()
                tags.add(TIT2(encoding=3, text=title)); tags.add(TPE1(encoding=3, text=artist)); tags.add(TPE2(encoding=3, text=albumartist))
                if album: tags.add(TALB(encoding=3, text=album))
                if year: tags.add(TDRC(encoding=3, text=year))
                if track_num: tags.add(TRCK(encoding=3, text=track_num))
                if disc_num: tags.add(TPOS(encoding=3, text=disc_num))
                if genre: tags.add(TCON(encoding=3, text=genre))
                if composer: tags.add(TCOM(encoding=3, text=composer))
                if lyrics_text: tags.add(USLT(encoding=3, lang="eng", desc="", text=lyrics_text))
                if cover.is_file() and cover.stat().st_size > 0:
                    mime = "image/png" if cover.suffix.lower() == ".png" else "image/jpeg"
                    tags.add(APIC(encoding=3, mime=mime, type=3, desc="Cover", data=cover.read_bytes()))
                tags.save(staged, v2_version=3)
            elif fmt == "wav":
                from mutagen.wave import WAVE
                from mutagen.id3 import ID3
                audio = WAVE(staged)
                if audio.tags is None: audio.add_tags()
                tags = audio.tags
                tags.add(TIT2(encoding=3, text=title)); tags.add(TPE1(encoding=3, text=artist)); tags.add(TPE2(encoding=3, text=albumartist))
                if album: tags.add(TALB(encoding=3, text=album))
                if year: tags.add(TDRC(encoding=3, text=year))
                if track_num: tags.add(TRCK(encoding=3, text=track_num))
                if disc_num: tags.add(TPOS(encoding=3, text=disc_num))
                if genre: tags.add(TCON(encoding=3, text=genre))
                if composer: tags.add(TCOM(encoding=3, text=composer))
                if lyrics_text: tags.add(USLT(encoding=3, lang="eng", desc="", text=lyrics_text))
                if cover.is_file() and cover.stat().st_size > 0:
                    mime = "image/png" if cover.suffix.lower() == ".png" else "image/jpeg"
                    tags.add(APIC(encoding=3, mime=mime, type=3, desc="Cover", data=cover.read_bytes()))
                audio.save()
            else:
                from mutagen import File as MutagenFile
                from mutagen.mp4 import MP4, MP4Cover
                from mutagen.flac import FLAC, Picture
                audio = MutagenFile(staged, easy=False)
                if audio is None:
                    raise ValueError("无法识别导出的音频容器。")
                if isinstance(audio, MP4):
                    tags = audio.tags
                    if tags is None: audio.add_tags(); tags = audio.tags
                    for key, value in (("\xa9nam", title), ("\xa9ART", artist), ("aART", albumartist), ("\xa9alb", album), ("\xa9day", year), ("\xa9gen", genre), ("\xa9wrt", composer), ("\xa9lyr", lyrics_text)):
                        if value: tags[key] = [str(value)]
                    if track_num: tags["trkn"] = [(int(track_num.split("/")[0]), int(track_num.split("/")[1]) if "/" in track_num else 0)]
                    if disc_num: tags["disk"] = [(int(disc_num.split("/")[0]), int(disc_num.split("/")[1]) if "/" in disc_num else 0)]
                    if cover.is_file() and cover.stat().st_size > 0:
                        image_format = MP4Cover.FORMAT_PNG if cover.suffix.lower() == ".png" else MP4Cover.FORMAT_JPEG
                        tags["covr"] = [MP4Cover(cover.read_bytes(), imageformat=image_format)]
                    audio.save()
                elif isinstance(audio, FLAC) or fmt == "ogg":
                    if audio.tags is None: audio.add_tags()
                    tags = audio.tags
                    pairs = (("title", title), ("artist", artist), ("album", album), ("albumartist", albumartist), ("date", year), ("tracknumber", track_num), ("discnumber", disc_num), ("genre", genre), ("composer", composer), ("lyrics", lyrics_text))
                    for key, value in pairs:
                        if value: tags[key] = [str(value)]
                    if cover.is_file() and cover.stat().st_size > 0:
                        picture = Picture(); picture.data = cover.read_bytes(); picture.type = 3
                        picture.mime = "image/png" if cover.suffix.lower() == ".png" else "image/jpeg"; picture.desc = "Cover"
                        if hasattr(audio, "clear_pictures"):
                            audio.clear_pictures(); audio.add_picture(picture)
                        else:
                            import base64
                            tags["metadata_block_picture"] = [base64.b64encode(picture.write()).decode("ascii")]
                    audio.save()
                else:
                    raise ValueError("此音频容器暂不支持写入元数据。")
        except Exception as exc:
            raise ValueError(f"写入音频标签失败：{exc}") from exc
        os.replace(staged, destination)

    if cleanup_source:
        source.unlink(missing_ok=True)
    return destination


def fetch_spotify_oembed(raw_url: str) -> dict:
    meta = {"title": "", "artist": "", "thumbnail": None}
    try:
        endpoint = "https://open.spotify.com/oembed?url=" + urllib.parse.quote(raw_url, safe="")
        req = urllib.request.Request(endpoint, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=6) as response:
            data = json.loads(response.read().decode("utf-8"))
            raw_title = html_module.unescape(str(data.get("title", ""))).strip()
            meta["thumbnail"] = data.get("thumbnail_url")
            meta["artist"] = html_module.unescape(str(data.get("author_name", ""))).strip()
            
            if " - " in raw_title and not meta["artist"]:
                parts = raw_title.split(" - ", 1)
                meta["artist"], meta["title"] = parts[0].strip(), parts[1].strip()
            else:
                meta["title"] = raw_title
    except Exception as exc:
        print(f"[MusicDesk] Spotify oEmbed 解析提示: {exc}")
    return meta


def fetch_spotify_embed_html(track_id: str) -> dict:
    meta = {"title": "", "artist": "", "thumbnail": None}
    try:
        url = f"https://open.spotify.com/embed/track/{track_id}"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8"
        })
        with urllib.request.urlopen(req, timeout=6) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
            title_m = re.search(r'<meta property="og:title" content="([^"]+)"', html)
            artist_m = re.search(r'<meta property="twitter:audio:artist_name" content="([^"]+)"', html) or \
                       re.search(r'<meta name="music:musician" content="([^"]+)"', html)
            img_m = re.search(r'<meta property="og:image" content="([^"]+)"', html)

            if title_m: meta["title"] = html_module.unescape(title_m.group(1)).strip()
            if artist_m: meta["artist"] = html_module.unescape(artist_m.group(1)).strip()
            if img_m: meta["thumbnail"] = img_m.group(1).strip()
    except Exception:
        pass
    return meta


def lookup_musicbrainz_metadata(title: str, artist: str, known_album: str = "") -> dict:
    print(f"[MusicDesk - MusicBrainz 检索] 正在查找: {title} - {artist} (已知专辑: {known_album})")
    res_meta = {"artist": artist, "album": known_album, "year": "", "track_num": "", "cover_url": None}
    if not title or title == "未知标题":
        return res_meta

    try:
        clean_artist = "" if artist in {"未知艺人", "Unknown Artist"} or artist.strip() == title.strip() else artist.strip()
        
        query = build_musicbrainz_search_query(title, clean_artist, known_album)

        result = musicbrainzngs.search_recordings(query=query, limit=15)
        recordings = result.get("recording-list", [])

        if not recordings and known_album:
            query_fallback = build_musicbrainz_search_query(title, clean_artist)
            result = musicbrainzngs.search_recordings(query=query_fallback, limit=15)
            recordings = result.get("recording-list", [])

        album_releases = []
        single_releases = []

        for rec in recordings:
            artist_credit = rec.get("artist-credit", [])
            if artist_credit and isinstance(artist_credit[0], dict):
                mb_artist = artist_credit[0].get("artist", {}).get("name", "")
                if mb_artist and (not clean_artist or res_meta["artist"] in {"未知艺人", title}):
                    res_meta["artist"] = mb_artist

            releases = rec.get("release-list", [])
            for rel in releases:
                rel_group = rel.get("release-group", {})
                primary_type = rel_group.get("type", "").lower()
                secondary_types = [t.lower() for t in rel_group.get("secondary-type-list", [])]

                if "live" in secondary_types or "remix" in secondary_types:
                    continue

                date_str = rel.get("date", "")
                year = date_str.split("-")[0] if date_str else "9999"

                item = {
                    "id": rel.get("id"),
                    "title": rel.get("title", ""),
                    "year": year if year != "9999" else "",
                    "is_album": primary_type == "album"
                }

                if primary_type == "album":
                    album_releases.append(item)
                else:
                    single_releases.append(item)

        candidate_releases = sorted(album_releases, key=lambda r: r["year"] or "9999") + \
                             sorted(single_releases, key=lambda r: r["year"] or "9999")

        for rel in candidate_releases:
            rel_id = rel["id"]
            album_name = rel["title"]
            year = rel["year"]

            cover_url = None
            try:
                test_url = f"https://coverartarchive.org/release/{rel_id}/front-500"
                req = urllib.request.Request(test_url, method='HEAD', headers={"User-Agent": "MusicDesk/1.0"})
                with urllib.request.urlopen(req, timeout=3):
                    cover_url = test_url
            except Exception:
                cover_url = None

            if not res_meta["album"]:
                res_meta["album"] = album_name
            if not res_meta["year"]:
                res_meta["year"] = year

            if cover_url:
                res_meta["cover_url"] = cover_url
                res_meta["album"] = album_name
                res_meta["year"] = year
                print(f"[MusicDesk 成功] 命中优先原画专辑封面 [{album_name} ({year})]: {cover_url}")
                return res_meta

    except Exception as e:
        print(f"[MusicDesk - MusicBrainz 提示]: {e}")

    return res_meta


def lookup_metadata(raw_url: str) -> dict:
    link = parse_share_url(raw_url)
    title, artist, album, year, track_num, thumbnail = "未知标题", "未知艺人", "", "", "", None

    if link["provider"] == "spotify":
        oembed_data = fetch_spotify_oembed(link["url"])
        if oembed_data.get("title"): title = oembed_data["title"]
        if oembed_data.get("artist"): artist = oembed_data["artist"]
        if oembed_data.get("thumbnail"): thumbnail = oembed_data["thumbnail"]

        if title == "未知标题" or artist == "未知艺人":
            embed_data = fetch_spotify_embed_html(link["id"])
            if title == "未知标题" and embed_data.get("title"): title = embed_data["title"]
            if artist == "未知艺人" and embed_data.get("artist"): artist = embed_data["artist"]
            if not thumbnail and embed_data.get("thumbnail"): thumbnail = embed_data["thumbnail"]

    elif link["provider"] == "youtube":
        yt_rich = fetch_youtube_rich_metadata(link["url"])
        if yt_rich.get("title"): title = yt_rich["title"]
        if yt_rich.get("artist"): artist = yt_rich["artist"]
        if yt_rich.get("album"): album = yt_rich["album"]
        if yt_rich.get("year"): year = yt_rich["year"]
        if yt_rich.get("thumbnail"): thumbnail = yt_rich["thumbnail"]

        if title == "未知标题":
            try:
                endpoint = "https://www.youtube.com/oembed?format=json&url=" + urllib.parse.quote(link["url"], safe="")
                req = urllib.request.Request(endpoint, headers={"User-Agent": "MusicDesk/1.0"})
                with urllib.request.urlopen(req, timeout=6) as response:
                    data = json.loads(response.read())
                    title = data.get("title", title)
                    artist = data.get("author_name", artist)
                    if not thumbnail: thumbnail = data.get("thumbnail_url")
            except Exception:
                pass

    artist = re.sub(r"\s*-\s*Topic$", "", artist, flags=re.IGNORECASE).strip()

    if title and title != "未知标题":
        mb_meta = lookup_musicbrainz_metadata(title, artist, known_album=album)
        if mb_meta.get("artist") and (artist == "未知艺人" or artist == title):
            artist = mb_meta["artist"]
        if mb_meta.get("album"):
            album = mb_meta["album"]
        if mb_meta.get("year"):
            year = mb_meta["year"]
        if mb_meta.get("cover_url"):
            thumbnail = mb_meta["cover_url"]

    if title == "未知标题":
        raise ValueError("未能读取到该音频链接信息，请检查链接或网络连接后重试。")

    return {
        "provider": link["provider"], "id": link["id"], "url": link["url"],
        "title": title, "artist": artist, "album": album, "year": year, "track_num": track_num,
        "thumbnail": thumbnail,
    }


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def send_json(self, code: int, value: dict):
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_api_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def send_api_cors_headers(self):
        origin = self.headers.get("Origin")
        if not getattr(self.server, "lan_mode", False) or origin is None or not self.validate_request_origin():
            return
        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Expose-Headers", "Content-Disposition, X-Source-Url")
        self.send_header("Vary", "Origin")

    def is_api_authorized(self) -> bool:
        if is_loopback_address(self.client_address[0]) and self.headers.get("Origin") != "null":
            return True
        token = getattr(self.server, "api_token", "")
        supplied = self.headers.get("Authorization", "")
        return is_api_authorized(supplied, token)

    def validate_request_origin(self) -> bool:
        try:
            parsed_host = urllib.parse.urlsplit("//" + self.headers.get("Host", ""))
            host = (parsed_host.hostname or "").lower().rstrip(".")
            port = parsed_host.port
        except ValueError:
            return False
        valid_hosts = {"localhost", "127.0.0.1", "::1"}
        if getattr(self.server, "lan_mode", False):
            valid_hosts.update(get_private_ipv4_addresses())
        if (host not in valid_hosts or port != self.server.server_port or parsed_host.username or
                parsed_host.password or parsed_host.path or parsed_host.query or parsed_host.fragment):
            return False
        origin = self.headers.get("Origin")
        if origin is None:
            return True
        if origin == "null":
            return bool(getattr(self.server, "lan_mode", False))
        try:
            parsed_origin = urllib.parse.urlsplit(origin)
            return (parsed_origin.scheme == "http" and parsed_origin.hostname and
                    parsed_origin.hostname.lower().rstrip(".") == host and
                    parsed_origin.port == self.server.server_port and
                    parsed_origin.path in ("", "/") and not parsed_origin.query and not parsed_origin.fragment)
        except ValueError:
            return False

    def read_request_body(self, max_size: int, content_type: str | None = None) -> bytes:
        raw_length = self.headers.get("Content-Length")
        if raw_length is None or not raw_length.isdecimal():
            self.close_connection = True
            raise ValueError("请求长度无效。")
        length = int(raw_length)
        if length < 1 or length > max_size:
            self.close_connection = True
            raise ValueError("请求为空或超过大小限制。")
        actual_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type and actual_type != content_type:
            self.close_connection = True
            raise ValueError("请求 Content-Type 无效。")
        body = self.rfile.read(length)
        if len(body) != length:
            self.close_connection = True
            raise ValueError("请求数据不完整。")
        return body

    def read_json_object(self, max_size: int = MAX_API_JSON) -> dict:
        value = json.loads(self.read_request_body(max_size, "application/json"))
        if not isinstance(value, dict):
            raise ValueError("JSON 请求必须是对象。")
        return value

    def reject_invalid_request(self) -> bool:
        if not self.validate_request_origin():
            self.send_json(403, {"error": "请求来源或 Host 无效。"})
            return True
        return False

    def do_OPTIONS(self):
        if not self.path.startswith("/api/") or not getattr(self.server, "lan_mode", False):
            self.send_error(404)
            return
        if self.reject_invalid_request():
            return
        self.send_response(204)
        self.send_api_cors_headers()
        self.end_headers()

    def handle_batch_get(self, job_id: str, want_zip: bool):
        if not self.is_api_authorized():
            self.send_json(401, {"error": "配对密钥无效。"})
            return
        manager = self.server.batch_manager
        manager.prune()
        job = manager.get(job_id)
        if job is None:
            self.send_json(404, {"error": "批量任务不存在或已过期。"})
            return
        if not want_zip:
            self.send_json(200, job.snapshot())
            return
        if job.zip_path is None or not job.zip_path.is_file():
            self.send_json(409, {"error": "压缩包还没有准备好。"})
            return
        size = job.zip_path.stat().st_size
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + urllib.parse.quote("MusicDesk-批量下载.zip"))
        self.send_header("Content-Length", str(size))
        self.send_api_cors_headers()
        self.end_headers()
        with job.zip_path.open("rb") as handle:
            shutil.copyfileobj(handle, self.wfile)

    def do_GET(self):
        if self.reject_invalid_request():
            return
        if self.path == "/api/status":
            if not self.is_api_authorized():
                self.send_json(401, {"error": "配对密钥无效。"})
                return
            self.send_json(200, {
                "ok": True,
                "service": "MusicDesk",
                "api_version": MUSICDESK_API_VERSION,
                "capabilities": list(MUSICDESK_API_CAPABILITIES),
            })
            return
        batch_match = re.fullmatch(r"/api/batch/([0-9a-f]{32})(/zip)?", urllib.parse.urlsplit(self.path).path)
        if batch_match:
            self.handle_batch_get(batch_match.group(1), bool(batch_match.group(2)))
            return
        if getattr(self.server, "lan_mode", False) and not is_loopback_address(self.client_address[0]):
            # Remote LAN clients get the API only; keep the browser UI local to this computer.
            self.send_error(404)
            return
        local_audio_prefix = "/api/local-audio/"
        request_path = urllib.parse.urlsplit(self.path).path
        if request_path.startswith(local_audio_prefix):
            if not is_loopback_address(self.client_address[0]):
                self.send_error(404)
                return
            serve_local_audio(self, request_path[len(local_audio_prefix):])
            return
        super().do_GET()

    def do_HEAD(self):
        if self.reject_invalid_request():
            return
        if getattr(self.server, "lan_mode", False) and not is_loopback_address(self.client_address[0]):
            self.send_error(404)
            return
        local_audio_prefix = "/api/local-audio/"
        request_path = urllib.parse.urlsplit(self.path).path
        if request_path.startswith(local_audio_prefix):
            if not is_loopback_address(self.client_address[0]):
                self.send_error(404)
                return
            serve_local_audio(self, request_path[len(local_audio_prefix):])
            return
        super().do_HEAD()

    def do_POST(self):
        if self.reject_invalid_request():
            return
        if self.path.startswith("/api/") and not self.is_api_authorized():
            self.send_json(401, {"error": "配对密钥无效。"})
            return
        if self.path == "/api/metadata":
            try:
                req_data = self.read_json_object()
                source = req_data.get("url", "")
                if not isinstance(source, str):
                    raise ValueError("分享链接必须是文本。")
                result = lookup_metadata(source)
                print(f"[MusicDesk 完整 Metadata] 歌名: {result.get('title')} | 歌手: {result.get('artist')} | 专辑: {result.get('album')} | 年份: {result.get('year')}")
                sys.stdout.flush()
                self.send_json(200, result)
            except Exception as exc:
                self.send_json(400, {"error": str(exc)})
            return

        if self.path == "/api/lyrics_text":
            try:
                req_data = self.read_json_object()
                title = req_data.get("title", "")
                artist = req_data.get("artist", "")
                if not isinstance(title, str) or not isinstance(artist, str):
                    raise ValueError("歌曲名和艺人必须是文本。")
                lrc = fetch_lrc_lyrics(title, artist)
                if not lrc:
                    raise ValueError("未在公开歌词库中检索到对应的同步 LRC 歌词。")
                self.send_json(200, {"lyrics": lrc})
            except Exception as exc:
                self.send_json(400, {"error": str(exc)})
            return

        if self.path == "/api/playlist":
            try:
                req_data = self.read_json_object()
                url = req_data.get("url", "")
                if not isinstance(url, str) or len(url) > 2048:
                    raise ValueError("播放列表链接无效。")
                self.send_json(200, list_playlist_entries(url))
            except subprocess.TimeoutExpired:
                self.send_json(400, {"error": "读取播放列表超时，请稍后重试。"})
            except Exception as exc:
                self.send_json(400, {"error": str(exc) or "读取播放列表失败。"})
            return

        if self.path == "/api/batch":
            try:
                req_data = self.read_json_object(256 * 1024)
                export_format = str(req_data.get("format", "mp3")).lower()
                if export_format not in FORMATS:
                    raise ValueError("不支持的音频格式。")
                bitrate = str(req_data.get("bitrate", "192"))
                if bitrate not in {"128", "192", "256", "320"}:
                    raise ValueError("不支持的音频比特率。")
                download_lrc = req_data.get("download_lrc", False)
                if not isinstance(download_lrc, bool):
                    raise ValueError("download_lrc 必须是布尔值。")
                raw_tracks = req_data.get("tracks")
                if not isinstance(raw_tracks, list):
                    raise ValueError("tracks 必须是列表。")
                tracks, seen = [], set()
                for raw in raw_tracks:
                    entry = batch_queue.clean_playlist_entry(raw if isinstance(raw, dict) else {})
                    if entry and entry["id"] not in seen:
                        seen.add(entry["id"])
                        tracks.append(entry)
                job = self.server.batch_manager.start(
                    tracks, {"format": export_format, "bitrate": bitrate, "download_lrc": download_lrc}, process_batch_track)
                self.send_json(200, {"job_id": job.id, "total": len(tracks)})
            except RuntimeError as exc:
                self.send_json(409, {"error": str(exc)})
            except Exception as exc:
                self.send_json(400, {"error": str(exc) or "无法开始批量下载。"})
            return

        cancel_match = re.fullmatch(r"/api/batch/([0-9a-f]{32})/cancel", self.path)
        if cancel_match:
            if self.server.batch_manager.cancel(cancel_match.group(1)):
                self.send_json(200, {"ok": True})
            else:
                self.send_json(404, {"error": "批量任务不存在或已过期。"})
            return

        if self.path == "/api/search_metadata":
            try:
                req_data = self.read_json_object()
                query = req_data.get("query", "")
                if not isinstance(query, str) or len(query) > 512:
                    raise ValueError("搜索内容无效或过长。")
                album_hint = req_data.get("album", "")
                if not isinstance(album_hint, str) or len(album_hint) > 256:
                    raise ValueError("专辑名称无效。")
                result = lookup_metadata_by_keyword(query, album_hint.strip())
                self.send_json(200, result)
            except Exception as exc:
                self.send_json(400, {"error": str(exc) or "搜索曲目信息失败。"})
            return

        if self.path == "/api/search_candidates":
            try:
                req_data = self.read_json_object()
                query = req_data.get("query", "")
                if not isinstance(query, str) or len(query) > 512:
                    raise ValueError("搜索内容无效或过长。")
                self.send_json(200, {"candidates": search_metadata_candidates(query)})
            except Exception as exc:
                self.send_json(400, {"error": str(exc) or "搜索其他匹配结果失败。"})
            return

        if self.path == "/api/parse_local_tag":
            try:
                request_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                if request_type not in {"application/json", "multipart/form-data"}:
                    raise ValueError("请求 Content-Type 无效。")
                raw = self.read_request_body(MAX_UPLOAD)
                if request_type == "application/json":
                    request_data = json.loads(raw)
                    if not isinstance(request_data, dict):
                        raise ValueError("JSON 请求必须是对象。")
                    source = resolve_selected_audio(self.server, str(request_data.get("local_audio_id", "")))
                    if source is None or not is_loopback_address(self.client_address[0]):
                        raise ValueError("所选音乐文件已失效，请重新选择。")
                    result = read_music_metadata(str(source), source.name)
                    self.send_json(200, result)
                else:
                    fields = multipart_fields(self.headers.get("Content-Type", ""), raw)
                    file_part = fields.get("file")
                    if not file_part or not file_part.get_filename():
                        raise ValueError("请选择有效的音乐文件。")

                    filename = Path(file_part.get_filename()).name
                    file_data = file_part.get_payload(decode=True) or b""

                    with tempfile.NamedTemporaryFile(suffix=Path(filename).suffix, delete=False) as tmp:
                        tmp.write(file_data)
                        tmp_path = Path(tmp.name)

                    try:
                        result = read_music_metadata(str(tmp_path), filename)
                        self.send_json(200, result)
                    finally:
                        tmp_path.unlink(missing_ok=True)

            except Exception as exc:
                self.send_json(400, {"error": str(exc) or "解析本地音频标签失败。"})
            return

        if self.path == "/api/package_custom_tag":
            try:
                raw = self.read_request_body(MAX_UPLOAD, "multipart/form-data")
                fields = multipart_fields(self.headers.get("Content-Type", ""), raw)

                audio_part = fields.get("audio_file")
                cover_part = fields.get("cover_file")
                has_audio_file = bool(audio_part and audio_part.get_filename())
                local_audio_id = multipart_text(fields, "local_audio_id")
                local_audio_path = resolve_selected_audio(self.server, local_audio_id) if local_audio_id else None
                if local_audio_path is not None and not is_loopback_address(self.client_address[0]):
                    local_audio_path = None
                if local_audio_id and local_audio_path is None:
                    raise ValueError("所选音乐文件已失效，请重新选择。")

                title = multipart_text(fields, "title")
                artist = multipart_text(fields, "artist")
                album = multipart_text(fields, "album")
                albumartist = multipart_text(fields, "albumartist")
                year = multipart_text(fields, "year")
                lyrics = multipart_text(fields, "lyrics")
                lyrics_format = multipart_text(fields, "lyrics_format") or "auto"
                track_num = multipart_text(fields, "track_num")
                disc_num = multipart_text(fields, "disc_num")
                genre = multipart_text(fields, "genre")
                composer = multipart_text(fields, "composer")
                export_format = multipart_text(fields, "format").lower() or "mp3"
                preferred_engine = multipart_text(fields, "preferred_engine") or "ytdlp"
                filename_append = multipart_text(fields, "filename_append") if multipart_text(fields, "filename_append_enabled") == "1" else ""
                try:
                    trim_start = float(multipart_text(fields, "trim_start") or 0)
                    trim_end = float(multipart_text(fields, "trim_end") or 0)
                except ValueError as exc:
                    raise ValueError("音频裁剪时间无效。") from exc

                if export_format not in FORMATS:
                    export_format = "mp3"
                if not has_audio_file and local_audio_path is None and not title:
                    raise ValueError("请提供本地音频，或先搜索并填写歌曲标题。")

                audio_bytes = (audio_part.get_payload(decode=True) or b"") if has_audio_file else None
                orig_filename = Path(audio_part.get_filename()).name if has_audio_file else (local_audio_path.name if local_audio_path else "")

                ffmpeg = find_ffmpeg_exe()
                if not ffmpeg:
                    raise ValueError("系统中未检测到 FFmpeg 转换工具。")

                with tempfile.TemporaryDirectory(prefix="musicdesk-tag-") as work:
                    work_dir = Path(work)
                    if local_audio_path is not None:
                        in_audio = local_audio_path
                    else:
                        in_audio, orig_filename = acquire_custom_audio_source(
                            audio_bytes, orig_filename, title, artist, preferred_engine, work_dir
                        )

                    staged_audio = work_dir / f"staged.{export_format}"
                    proc = subprocess.run(
                        [ffmpeg, *build_audio_trim_args(in_audio, staged_audio, trim_start, trim_end)],
                        capture_output=True, timeout=300, env=get_env_with_utf8()
                    )
                    if proc.returncode or not staged_audio.is_file():
                        raise ValueError("音频重编码/封装失败，请确保上载的是有效音频。")

                    f = load_music_tag(str(staged_audio))
                    if title: f['title'] = title
                    if artist: f['artist'] = artist
                    if album: f['album'] = album
                    if albumartist: f['albumartist'] = albumartist
                    if year and year.isdigit(): f['year'] = int(year)
                    lyrics = normalize_lyrics(lyrics or fetch_lrc_lyrics(title, artist), lyrics_format)
                    if lyrics and trim_start > 0:
                        lyrics = shift_lrc_timestamps(lyrics, trim_start)
                    if lyrics: f['lyrics'] = lyrics
                    if track_num: f['tracknumber'] = track_num
                    if disc_num: f['discnumber'] = disc_num
                    if genre: f['genre'] = genre
                    if composer: f['composer'] = composer

                    if cover_part and cover_part.get_payload(decode=True):
                        c_bytes = cover_part.get_payload(decode=True)
                        f['artwork'] = c_bytes

                    f.save()
                    final_bytes = staged_audio.read_bytes()

                out_name = make_tag_export_filename(artist, title, orig_filename, export_format, filename_append)

                self.send_response(200)
                self.send_header("Content-Type", FORMATS.get(export_format, "audio/mpeg"))
                self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + urllib.parse.quote(out_name))
                self.send_header("Content-Length", str(len(final_bytes)))
                self.send_api_cors_headers()
                self.end_headers()
                self.wfile.write(final_bytes)

            except Exception as exc:
                self.send_json(400, {"error": str(exc) or "自定义音频封装保存失败。"})
            return

        if self.path == "/api/download":
            try:
                req_data = self.read_json_object()

                for field in ("url", "title", "artist", "album", "albumartist", "year", "thumbnail", "preferred_engine"):
                    if field in req_data and not isinstance(req_data[field], str):
                        raise ValueError(f"{field} 必须是文本。")
                for field in ("title", "artist"):
                    if len(req_data.get(field, "")) > 256:
                        raise ValueError("歌曲信息过长。")
                if "keyword_search" in req_data and not isinstance(req_data["keyword_search"], bool):
                    raise ValueError("keyword_search 必须是布尔值。")
                export_format = str(req_data.get("format", "mp3")).lower()
                if export_format not in FORMATS:
                    raise ValueError("不支持的音频格式。")
                bitrate = str(req_data.get("bitrate", "192"))
                if bitrate not in {"128", "192", "256", "320"}:
                    raise ValueError("不支持的音频比特率。")
                download_lrc = req_data.get("download_lrc", False)
                if not isinstance(download_lrc, bool):
                    raise ValueError("download_lrc 必须是布尔值。")
                for field in ("track_num", "disc_num", "genre", "composer"):
                    if field in req_data and not isinstance(req_data[field], str):
                        raise ValueError(f"{field} 必须是文本。")
                for field in ("lyrics", "lyrics_format"):
                    if field in req_data and not isinstance(req_data[field], str):
                        raise ValueError(f"{field} 必须是文本。")
                
                built_url = build_download_query(
                    req_data.get("url", ""),
                    req_data.get("title", ""),
                    req_data.get("artist", ""),
                    bool(req_data.get("keyword_search")),
                )
                url = validate_download_source(built_url)
                title = req_data.get("title", "未知标题").strip()
                artist = req_data.get("artist", "未知艺人").strip()
                thumbnail = validate_thumbnail_url(req_data.get("thumbnail", ""))
                preferred_engine = req_data.get("preferred_engine", "ytdlp")
                
                if not url:
                    raise ValueError("未获取到有效的歌曲分享链接。")
                
                print(f"\n[MusicDesk 下载请求] {artist} - {title}")
                sys.stdout.flush()
                
                with tempfile.TemporaryDirectory(prefix="musicdesk-dl-") as temp_dir:
                    downloaded_file, source_url = fetch_media_stream(url, title, artist, preferred_engine, temp_dir)
                    
                    cover_p = Path(temp_dir) / "cover.jpg"
                    if thumbnail:
                        try:
                            raw_cover_bytes = fetch_thumbnail(thumbnail)
                            if urllib.parse.urlsplit(thumbnail).hostname in {"i.ytimg.com", "img.youtube.com"}:
                                processed_cover = crop_yt_padding_smart(raw_cover_bytes)
                            else:
                                processed_cover = raw_cover_bytes
                            cover_p.write_bytes(processed_cover)
                        except Exception:
                            cover_p.write_bytes(b"")
                    else:
                        cover_p.write_bytes(b"")
                    
                    out_dir = Path(temp_dir) / "out"
                    final_mp3 = process_and_export_media(
                        source_path=downloaded_file,
                        meta_info=req_data,
                        cover_path=cover_p,
                        export_format=export_format,
                        output_dir=out_dir,
                        bitrate=bitrate,
                        lyrics_text=str(req_data.get("lyrics") or ""),
                        track_num=str(req_data.get("track_num") or ""),
                        disc_num=str(req_data.get("disc_num") or ""),
                        genre=str(req_data.get("genre") or ""),
                        composer=str(req_data.get("composer") or ""),
                    )
                    
                    if download_lrc:
                        lyric_text = normalize_lyrics(str(req_data.get("lyrics") or "") or fetch_lrc_lyrics(title, artist), str(req_data.get("lyrics_format") or "auto"))
                        archive = out_dir / f"{final_mp3.stem}.zip"
                        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
                            bundle.write(final_mp3, final_mp3.name)
                            if lyric_text:
                                bundle.writestr(f"{final_mp3.stem}.lrc", lyric_text.encode("utf-8-sig"))
                            else:
                                bundle.writestr("歌词未找到.txt", "未找到可下载的歌词内容。音频文件已正常保存。")
                        converted = archive.read_bytes()
                        download_name = archive.name
                    else:
                        converted = final_mp3.read_bytes()
                        download_name = final_mp3.name
                
                self.send_response(200)
                self.send_header("Content-Type", "application/zip" if download_lrc else FORMATS[export_format])
                self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + urllib.parse.quote(download_name))
                self.send_header("Access-Control-Expose-Headers", "X-Source-Url, X-Lyrics-Sidecar")
                self.send_api_cors_headers()
                self.send_header("X-Source-Url", urllib.parse.quote(source_url, safe="/:?=&_"))
                if download_lrc:
                    self.send_header("X-Lyrics-Sidecar", "included" if lyric_text else "missing")
                self.send_header("Content-Length", str(len(converted)))
                self.end_headers()
                self.wfile.write(converted)
                
            except Exception as exc:
                self.send_json(400, {"error": str(exc) or "下载失败。"})
            return

        if self.path == "/api/convert":
            ffmpeg = find_ffmpeg_exe()
            if not ffmpeg:
                self.send_json(503, {"error": "未检测到 FFmpeg。"})
                return
            try:
                raw = self.read_request_body(MAX_UPLOAD, "multipart/form-data")
                message = BytesParser(policy=default).parsebytes(
                    b"Content-Type: " + self.headers.get("Content-Type", "").encode("ascii", "replace") + b"\r\nMIME-Version: 1.0\r\n\r\n" + raw
                )
                fields = {part.get_param("name", header="content-disposition"): part for part in message.iter_parts()}
                file_part = fields.get("file")
                local_audio_id = str(fields["local_audio_id"].get_content()).strip() if fields.get("local_audio_id") else ""
                local_audio_path = resolve_selected_audio(self.server, local_audio_id) if local_audio_id else None
                if local_audio_path is not None and not is_loopback_address(self.client_address[0]):
                    local_audio_path = None
                if local_audio_id and local_audio_path is None:
                    raise ValueError("所选音乐文件已失效，请重新选择。")
                fmt = str(fields["format"].get_content()).strip().lower() if fields.get("format") else ""
                has_file = bool(file_part and file_part.get_filename())
                if (not has_file and local_audio_path is None) or fmt not in FORMATS:
                    raise ValueError("请选择音频文件和有效的导出格式。")

                selected_name = file_part.get_filename() if has_file else local_audio_path.name
                source_name = SAFE_NAME.sub("_", Path(selected_name).name).strip(" .") or "audio"
                with tempfile.TemporaryDirectory(prefix="musicdesk-") as work:
                    source = local_audio_path or Path(work) / ("input" + Path(source_name).suffix[:12])
                    target = Path(work) / ("converted." + fmt)
                    if has_file:
                        source.write_bytes(file_part.get_payload(decode=True) or b"")
                    proc = subprocess.run(build_conversion_args(ffmpeg, source, target), capture_output=True, timeout=300, env=get_env_with_utf8())
                    if proc.returncode or not target.exists():
                        raise ValueError("转换失败。请确认上传的是可读取的音频文件。")
                    converted = target.read_bytes()
                
                download_name = limit_filename_length(Path(source_name).stem + "." + fmt)
                self.send_response(200)
                self.send_header("Content-Type", FORMATS[fmt])
                self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + urllib.parse.quote(download_name))
                self.send_header("Content-Length", str(len(converted)))
                self.send_api_cors_headers()
                self.end_headers()
                self.wfile.write(converted)
            except Exception as exc:
                self.send_json(400, {"error": str(exc) or "转换失败。"})
            return

        self.send_json(404, {"error": "找不到该接口。"})

def create_musicdesk_server(host: str = "127.0.0.1", port: int = 8765, api_token: str = ""):
    lan_mode = not is_loopback_address(host)
    if lan_mode and not api_token:
        raise ValueError("局域网服务必须配置配对令牌。")
    if lan_mode and len(api_token) < 24:
        raise ValueError("局域网配对令牌至少需要 24 个字符。")
    server = ThreadingHTTPServer((host, port), Handler)
    server.lan_mode = lan_mode
    server.api_token = api_token
    server.batch_manager = batch_queue.BatchManager()
    return server


def is_api_authorized(authorization: str, token: str) -> bool:
    if not token:
        return False
    try:
        return hmac.compare_digest(authorization.encode("utf-8"), f"Bearer {token}".encode("utf-8"))
    except (AttributeError, UnicodeError):
        return False


def is_loopback_address(address: str) -> bool:
    try:
        return ipaddress.ip_address(address).is_loopback
    except ValueError:
        return False


def get_private_ipv4_addresses() -> list[str]:
    addresses = set()
    for result in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
        address = result[4][0]
        parsed = ipaddress.ip_address(address)
        if parsed.is_private and not parsed.is_loopback and not parsed.is_link_local:
            addresses.add(address)
    return sorted(addresses)


def main(argv=None):
    parser = argparse.ArgumentParser(description="MusicDesk local audio and metadata service")
    parser.add_argument("--lan", action="store_true", help="Expose the API on the local network with a one-run pairing token")
    parser.add_argument("--host", default=None, help="Bind address (defaults to localhost, or all interfaces with --lan)")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--token", default=None, help="Override the generated LAN pairing token")
    args = parser.parse_args(argv)
    if args.token and not args.lan:
        parser.error("--token requires --lan")
    if args.token and len(args.token) < 24:
        parser.error("--token must contain at least 24 characters")
    if args.lan and args.host not in (None, "0.0.0.0"):
        parser.error("--lan only supports binding to 0.0.0.0")
    if args.host == "0.0.0.0" and not args.lan:
        parser.error("Binding beyond localhost requires --lan and its token protection")
    if args.host and args.host not in ("127.0.0.1", "localhost") and not args.lan:
        parser.error("Binding beyond localhost requires --lan and its token protection")

    host = args.host or ("0.0.0.0" if args.lan else "127.0.0.1")
    token = (args.token or secrets.token_urlsafe(24)) if args.lan else ""
    server = create_musicdesk_server(host, args.port, token)
    if args.lan:
        print(f"MusicDesk LAN API listening on port {server.server_port}")
        addresses = get_private_ipv4_addresses()
        for address in addresses:
            print(f"Phone server address: http://{address}:{server.server_port}")
        print(f"One-run pairing token: {token}")
        print("Only share this token with your phone on a trusted private Wi-Fi network.")
    else:
        print(f"MusicDesk is ready at http://127.0.0.1:{server.server_port}")
    sys.stdout.flush()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nMusicDesk stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

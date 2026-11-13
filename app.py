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
from desktop.lyrics import LyricsService
from desktop.metadata import MetadataService
from desktop.server import make_handler
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
_metadata_service = MetadataService(sys.modules[__name__])
_lyrics_service = LyricsService(sys.modules[__name__])

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
    return _metadata_service.search_ytdlp_metadata(query)


def fetch_youtube_rich_metadata(url: str) -> dict:
    return _metadata_service.fetch_youtube_rich_metadata(url)


def lookup_metadata_by_keyword(query: str, album_hint: str = "") -> dict:
    return _metadata_service.lookup_metadata_by_keyword(query, album_hint)


def search_metadata_candidates(query: str, limit: int = 8) -> list[dict]:
    return _metadata_service.search_metadata_candidates(query, limit)


def fetch_spotify_oembed(raw_url: str) -> dict:
    return _metadata_service.fetch_spotify_oembed(raw_url)


def fetch_spotify_embed_html(track_id: str) -> dict:
    return _metadata_service.fetch_spotify_embed_html(track_id)


def lookup_musicbrainz_metadata(title: str, artist: str, known_album: str = "") -> dict:
    return _metadata_service.lookup_musicbrainz_metadata(title, artist, known_album)


def lookup_metadata(raw_url: str) -> dict:
    return _metadata_service.lookup_metadata(raw_url)






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
    return _lyrics_service.fetch_lrc_lyrics(title, artist)


def search_lrc_track(title: str, artist: str) -> dict | None:
    return _lyrics_service.search_lrc_track(title, artist)






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










Handler = make_handler(sys.modules[__name__])


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

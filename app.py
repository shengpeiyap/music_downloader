"""Local music metadata lookup and personal-audio converter with Player, Lyrics View & Custom Tag Editor integration."""
from __future__ import annotations

import base64
import json
import argparse
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

musicbrainzngs.set_useragent("MusicDesk", "1.0", "https://github.com/musicdesk")

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
FORMATS = {"mp3": "audio/mpeg", "wav": "audio/wav", "flac": "audio/flac", "ogg": "audio/ogg", "m4a": "audio/mp4"}
MAX_UPLOAD = 150 * 1024 * 1024
SAFE_NAME = re.compile(r"[^\w .()-]+", re.UNICODE)


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
    get_tag = lambda name: str(audio[name]) if audio[name] else ""

    cover = None
    artwork = audio["artwork"]
    if artwork and artwork.values:
        image = artwork.first
        cover = f"data:{image.mime or 'image/jpeg'};base64," + base64.b64encode(image.data).decode("ascii")

    return {
        "filename": filename,
        "title": get_tag("title"),
        "artist": get_tag("artist"),
        "album": get_tag("album"),
        "albumartist": get_tag("albumartist"),
        "year": get_tag("year"),
        "lyrics": get_tag("lyrics"),
        "cover": cover,
    }


def parse_metadata_search_query(query: str) -> tuple[str, str]:
    """Accept either an artist-title pair or a title-only MusicBrainz query."""
    query = " ".join(query.split())
    match = re.match(r"^(.+?)\s+[-–—]\s+(.+)$", query)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return "未知艺人", query


def lookup_metadata_by_keyword(query: str) -> dict:
    artist, title = parse_metadata_search_query(query)
    if not title:
        raise ValueError("请输入“作者 - 标题”或歌曲标题。")

    metadata = lookup_musicbrainz_metadata(title, artist)
    lyric_track = search_lrc_track(title, artist)
    found_artist = metadata.get("artist") or artist
    if found_artist in {"未知艺人", "Unknown Artist", title} and lyric_track:
        found_artist = lyric_track.get("artistName") or found_artist
    if not any(metadata.get(field) for field in ("album", "year", "cover_url")) and not lyric_track:
        raise ValueError("没有找到匹配的曲目信息，请换一种关键词试试。")
    if artist == "未知艺人" and found_artist in {"未知艺人", title}:
        raise ValueError("没有找到匹配的曲目信息，请换一种关键词试试。")

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
    }


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


def make_tag_export_filename(
    artist: str,
    title: str,
    original_filename: str,
    export_format: str,
    append_text: str = "",
) -> str:
    artist = artist.strip() or "未知艺人"
    title = title.strip() or Path(original_filename).stem or "未知标题"
    suffix = SAFE_NAME.sub("_", append_text).strip(" ._-()")
    base_name = f"{artist} - {title}" + (f" - {suffix}" if suffix else "")
    name = SAFE_NAME.sub("_", f"{base_name}.{export_format}").strip(" .")
    return name or f"未知艺人 - 未知标题.{export_format}"


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
            if not all(is_similar(pixels[x, y], bg_color) for x in range(0, sq_h, 5)):
                left_b = x
                break

        for x in range(sq_w - 1, sq_w // 2, -1):
            if not all(is_similar(pixels[x, y], bg_color) for x in range(0, sq_h, 5)):
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

    if local_path.exists():
        return [str(local_path)]

    which_path = shutil.which(name)
    if which_path:
        return [which_path]

    if name == "yt-dlp":
        return [sys.executable, "-m", "yt_dlp"]
    return [name]


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
            shell=(os.name == 'nt')
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

    cmd = find_executable("yt-dlp") + [
        "-x",
        "--audio-format", "mp3",
        "--no-playlist",
        "--print", "after_move:filepath",
        "--print", "webpage_url",
        "-o", str(base_dir / "ytdlp_%(id)s.%(ext)s"),
        target_url
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
        shell=False
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
        shell=False
    )
    
    if proc.returncode == 0:
        mp3_files = list(base_dir.glob("*.mp3"))
        if mp3_files:
            latest = max(mp3_files, key=lambda p: p.stat().st_mtime)
            print(f"[MusicDesk 音频来源] {url}")
            sys.stdout.flush()
            return latest, url

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

    engines = {
        "ytdlp": lambda: fetch_with_ytdlp(url, title, artist, base_dir),
        "spotdl": lambda: fetch_with_spotdl(url, base_dir),
    }

    valid_engine = preferred_engine if preferred_engine in engines else "ytdlp"

    priority_order = [valid_engine]
    for eng in ["ytdlp", "spotdl"]:
        if eng not in priority_order:
            priority_order.append(eng)

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
    album = meta_info.get("album", "").strip()
    year = meta_info.get("year", "").strip()
    track_num = meta_info.get("track_num", "").strip()

    destination_dir = Path(output_dir)
    destination_dir.mkdir(parents=True, exist_ok=True)
    base = SAFE_NAME.sub("_", f"{artist} - {title}").strip(" .") or "audio"
    destination = destination_dir / f"{base}.mp3"

    with tempfile.TemporaryDirectory(prefix="musicdesk-export-", dir=destination_dir) as work:
        staged = Path(work) / "export.mp3"
        proc = subprocess.run(
            [ffmpeg, "-nostdin", "-v", "error", "-y", "-i", str(source), "-map", "0:a:0", "-vn", str(staged)],
            capture_output=True, timeout=300, env=get_env_with_utf8()
        )
        if proc.returncode or not staged.is_file():
            raise ValueError("FFmpeg 处理音频失败")

        from mutagen.id3 import APIC, ID3, TALB, TDRC, TRCK, TIT2, TPE1, TPE2, USLT

        tags = ID3()
        tags.add(TIT2(encoding=3, text=[title]))
        tags.add(TPE1(encoding=3, text=[artist]))
        tags.add(TPE2(encoding=3, text=[artist]))
        if album:
            tags.add(TALB(encoding=3, text=[album]))
        if year:
            tags.add(TDRC(encoding=3, text=[year]))
        if track_num:
            tags.add(TRCK(encoding=3, text=[track_num]))

        lyrics_text = fetch_lrc_lyrics(title, artist)
        if lyrics_text:
            tags.add(USLT(encoding=3, lang='eng', desc='', text=lyrics_text))

        if cover.is_file() and cover.stat().st_size > 0:
            mime = "image/png" if cover.suffix.lower() == ".png" else "image/jpeg"
            tags.add(APIC(encoding=3, mime=mime, type=3, desc="Cover", data=cover.read_bytes()))

        tags.save(staged, v2_version=3)
        os.replace(staged, destination)

    if cleanup_source:
        source.unlink(missing_ok=True)
    return destination


def parse_share_url(raw: str) -> dict:
    try:
        parts = urllib.parse.urlsplit(raw.strip())
    except ValueError as exc:
        raise ValueError("请输入有效的 Spotify 或 YouTube Music 分享链接。") from exc
    host = (parts.hostname or "").lower()
    if parts.scheme != "https":
        raise ValueError("仅支持 HTTPS 分享链接。")
    if host in {"open.spotify.com", "spotify.com", "www.spotify.com"}:
        match = re.fullmatch(r"/track/([A-Za-z0-9]+)/*", parts.path)
        if match:
            track_id = match.group(1)
            return {"provider": "spotify", "id": track_id, "url": f"https://open.spotify.com/track/{track_id}"}
    if host in {"music.youtube.com", "youtube.com", "www.youtube.com"}:
        video_id = urllib.parse.parse_qs(parts.query).get("v", [None])[0]
        if parts.path == "/watch" and video_id and re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
            return {"provider": "youtube", "id": video_id, "url": f"https://www.youtube.com/watch?v={video_id}"}
    if host in {"youtu.be", "www.youtu.be"}:
        video_id = parts.path.strip("/")
        if re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
            return {"provider": "youtube", "id": video_id, "url": f"https://www.youtube.com/watch?v={video_id}"}
    raise ValueError("目前支持 Spotify 单曲链接，以及 YouTube Music / YouTube 视频链接。")


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
        
        query = f'recording:"{title}"'
        if clean_artist:
            query += f' AND artist:"{clean_artist}"'
        if known_album:
            query += f' AND release:"{known_album}"'

        result = musicbrainzngs.search_recordings(query=query, limit=15)
        recordings = result.get("recording-list", [])

        if not recordings and known_album:
            query_fallback = f'recording:"{title}"'
            if clean_artist: query_fallback += f' AND artist:"{clean_artist}"'
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
        if not getattr(self.server, "lan_mode", False):
            return
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Expose-Headers", "Content-Disposition, X-Source-Url")
        self.send_header("Vary", "Origin")

    def is_api_authorized(self) -> bool:
        token = getattr(self.server, "api_token", "")
        if not token:
            return True
        supplied = self.headers.get("Authorization", "")
        return hmac.compare_digest(supplied, f"Bearer {token}")

    def do_OPTIONS(self):
        if not self.path.startswith("/api/") or not getattr(self.server, "lan_mode", False):
            self.send_error(404)
            return
        self.send_response(204)
        self.send_api_cors_headers()
        self.end_headers()

    def do_GET(self):
        if self.path == "/api/status":
            if not self.is_api_authorized():
                self.send_json(401, {"error": "配对密钥无效。"})
                return
            self.send_json(200, {"ok": True, "service": "MusicDesk"})
            return
        if getattr(self.server, "lan_mode", False):
            # LAN mode is an API-only listener; never expose project files/source.
            self.send_error(404)
            return
        super().do_GET()

    def do_HEAD(self):
        if getattr(self.server, "lan_mode", False):
            self.send_error(404)
            return
        super().do_HEAD()

    def do_POST(self):
        if self.path.startswith("/api/") and not self.is_api_authorized():
            self.send_json(401, {"error": "配对密钥无效。"})
            return
        if self.path == "/api/metadata":
            try:
                body = self.rfile.read(min(int(self.headers.get("Content-Length", "0")), 8192))
                result = lookup_metadata(json.loads(body).get("url", ""))
                print(f"[MusicDesk 完整 Metadata] 歌名: {result.get('title')} | 歌手: {result.get('artist')} | 专辑: {result.get('album')} | 年份: {result.get('year')}")
                sys.stdout.flush()
                self.send_json(200, result)
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                self.send_json(400, {"error": str(exc)})
            return

        if self.path == "/api/lyrics_text":
            try:
                body = self.rfile.read(min(int(self.headers.get("Content-Length", "0")), 8192))
                req_data = json.loads(body)
                title = req_data.get("title", "")
                artist = req_data.get("artist", "")
                lrc = fetch_lrc_lyrics(title, artist)
                if not lrc:
                    raise ValueError("未在公开歌词库中检索到对应的同步 LRC 歌词。")
                self.send_json(200, {"lyrics": lrc})
            except Exception as exc:
                self.send_json(400, {"error": str(exc)})
            return

        if self.path == "/api/search_metadata":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 1 or length > 8192:
                    raise ValueError("搜索内容无效或过长。")
                req_data = json.loads(self.rfile.read(length))
                result = lookup_metadata_by_keyword(str(req_data.get("query", "")))
                self.send_json(200, result)
            except Exception as exc:
                self.send_json(400, {"error": str(exc) or "搜索曲目信息失败。"})
            return

        if self.path == "/api/parse_local_tag":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 1 or length > MAX_UPLOAD:
                    raise ValueError("文件不能为空或超过 150 MB。")
                raw = self.rfile.read(length)
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
                length = int(self.headers.get("Content-Length", "0"))
                if length < 1 or length > MAX_UPLOAD:
                    raise ValueError("数据超出大小限制。")
                raw = self.rfile.read(length)
                fields = multipart_fields(self.headers.get("Content-Type", ""), raw)

                audio_part = fields.get("audio_file")
                cover_part = fields.get("cover_file")
                has_audio_file = bool(audio_part and audio_part.get_filename())

                title = multipart_text(fields, "title")
                artist = multipart_text(fields, "artist")
                album = multipart_text(fields, "album")
                albumartist = multipart_text(fields, "albumartist")
                year = multipart_text(fields, "year")
                lyrics = multipart_text(fields, "lyrics")
                export_format = multipart_text(fields, "format").lower() or "mp3"
                preferred_engine = multipart_text(fields, "preferred_engine") or "ytdlp"
                filename_append = multipart_text(fields, "filename_append") if multipart_text(fields, "filename_append_enabled") == "1" else ""

                if export_format not in FORMATS:
                    export_format = "mp3"
                if not has_audio_file and not title:
                    raise ValueError("请提供本地音频，或先搜索并填写歌曲标题。")

                audio_bytes = (audio_part.get_payload(decode=True) or b"") if has_audio_file else None
                orig_filename = Path(audio_part.get_filename()).name if has_audio_file else ""

                ffmpeg = find_ffmpeg_exe()
                if not ffmpeg:
                    raise ValueError("系统中未检测到 FFmpeg 转换工具。")

                with tempfile.TemporaryDirectory(prefix="musicdesk-tag-") as work:
                    work_dir = Path(work)
                    in_audio, orig_filename = acquire_custom_audio_source(
                        audio_bytes, orig_filename, title, artist, preferred_engine, work_dir
                    )

                    staged_audio = work_dir / f"staged.{export_format}"
                    proc = subprocess.run(
                        [ffmpeg, "-nostdin", "-v", "error", "-y", "-i", str(in_audio), "-map", "0:a:0", "-vn", str(staged_audio)],
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
                    lyrics = lyrics or fetch_lrc_lyrics(title, artist)
                    if lyrics: f['lyrics'] = lyrics

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
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(min(length, 8192))
                req_data = json.loads(body)
                
                url = build_download_query(
                    req_data.get("url", ""),
                    req_data.get("title", ""),
                    req_data.get("artist", ""),
                    bool(req_data.get("keyword_search")),
                )
                title = req_data.get("title", "未知标题").strip()
                artist = req_data.get("artist", "未知艺人").strip()
                thumbnail = req_data.get("thumbnail", "")
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
                            req = urllib.request.Request(thumbnail, headers={"User-Agent": "Mozilla/5.0"})
                            with urllib.request.urlopen(req, timeout=10) as res:
                                raw_cover_bytes = res.read()
                                if "ytimg.com" in thumbnail or "youtube.com" in thumbnail:
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
                        export_format="mp3",
                        output_dir=out_dir
                    )
                    
                    converted = final_mp3.read_bytes()
                    download_name = final_mp3.name
                
                self.send_response(200)
                self.send_header("Content-Type", "audio/mpeg")
                self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + urllib.parse.quote(download_name))
                self.send_header("Access-Control-Expose-Headers", "X-Source-Url")
                self.send_api_cors_headers()
                self.send_header("X-Source-Url", urllib.parse.quote(source_url, safe="/:?=&_"))
                self.send_header("Content-Length", str(len(converted)))
                self.end_headers()
                self.wfile.write(converted)
                
            except (ValueError, TimeoutError, OSError, json.JSONDecodeError) as exc:
                self.send_json(400, {"error": str(exc) or "下载失败。"})
            return

        if self.path == "/api/convert":
            ffmpeg = find_ffmpeg_exe()
            if not ffmpeg:
                self.send_json(503, {"error": "未检测到 FFmpeg。"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 1 or length > MAX_UPLOAD:
                    raise ValueError("文件不能为空或超过 150 MB。")
                raw = self.rfile.read(length)
                message = BytesParser(policy=default).parsebytes(
                    b"Content-Type: " + self.headers.get("Content-Type", "").encode("ascii", "replace") + b"\r\nMIME-Version: 1.0\r\n\r\n" + raw
                )
                fields = {part.get_param("name", header="content-disposition"): part for part in message.iter_parts()}
                file_part = fields.get("file")
                fmt = str(fields["format"].get_content()).strip().lower() if fields.get("format") else ""
                if not file_part or not file_part.get_filename() or fmt not in FORMATS:
                    raise ValueError("请选择音频文件和有效的导出格式。")
                
                source_name = SAFE_NAME.sub("_", Path(file_part.get_filename()).name).strip(" .") or "audio"
                with tempfile.TemporaryDirectory(prefix="musicdesk-") as work:
                    source = Path(work) / ("input" + Path(source_name).suffix[:12])
                    target = Path(work) / ("converted." + fmt)
                    source.write_bytes(file_part.get_payload(decode=True) or b"")
                    proc = subprocess.run([ffmpeg, "-nostdin", "-v", "error", "-i", str(source), "-y", str(target)], capture_output=True, timeout=300, env=get_env_with_utf8())
                    if proc.returncode or not target.exists():
                        raise ValueError("转换失败。请确认上传的是可读取的音频文件。")
                    converted = target.read_bytes()
                
                download_name = Path(source_name).stem + "." + fmt
                self.send_response(200)
                self.send_header("Content-Type", FORMATS[fmt])
                self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + urllib.parse.quote(download_name))
                self.send_header("Content-Length", str(len(converted)))
                self.send_api_cors_headers()
                self.end_headers()
                self.wfile.write(converted)
            except (ValueError, TimeoutError, OSError) as exc:
                self.send_json(400, {"error": str(exc) or "转换失败。"})
            return

        self.send_json(404, {"error": "找不到该接口。"})

def create_musicdesk_server(host: str = "127.0.0.1", port: int = 8765, api_token: str = ""):
    server = ThreadingHTTPServer((host, port), Handler)
    server.lan_mode = bool(api_token)
    server.api_token = api_token
    return server


def is_api_authorized(authorization: str, token: str) -> bool:
    return not token or hmac.compare_digest(authorization, f"Bearer {token}")


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

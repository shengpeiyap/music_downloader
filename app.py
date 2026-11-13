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
from desktop.downloads import DownloadsService
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
_downloads_service = DownloadsService(sys.modules[__name__])

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
    return _downloads_service.list_playlist_entries(url)


def process_batch_track(track: dict, options: dict, dest_dir: Path) -> Path:
    return _downloads_service.process_batch_track(track, options, dest_dir)


def build_download_query(url: str, title: str, artist: str, keyword_search: bool) -> str:
    return _downloads_service.build_download_query(url, title, artist, keyword_search)


def validate_download_source(source: str) -> str:
    return _downloads_service.validate_download_source(source)


def validate_thumbnail_url(url: str) -> str:
    return _downloads_service.validate_thumbnail_url(url)


def fetch_thumbnail(url: str) -> bytes:
    return _downloads_service.fetch_thumbnail(url)


def acquire_custom_audio_source(audio_bytes: bytes | None, original_filename: str, title: str, artist: str, preferred_engine: str, work_dir: Path) -> tuple[Path, str]:
    return _downloads_service.acquire_custom_audio_source(audio_bytes, original_filename, title, artist, preferred_engine, work_dir)


def find_executable(name: str) -> list[str]:
    return _downloads_service.find_executable(name)


def get_ytdlp_js_runtime_args() -> list[str]:
    return _downloads_service.get_ytdlp_js_runtime_args()


def log_downloader_failure(engine: str, proc: subprocess.CompletedProcess[str]) -> None:
    return _downloads_service.log_downloader_failure(engine, proc)


def fetch_with_ytdlp(url: str, title: str, artist: str, base_dir: Path) -> tuple[Path | None, str]:
    return _downloads_service.fetch_with_ytdlp(url, title, artist, base_dir)


def fetch_with_spotdl(url: str, base_dir: Path) -> tuple[Path | None, str]:
    return _downloads_service.fetch_with_spotdl(url, base_dir)


def fetch_media_stream(url: str, title: str = "", artist: str = "", preferred_engine: str = "ytdlp", temp_dir: str | Path | None = None) -> tuple[Path, str]:
    return _downloads_service.fetch_media_stream(url, title, artist, preferred_engine, temp_dir)


def process_and_export_media(source_path: str | Path, meta_info: dict, cover_path: str | Path, export_format: str, output_dir: str | Path, *, cleanup_source: bool = True, bitrate: str = "192", lyrics_text: str = "", track_num: str = "", genre: str = "", composer: str = "", disc_num: str = "") -> Path:
    return _downloads_service.process_and_export_media(
        source_path, meta_info, cover_path, export_format, output_dir,
        cleanup_source=cleanup_source, bitrate=bitrate, lyrics_text=lyrics_text,
        track_num=track_num, genre=genre, composer=composer, disc_num=disc_num,
    )














class SafeThumbnailRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_thumbnail_url(urllib.parse.urljoin(req.full_url, newurl))
        return super().redirect_request(req, fp, code, msg, headers, newurl)




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

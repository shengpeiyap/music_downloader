"""Local music metadata lookup and personal-audio converter."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import ipaddress
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from email.parser import BytesParser
from email.policy import default

ROOT = Path(__file__).resolve().parent
FORMATS = {"mp3": "audio/mpeg", "wav": "audio/wav", "flac": "audio/flac", "ogg": "audio/ogg", "m4a": "audio/mp4"}
MAX_UPLOAD = 150 * 1024 * 1024
SAFE_NAME = re.compile(r"[^\w .()-]+", re.UNICODE)


def fetch_media_stream(url: str, temp_dir: str | Path | None = None) -> Path:
    """Stream a media URL into a uniquely named file in the local temp directory.

    The caller owns the returned file and should remove it when finished.
    Only HTTP(S) URLs without embedded credentials are accepted.
    """
    try:
        parsed = urllib.parse.urlsplit(url.strip())
        host = parsed.hostname
        if parsed.scheme not in {"http", "https"} or not host or parsed.username or parsed.password:
            raise ValueError("A valid HTTP(S) media URL is required")
        # Avoid direct requests to local/private IP literals from this local service.
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address and (address.is_private or address.is_loopback or address.is_link_local or address.is_reserved):
            raise ValueError("Local and private network addresses are not allowed")
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("A valid HTTP(S) media URL is required") from exc

    request = urllib.request.Request(url.strip(), headers={"User-Agent": "MusicDesk/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            final = urllib.parse.urlsplit(response.geturl())
            if final.scheme not in {"http", "https"}:
                raise ValueError("Unsupported redirect scheme")
            with tempfile.NamedTemporaryFile(mode="wb", prefix="musicdesk-media-", suffix=".bin",
                                             dir=temp_dir, delete=False) as output:
                path = Path(output.name)
                shutil.copyfileobj(response, output, length=64 * 1024)
        return path
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ValueError("Unable to fetch media stream") from exc


def find_ffmpeg() -> str | None:
    """Use the app-managed FFmpeg binary, then fall back to the system PATH."""
    try:
        import imageio_ffmpeg

        bundled = imageio_ffmpeg.get_ffmpeg_exe()
        if Path(bundled).is_file():
            return bundled
    except (ImportError, OSError, RuntimeError):
        pass
    return shutil.which("ffmpeg")


def parse_share_url(raw: str) -> dict:
    """Validate supported share URLs and return provider, ID, and canonical URL."""
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


def lookup_metadata(raw_url: str) -> dict:
    link = parse_share_url(raw_url)
    if link["provider"] == "spotify":
        endpoint = "https://open.spotify.com/oembed?url=" + urllib.parse.quote(link["url"], safe="")
    else:
        endpoint = "https://www.youtube.com/oembed?format=json&url=" + urllib.parse.quote(link["url"], safe="")
    request = urllib.request.Request(endpoint, headers={"User-Agent": "MusicDesk/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            data = json.loads(response.read(1024 * 1024))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ValueError("无法读取该链接的公开 metadata。请检查链接并稍后重试。") from exc
    return {
        "provider": link["provider"], "id": link["id"], "url": link["url"],
        "title": data.get("title", "未知标题"), "artist": data.get("author_name", "未知艺人"),
        "thumbnail": data.get("thumbnail_url"),
    }


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def send_json(self, code: int, value: dict):
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path == "/api/metadata":
            try:
                body = self.rfile.read(min(int(self.headers.get("Content-Length", "0")), 8192))
                result = lookup_metadata(json.loads(body).get("url", ""))
                self.send_json(200, result)
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                self.send_json(400, {"error": str(exc)})
            return
        if self.path != "/api/convert":
            self.send_json(404, {"error": "找不到该接口。"})
            return
        ffmpeg = find_ffmpeg()
        if not ffmpeg:
            self.send_json(503, {"error": "未检测到 FFmpeg。请先安装 FFmpeg 并加入 PATH。"})
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
                proc = subprocess.run([ffmpeg, "-nostdin", "-v", "error", "-i", str(source), "-y", str(target)], capture_output=True, timeout=300)
                if proc.returncode or not target.exists():
                    raise ValueError("转换失败。请确认上传的是可读取的音频文件。")
                converted = target.read_bytes()
            download_name = Path(source_name).stem + "." + fmt
            self.send_response(200)
            self.send_header("Content-Type", FORMATS[fmt])
            self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + urllib.parse.quote(download_name))
            self.send_header("Content-Length", str(len(converted)))
            self.end_headers()
            self.wfile.write(converted)
        except (ValueError, TimeoutError, OSError) as exc:
            self.send_json(400, {"error": str(exc) or "转换失败。"})


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 8765), Handler)
    print("MusicDesk is ready at http://127.0.0.1:8765")
    server.serve_forever()

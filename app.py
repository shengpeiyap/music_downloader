"""Local music metadata lookup and personal-audio converter with MusicBrainz & SpotDL integration."""
from __future__ import annotations

import json
import html as html_module
import os
import re
import shutil
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

import musicbrainzngs

musicbrainzngs.set_useragent("MusicDesk", "1.0", "https://github.com/musicdesk")

ROOT = Path(__file__).resolve().parent
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


def find_ffmpeg_exe() -> str | None:
    try:
        import imageio_ffmpeg
        bundled = imageio_ffmpeg.get_ffmpeg_exe()
        if Path(bundled).is_file():
            return bundled
    except (ImportError, OSError, RuntimeError):
        pass
    return shutil.which("ffmpeg")


# Keep compatibility with earlier callers and existing tests.
find_ffmpeg = find_ffmpeg_exe


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


def fetch_with_ytdlp(url: str, title: str, artist: str, base_dir: Path) -> Path | None:
    target_url = url.strip()
    if "spotify.com" in target_url:
        clean_title = re.sub(r"\s*-\s*Topic$", "", title, flags=re.IGNORECASE).strip()
        clean_artist = "" if artist in {"未知艺人", "Unknown Artist"} else artist.strip()
        search_query = f"{clean_artist} {clean_title} Official Audio".strip()
        if not search_query or search_query == "Official Audio":
            search_query = "music"
        target_url = f"ytsearch1:{search_query}"
        print(f"[yt-dlp 引擎] 检索关键词: {search_query}")

    cmd = find_executable("yt-dlp") + [
        "-x",
        "--audio-format", "mp3",
        "--no-playlist",
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
        shell=(os.name == 'nt')
    )
    
    if proc.returncode == 0:
        mp3_files = list(base_dir.glob("ytdlp_*.mp3"))
        if mp3_files:
            latest = max(mp3_files, key=lambda p: p.stat().st_mtime)
            print(f"[MusicDesk 成功] yt-dlp 成功提取: {latest.name}")
            return latest
    
    print(f"[yt-dlp 抓取失败]")
    sys.stdout.flush()
    return None


def fetch_with_spotdl(url: str, base_dir: Path) -> Path | None:
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
        shell=(os.name == 'nt')
    )
    
    if proc.returncode == 0:
        mp3_files = list(base_dir.glob("*.mp3"))
        if mp3_files:
            latest = max(mp3_files, key=lambda p: p.stat().st_mtime)
            return latest

    print(f"[spotdl 下载未成功]")
    sys.stdout.flush()
    return None


def fetch_media_stream(url: str, title: str = "", artist: str = "", preferred_engine: str = "ytdlp", temp_dir: str | Path | None = None) -> Path:
    base_dir = Path(temp_dir) if temp_dir else Path(tempfile.gettempdir())

    engines = {
        "ytdlp": lambda: fetch_with_ytdlp(url, title, artist, base_dir),
        "spotdl": lambda: fetch_with_spotdl(url, base_dir),
    }

    priority_order = [preferred_engine]
    for eng in ["ytdlp", "spotdl"]:
        if eng not in priority_order:
            priority_order.append(eng)

    for eng_name in priority_order:
        res_file = engines[eng_name]()
        if res_file and res_file.is_file():
            return res_file

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

        from mutagen.id3 import APIC, ID3, TALB, TDRC, TRCK, TIT2, TPE1, TPE2

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


def fetch_spotify_via_spotdl_sdk(url: str) -> dict | None:
    """初始化并调用 spotdl SDK，带 Client 初始化保护"""
    try:
        from spotdl.utils.spotify import SpotifyClient
        from spotdl.utils.search import Song
        
        # 先安全初始化 spotdl 的客户端，防止抛出 Client not created 异常
        try:
            SpotifyClient.init()
        except Exception:
            pass
            
        song = Song.from_url(url)
        return {
            "title": song.name,
            "artist": song.artist,
            "album": song.album_name,
            "year": str(song.year) if song.year else "",
            "track_num": str(song.track_number) if song.track_number else "",
            "thumbnail": song.cover_url
        }
    except Exception as e:
        print(f"[MusicDesk] spotdl SDK 抓取未使用: {e}")
        return None


def fetch_spotify_web_html(raw_url: str) -> dict:
    """直接解析 Spotify 页面结构（提取歌名、歌手与 1:1 封面）"""
    meta = {"title": "", "artist": "", "thumbnail": None}
    try:
        req = urllib.request.Request(raw_url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8"
        })
        with urllib.request.urlopen(req, timeout=6) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
            # Parse attributes independently: Spotify can reorder meta attributes.
            for tag in re.findall(r"<meta\b[^>]*>", html, flags=re.IGNORECASE):
                attrs = dict((key.lower(), html_module.unescape(value)) for key, value in re.findall(
                    r'''([\w:-]+)\s*=\s*["']([^"']*)["']''', tag, flags=re.IGNORECASE
                ))
                key = (attrs.get("property") or attrs.get("name") or "").lower()
                content = attrs.get("content", "").strip()
                if key == "og:title":
                    meta["title"] = content
                elif key in {"twitter:audio:artist_name", "music:musician"}:
                    meta["artist"] = content
                elif key == "og:description" and not meta["artist"]:
                    meta["artist"] = re.split(r"\s*[·|]\s*", content, maxsplit=1)[0]
                elif key == "og:image":
                    meta["thumbnail"] = content
            title_m = re.search(r'<meta property="og:title" content="([^"]+)"', html)
            artist_m = re.search(r'<meta property="twitter:audio:artist_name" content="([^"]+)"', html) or \
                       re.search(r'<meta name="music:musician" content="([^"]+)"', html) or \
                       re.search(r'<meta property="og:description" content="([^·"]+)', html)
            img_m = re.search(r'<meta property="og:image" content="([^"]+)"', html)

            if title_m: meta["title"] = title_m.group(1).strip()
            if artist_m: meta["artist"] = artist_m.group(1).strip()
            if img_m: meta["thumbnail"] = img_m.group(1).strip()
    except Exception:
        pass
    return meta


def lookup_musicbrainz_metadata(title: str, artist: str) -> dict:
    """ MusicBrainz 检索：按发行日期升序筛选原版专辑 """
    print(f"[MusicDesk - MusicBrainz] 正在检索: {title} - {artist}")
    res_meta = {"artist": artist, "album": "", "year": "", "track_num": "", "cover_url": None}
    if not title or title == "未知标题":
        return res_meta

    try:
        clean_artist = "" if artist in {"未知艺人", "Unknown Artist"} else artist.strip()
        query = f'recording:"{title}"'
        if clean_artist:
            query += f' AND artist:"{clean_artist}"'

        result = musicbrainzngs.search_recordings(query=query, limit=10)
        recordings = result.get("recording-list", [])

        for rec in recordings:
            artist_credit = rec.get("artist-credit", [])
            if artist_credit and isinstance(artist_credit[0], dict):
                mb_artist = artist_credit[0].get("artist", {}).get("name", "")
                if mb_artist and (not clean_artist or res_meta["artist"] == "未知艺人"):
                    res_meta["artist"] = mb_artist

            releases = rec.get("release-list", [])
            # 依发行时间排序，优先获取最早期发行的原版专辑
            releases_sorted = sorted(releases, key=lambda r: r.get("date", "9999"))

            for rel in releases_sorted:
                rel_id = rel.get("id")
                album_name = rel.get("title", "")
                date_str = rel.get("date", "")
                year = date_str.split("-")[0] if date_str else ""

                cover_url = None
                try:
                    test_url = f"https://coverartarchive.org/release/{rel_id}/front-500"
                    req = urllib.request.Request(test_url, method='HEAD', headers={"User-Agent": "MusicDesk/1.0"})
                    with urllib.request.urlopen(req, timeout=3):
                        cover_url = test_url
                except Exception:
                    cover_url = None

                res_meta["album"] = album_name
                res_meta["year"] = year
                if cover_url:
                    res_meta["cover_url"] = cover_url
                    print(f"[MusicDesk - MusicBrainz] 匹配到专辑 [{album_name} ({year})] 封面: {cover_url}")
                    return res_meta

                if album_name and not res_meta["album"]:
                    res_meta["album"] = album_name
                    res_meta["year"] = year

    except Exception as e:
        print(f"[MusicDesk - MusicBrainz 提示]: {e}")

    return res_meta


def lookup_metadata(raw_url: str) -> dict:
    link = parse_share_url(raw_url)
    title, artist, album, year, track_num, thumbnail = "未知标题", "未知艺人", "", "", "", None

    # 1. 如果是 Spotify 链接，先尝试 SDK，若未成功再降级使用 HTML/oEmbed 提取
    if link["provider"] == "spotify":
        spot_sdk = fetch_spotify_via_spotdl_sdk(link["url"])
        if spot_sdk:
            title = spot_sdk["title"]
            artist = spot_sdk["artist"]
            album = spot_sdk["album"]
            year = spot_sdk["year"]
            track_num = spot_sdk["track_num"]
            thumbnail = spot_sdk["thumbnail"]
        else:
            web_meta = fetch_spotify_web_html(link["url"])
            if web_meta.get("title"): title = web_meta["title"]
            if web_meta.get("artist"): artist = web_meta["artist"]
            if web_meta.get("thumbnail"): thumbnail = web_meta["thumbnail"]

    # 2. 如果是 YouTube 链接
    elif link["provider"] == "youtube":
        try:
            endpoint = "https://www.youtube.com/oembed?format=json&url=" + urllib.parse.quote(link["url"], safe="")
            req = urllib.request.Request(endpoint, headers={"User-Agent": "MusicDesk/1.0"})
            with urllib.request.urlopen(req, timeout=6) as response:
                data = json.loads(response.read())
                title = data.get("title", title)
                artist = data.get("author_name", artist)
                thumbnail = data.get("thumbnail_url")
        except Exception:
            pass

    artist = re.sub(r"\s*-\s*Topic$", "", artist, flags=re.IGNORECASE).strip()

    # 3. 补充 MusicBrainz 精细专辑数据
    if title and title != "未知标题":
        mb_meta = lookup_musicbrainz_metadata(title, artist)
        if mb_meta.get("artist") and artist == "未知艺人":
            artist = mb_meta["artist"]
        if mb_meta.get("album") and not album:
            album = mb_meta["album"]
        if mb_meta.get("year") and not year:
            year = mb_meta["year"]
        if mb_meta.get("cover_url") and not thumbnail:
            thumbnail = mb_meta["cover_url"]

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
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
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

        if self.path == "/api/download":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(min(length, 8192))
                req_data = json.loads(body)
                
                url = req_data.get("url", "").strip()
                title = req_data.get("title", "未知标题").strip()
                artist = req_data.get("artist", "未知艺人").strip()
                thumbnail = req_data.get("thumbnail", "")
                preferred_engine = req_data.get("preferred_engine", "ytdlp")
                
                if not url:
                    raise ValueError("未获取到有效的歌曲分享链接。")
                
                print(f"\n[MusicDesk 下载请求] {artist} - {title}")
                sys.stdout.flush()
                
                with tempfile.TemporaryDirectory(prefix="musicdesk-dl-") as temp_dir:
                    downloaded_file = fetch_media_stream(url, title, artist, preferred_engine, temp_dir)
                    
                    cover_p = Path(temp_dir) / "cover.jpg"
                    if thumbnail:
                        try:
                            req = urllib.request.Request(thumbnail, headers={"User-Agent": "Mozilla/5.0"})
                            with urllib.request.urlopen(req, timeout=10) as res:
                                cover_p.write_bytes(res.read())
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
                self.end_headers()
                self.wfile.write(converted)
            except (ValueError, TimeoutError, OSError) as exc:
                self.send_json(400, {"error": str(exc) or "转换失败。"})
            return

        self.send_json(404, {"error": "找不到该接口。"})


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 8765), Handler)
    print("MusicDesk is ready at http://127.0.0.1:8765")
    sys.stdout.flush()
    server.serve_forever()

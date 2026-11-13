"""HTTP request handling for the desktop MusicDesk service.

The app module is injected as a service namespace so existing app.* patch points remain valid.
"""
from __future__ import annotations

from http.server import SimpleHTTPRequestHandler


def make_handler(services):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(services.ROOT), **kwargs)

        def send_json(self, code: int, value: dict):
            body = services.json.dumps(value, ensure_ascii=False).encode("utf-8")
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
            if services.is_loopback_address(self.client_address[0]) and self.headers.get("Origin") != "null":
                return True
            token = getattr(self.server, "api_token", "")
            supplied = self.headers.get("Authorization", "")
            return services.is_api_authorized(supplied, token)

        def validate_request_origin(self) -> bool:
            try:
                parsed_host = services.urllib.parse.urlsplit("//" + self.headers.get("Host", ""))
                host = (parsed_host.hostname or "").lower().rstrip(".")
                port = parsed_host.port
            except ValueError:
                return False
            valid_hosts = {"localhost", "127.0.0.1", "::1"}
            if getattr(self.server, "lan_mode", False):
                valid_hosts.update(services.get_private_ipv4_addresses())
            if (host not in valid_hosts or port != self.server.server_port or parsed_host.username or
                    parsed_host.password or parsed_host.path or parsed_host.query or parsed_host.fragment):
                return False
            origin = self.headers.get("Origin")
            if origin is None:
                return True
            if origin == "null":
                return bool(getattr(self.server, "lan_mode", False))
            try:
                parsed_origin = services.urllib.parse.urlsplit(origin)
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

        def read_json_object(self, max_size: int = services.MAX_API_JSON) -> dict:
            value = services.json.loads(self.read_request_body(max_size, "application/json"))
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
            self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + services.urllib.parse.quote("MusicDesk-批量下载.zip"))
            self.send_header("Content-Length", str(size))
            self.send_api_cors_headers()
            self.end_headers()
            with job.zip_path.open("rb") as handle:
                services.shutil.copyfileobj(handle, self.wfile)

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
                    "api_version": services.MUSICDESK_API_VERSION,
                    "capabilities": list(services.MUSICDESK_API_CAPABILITIES),
                })
                return
            batch_match = services.re.fullmatch(r"/api/batch/([0-9a-f]{32})(/zip)?", services.urllib.parse.urlsplit(self.path).path)
            if batch_match:
                self.handle_batch_get(batch_match.group(1), bool(batch_match.group(2)))
                return
            if getattr(self.server, "lan_mode", False) and not services.is_loopback_address(self.client_address[0]):
                # Remote LAN clients get the API only; keep the browser UI local to this computer.
                self.send_error(404)
                return
            local_audio_prefix = "/api/local-audio/"
            request_path = services.urllib.parse.urlsplit(self.path).path
            if request_path.startswith(local_audio_prefix):
                if not services.is_loopback_address(self.client_address[0]):
                    self.send_error(404)
                    return
                services.serve_local_audio(self, request_path[len(local_audio_prefix):])
                return
            super().do_GET()

        def do_HEAD(self):
            if self.reject_invalid_request():
                return
            if getattr(self.server, "lan_mode", False) and not services.is_loopback_address(self.client_address[0]):
                self.send_error(404)
                return
            local_audio_prefix = "/api/local-audio/"
            request_path = services.urllib.parse.urlsplit(self.path).path
            if request_path.startswith(local_audio_prefix):
                if not services.is_loopback_address(self.client_address[0]):
                    self.send_error(404)
                    return
                services.serve_local_audio(self, request_path[len(local_audio_prefix):])
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
                    result = services.lookup_metadata(source)
                    print(f"[MusicDesk 完整 Metadata] 歌名: {result.get('title')} | 歌手: {result.get('artist')} | 专辑: {result.get('album')} | 年份: {result.get('year')}")
                    services.sys.stdout.flush()
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
                    lrc = services.fetch_lrc_lyrics(title, artist)
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
                    self.send_json(200, services.list_playlist_entries(url))
                except services.subprocess.TimeoutExpired:
                    self.send_json(400, {"error": "读取播放列表超时，请稍后重试。"})
                except Exception as exc:
                    self.send_json(400, {"error": str(exc) or "读取播放列表失败。"})
                return

            if self.path == "/api/batch":
                try:
                    req_data = self.read_json_object(256 * 1024)
                    export_format = str(req_data.get("format", "mp3")).lower()
                    if export_format not in services.FORMATS:
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
                        entry = services.batch_queue.clean_playlist_entry(raw if isinstance(raw, dict) else {})
                        if entry and entry["id"] not in seen:
                            seen.add(entry["id"])
                            tracks.append(entry)
                    job = self.server.batch_manager.start(
                        tracks, {"format": export_format, "bitrate": bitrate, "download_lrc": download_lrc}, services.process_batch_track)
                    self.send_json(200, {"job_id": job.id, "total": len(tracks)})
                except RuntimeError as exc:
                    self.send_json(409, {"error": str(exc)})
                except Exception as exc:
                    self.send_json(400, {"error": str(exc) or "无法开始批量下载。"})
                return

            cancel_match = services.re.fullmatch(r"/api/batch/([0-9a-f]{32})/cancel", self.path)
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
                    result = services.lookup_metadata_by_keyword(query, album_hint.strip())
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
                    self.send_json(200, {"candidates": services.search_metadata_candidates(query)})
                except Exception as exc:
                    self.send_json(400, {"error": str(exc) or "搜索其他匹配结果失败。"})
                return

            if self.path == "/api/parse_local_tag":
                try:
                    request_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                    if request_type not in {"application/json", "multipart/form-data"}:
                        raise ValueError("请求 Content-Type 无效。")
                    raw = self.read_request_body(services.MAX_UPLOAD)
                    if request_type == "application/json":
                        request_data = services.json.loads(raw)
                        if not isinstance(request_data, dict):
                            raise ValueError("JSON 请求必须是对象。")
                        source = services.resolve_selected_audio(self.server, str(request_data.get("local_audio_id", "")))
                        if source is None or not services.is_loopback_address(self.client_address[0]):
                            raise ValueError("所选音乐文件已失效，请重新选择。")
                        result = services.read_music_metadata(str(source), source.name)
                        self.send_json(200, result)
                    else:
                        fields = services.multipart_fields(self.headers.get("Content-Type", ""), raw)
                        file_part = fields.get("file")
                        if not file_part or not file_part.get_filename():
                            raise ValueError("请选择有效的音乐文件。")

                        filename = services.Path(file_part.get_filename()).name
                        file_data = file_part.get_payload(decode=True) or b""

                        with services.tempfile.NamedTemporaryFile(suffix=services.Path(filename).suffix, delete=False) as tmp:
                            tmp.write(file_data)
                            tmp_path = services.Path(tmp.name)

                        try:
                            result = services.read_music_metadata(str(tmp_path), filename)
                            self.send_json(200, result)
                        finally:
                            tmp_path.unlink(missing_ok=True)

                except Exception as exc:
                    self.send_json(400, {"error": str(exc) or "解析本地音频标签失败。"})
                return

            if self.path == "/api/package_custom_tag":
                try:
                    raw = self.read_request_body(services.MAX_UPLOAD, "multipart/form-data")
                    fields = services.multipart_fields(self.headers.get("Content-Type", ""), raw)

                    audio_part = fields.get("audio_file")
                    cover_part = fields.get("cover_file")
                    has_audio_file = bool(audio_part and audio_part.get_filename())
                    local_audio_id = services.multipart_text(fields, "local_audio_id")
                    local_audio_path = services.resolve_selected_audio(self.server, local_audio_id) if local_audio_id else None
                    if local_audio_path is not None and not services.is_loopback_address(self.client_address[0]):
                        local_audio_path = None
                    if local_audio_id and local_audio_path is None:
                        raise ValueError("所选音乐文件已失效，请重新选择。")

                    title = services.multipart_text(fields, "title")
                    artist = services.multipart_text(fields, "artist")
                    album = services.multipart_text(fields, "album")
                    albumartist = services.multipart_text(fields, "albumartist")
                    year = services.multipart_text(fields, "year")
                    lyrics = services.multipart_text(fields, "lyrics")
                    lyrics_format = services.multipart_text(fields, "lyrics_format") or "auto"
                    track_num = services.multipart_text(fields, "track_num")
                    disc_num = services.multipart_text(fields, "disc_num")
                    genre = services.multipart_text(fields, "genre")
                    composer = services.multipart_text(fields, "composer")
                    export_format = services.multipart_text(fields, "format").lower() or "mp3"
                    preferred_engine = services.multipart_text(fields, "preferred_engine") or "ytdlp"
                    filename_append = services.multipart_text(fields, "filename_append") if services.multipart_text(fields, "filename_append_enabled") == "1" else ""
                    try:
                        trim_start = float(services.multipart_text(fields, "trim_start") or 0)
                        trim_end = float(services.multipart_text(fields, "trim_end") or 0)
                    except ValueError as exc:
                        raise ValueError("音频裁剪时间无效。") from exc

                    if export_format not in services.FORMATS:
                        export_format = "mp3"
                    if not has_audio_file and local_audio_path is None and not title:
                        raise ValueError("请提供本地音频，或先搜索并填写歌曲标题。")

                    audio_bytes = (audio_part.get_payload(decode=True) or b"") if has_audio_file else None
                    orig_filename = services.Path(audio_part.get_filename()).name if has_audio_file else (local_audio_path.name if local_audio_path else "")

                    ffmpeg = services.find_ffmpeg_exe()
                    if not ffmpeg:
                        raise ValueError("系统中未检测到 FFmpeg 转换工具。")

                    with services.tempfile.TemporaryDirectory(prefix="musicdesk-tag-") as work:
                        work_dir = services.Path(work)
                        if local_audio_path is not None:
                            in_audio = local_audio_path
                        else:
                            in_audio, orig_filename = services.acquire_custom_audio_source(
                                audio_bytes, orig_filename, title, artist, preferred_engine, work_dir
                            )

                        staged_audio = work_dir / f"staged.{export_format}"
                        proc = services.subprocess.run(
                            [ffmpeg, *services.build_audio_trim_args(in_audio, staged_audio, trim_start, trim_end)],
                            capture_output=True, timeout=300, env=services.get_env_with_utf8()
                        )
                        if proc.returncode or not staged_audio.is_file():
                            raise ValueError("音频重编码/封装失败，请确保上载的是有效音频。")

                        f = services.load_music_tag(str(staged_audio))
                        if title: f['title'] = title
                        if artist: f['artist'] = artist
                        if album: f['album'] = album
                        if albumartist: f['albumartist'] = albumartist
                        if year and year.isdigit(): f['year'] = int(year)
                        lyrics = services.normalize_lyrics(lyrics or services.fetch_lrc_lyrics(title, artist), lyrics_format)
                        if lyrics and trim_start > 0:
                            lyrics = services.shift_lrc_timestamps(lyrics, trim_start)
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

                    out_name = services.make_tag_export_filename(artist, title, orig_filename, export_format, filename_append)

                    self.send_response(200)
                    self.send_header("Content-Type", services.FORMATS.get(export_format, "audio/mpeg"))
                    self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + services.urllib.parse.quote(out_name))
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
                    if export_format not in services.FORMATS:
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
                
                    built_url = services.build_download_query(
                        req_data.get("url", ""),
                        req_data.get("title", ""),
                        req_data.get("artist", ""),
                        bool(req_data.get("keyword_search")),
                    )
                    url = services.validate_download_source(built_url)
                    title = req_data.get("title", "未知标题").strip()
                    artist = req_data.get("artist", "未知艺人").strip()
                    thumbnail = services.validate_thumbnail_url(req_data.get("thumbnail", ""))
                    preferred_engine = req_data.get("preferred_engine", "ytdlp")
                
                    if not url:
                        raise ValueError("未获取到有效的歌曲分享链接。")
                
                    print(f"\n[MusicDesk 下载请求] {artist} - {title}")
                    services.sys.stdout.flush()
                
                    with services.tempfile.TemporaryDirectory(prefix="musicdesk-dl-") as temp_dir:
                        downloaded_file, source_url = services.fetch_media_stream(url, title, artist, preferred_engine, temp_dir)
                    
                        cover_p = services.Path(temp_dir) / "cover.jpg"
                        if thumbnail:
                            try:
                                raw_cover_bytes = services.fetch_thumbnail(thumbnail)
                                if services.urllib.parse.urlsplit(thumbnail).hostname in {"i.ytimg.com", "img.youtube.com"}:
                                    processed_cover = services.crop_yt_padding_smart(raw_cover_bytes)
                                else:
                                    processed_cover = raw_cover_bytes
                                cover_p.write_bytes(processed_cover)
                            except Exception:
                                cover_p.write_bytes(b"")
                        else:
                            cover_p.write_bytes(b"")
                    
                        out_dir = services.Path(temp_dir) / "out"
                        final_mp3 = services.process_and_export_media(
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
                            lyric_text = services.normalize_lyrics(str(req_data.get("lyrics") or "") or services.fetch_lrc_lyrics(title, artist), str(req_data.get("lyrics_format") or "auto"))
                            archive = out_dir / f"{final_mp3.stem}.zip"
                            with services.zipfile.ZipFile(archive, "w", compression=services.zipfile.ZIP_DEFLATED) as bundle:
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
                    self.send_header("Content-Type", "application/zip" if download_lrc else services.FORMATS[export_format])
                    self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + services.urllib.parse.quote(download_name))
                    self.send_header("Access-Control-Expose-Headers", "X-Source-Url, X-Lyrics-Sidecar")
                    self.send_api_cors_headers()
                    self.send_header("X-Source-Url", services.urllib.parse.quote(source_url, safe="/:?=&_"))
                    if download_lrc:
                        self.send_header("X-Lyrics-Sidecar", "included" if lyric_text else "missing")
                    self.send_header("Content-Length", str(len(converted)))
                    self.end_headers()
                    self.wfile.write(converted)
                
                except Exception as exc:
                    self.send_json(400, {"error": str(exc) or "下载失败。"})
                return

            if self.path == "/api/convert":
                ffmpeg = services.find_ffmpeg_exe()
                if not ffmpeg:
                    self.send_json(503, {"error": "未检测到 FFmpeg。"})
                    return
                try:
                    raw = self.read_request_body(services.MAX_UPLOAD, "multipart/form-data")
                    message = services.BytesParser(policy=services.default).parsebytes(
                        b"Content-Type: " + self.headers.get("Content-Type", "").encode("ascii", "replace") + b"\r\nMIME-Version: 1.0\r\n\r\n" + raw
                    )
                    fields = {part.get_param("name", header="content-disposition"): part for part in message.iter_parts()}
                    file_part = fields.get("file")
                    local_audio_id = str(fields["local_audio_id"].get_content()).strip() if fields.get("local_audio_id") else ""
                    local_audio_path = services.resolve_selected_audio(self.server, local_audio_id) if local_audio_id else None
                    if local_audio_path is not None and not services.is_loopback_address(self.client_address[0]):
                        local_audio_path = None
                    if local_audio_id and local_audio_path is None:
                        raise ValueError("所选音乐文件已失效，请重新选择。")
                    fmt = str(fields["format"].get_content()).strip().lower() if fields.get("format") else ""
                    has_file = bool(file_part and file_part.get_filename())
                    if (not has_file and local_audio_path is None) or fmt not in services.FORMATS:
                        raise ValueError("请选择音频文件和有效的导出格式。")

                    selected_name = file_part.get_filename() if has_file else local_audio_path.name
                    source_name = services.SAFE_NAME.sub("_", services.Path(selected_name).name).strip(" .") or "audio"
                    with services.tempfile.TemporaryDirectory(prefix="musicdesk-") as work:
                        source = local_audio_path or services.Path(work) / ("input" + services.Path(source_name).suffix[:12])
                        target = services.Path(work) / ("converted." + fmt)
                        if has_file:
                            source.write_bytes(file_part.get_payload(decode=True) or b"")
                        proc = services.subprocess.run(services.build_conversion_args(ffmpeg, source, target), capture_output=True, timeout=300, env=services.get_env_with_utf8())
                        if proc.returncode or not target.exists():
                            raise ValueError("转换失败。请确认上传的是可读取的音频文件。")
                        converted = target.read_bytes()
                
                    download_name = services.limit_filename_length(services.Path(source_name).stem + "." + fmt)
                    self.send_response(200)
                    self.send_header("Content-Type", services.FORMATS[fmt])
                    self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + services.urllib.parse.quote(download_name))
                    self.send_header("Content-Length", str(len(converted)))
                    self.send_api_cors_headers()
                    self.end_headers()
                    self.wfile.write(converted)
                except Exception as exc:
                    self.send_json(400, {"error": str(exc) or "转换失败。"})
                return

            self.send_json(404, {"error": "找不到该接口。"})
    return Handler

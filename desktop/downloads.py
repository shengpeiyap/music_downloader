"""Desktop download, playlist, and audio export operations."""

from __future__ import annotations
from pathlib import Path
import subprocess

class DownloadsService:
    """Desktop download and media export operations."""

    def __init__(self, services):
        self.services = services

    def list_playlist_entries(self, url: str) -> dict:
        """List a YouTube / YouTube Music playlist without downloading anything."""
        playlist_url = self.services.batch_queue.parse_playlist_url(url)['url']
        command = self.services.find_executable('yt-dlp') + self.services.get_ytdlp_js_runtime_args() + ['--flat-playlist', '--dump-json', '--no-warnings', '--playlist-end', str(self.services.batch_queue.MAX_BATCH_TRACKS), playlist_url]
        process = self.services.subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace', env=self.services.get_env_with_utf8(), shell=False, timeout=120)
        entries, title = ([], '')
        for line in process.stdout.splitlines():
            try:
                raw = self.services.json.loads(line)
            except self.services.json.JSONDecodeError:
                continue
            title = title or str(raw.get('playlist_title') or '')
            entry = self.services.batch_queue.clean_playlist_entry(raw)
            if entry:
                entries.append(entry)
        if not entries:
            details = (process.stderr or '').strip().splitlines()
            raise ValueError(' '.join(details[-2:])[-300:] or '没有读取到可下载的曲目（播放列表可能是私有的或为空）。')
        return {'title': title, 'entries': entries}

    def process_batch_track(self, track: dict, options: dict, dest_dir: Path) -> Path:
        """Download one playlist entry, tag it, and move the finished file into dest_dir."""
        video_url = self.services.parse_share_url(f"https://www.youtube.com/watch?v={track['id']}")['url']
        title, artist = (track['title'], track['artist'])
        export_format, bitrate = (options['format'], options['bitrate'])
        with self.services.tempfile.TemporaryDirectory(prefix='musicdesk-batch-dl-') as temp_dir:
            downloaded_file, _source = self.services.fetch_media_stream(video_url, title, artist, 'ytdlp', temp_dir)
            cover_path = self.services.Path(temp_dir) / 'cover.jpg'
            try:
                cover_path.write_bytes(self.services.crop_yt_padding_smart(self.services.fetch_thumbnail(self.services.validate_thumbnail_url(track['thumbnail']))))
            except Exception:
                cover_path.write_bytes(b'')
            try:
                lyrics = self.services.fetch_lrc_lyrics(title, artist) or ''
            except Exception:
                lyrics = ''
            meta = {'title': title, 'artist': artist, 'album': '', 'albumartist': artist, 'year': ''}
            final = self.services.process_and_export_media(source_path=downloaded_file, meta_info=meta, cover_path=cover_path, export_format=export_format, output_dir=self.services.Path(temp_dir) / 'out', bitrate=bitrate, lyrics_text=lyrics)
            target = self.services.batch_queue.unique_name(dest_dir, final.name)
            self.services.shutil.move(str(final), str(target))
            if options.get('download_lrc') and lyrics:
                sidecar = target.with_suffix('.lrc')
                sidecar.write_bytes(self.services.normalize_lyrics(lyrics).encode('utf-8-sig'))
            return target

    def build_download_query(self, url: str, title: str, artist: str, keyword_search: bool) -> str:
        url = (url or '').strip()
        if url or not keyword_search:
            return url
        artist = (artist or '').strip()
        title = (title or '').strip()
        query = f'{artist} - {title}' if artist else title
        if not query:
            raise ValueError('请先搜索一首歌曲，或提供有效的分享链接。')
        return 'musicdesk-query:' + query

    def validate_download_source(self, source: str) -> str:
        """Allow only supported share URLs or MusicDesk's internal keyword query."""
        if not isinstance(source, str) or len(source) > 2048 or any((ord(char) < 32 for char in source)):
            raise ValueError('下载来源无效。')
        source = source.strip()
        if source.startswith('musicdesk-query:'):
            query = source.removeprefix('musicdesk-query:').strip()
            if not query or len(query) > 512 or query.startswith('-'):
                raise ValueError('歌曲搜索词无效。')
            return 'musicdesk-query:' + query
        if source.startswith('ytsearch1:'):
            query = source.removeprefix('ytsearch1:').strip()
            if not query or len(query) > 512 or query.startswith('-'):
                raise ValueError('歌曲搜索词无效。')
            return 'ytsearch1:' + query
        return self.services.parse_share_url(source)['url']

    def validate_thumbnail_url(self, url: str) -> str:
        """Restrict user-supplied artwork URLs to known public artwork hosts."""
        if not url:
            return ''
        if not isinstance(url, str) or len(url) > 2048 or any((ord(char) < 32 for char in url)):
            raise ValueError('封面地址无效。')
        try:
            parsed = self.services.urllib.parse.urlsplit(url.strip())
            host = (parsed.hostname or '').lower().rstrip('.')
            port = parsed.port
        except ValueError as exc:
            raise ValueError('封面地址无效。') from exc
        allowed_host = host in self.services.SAFE_THUMBNAIL_HOSTS
        if parsed.scheme != 'https' or not allowed_host or parsed.username or parsed.password or (port not in (None, 443)) or (not parsed.path.startswith('/')):
            raise ValueError('封面地址必须来自受支持的 HTTPS 图片来源。')
        return self.services.urllib.parse.urlunsplit(parsed)

    def fetch_thumbnail(self, url: str) -> bytes:
        safe_url = self.services.validate_thumbnail_url(url)
        request = self.services.urllib.request.Request(safe_url, headers={'User-Agent': 'Mozilla/5.0'})
        opener = self.services.urllib.request.build_opener(self.services.SafeThumbnailRedirectHandler())
        with opener.open(request, timeout=10) as response:
            if not response.headers.get_content_type().startswith('image/'):
                raise ValueError('封面来源没有返回图片。')
            image_data = response.read(self.services.MAX_COVER_BYTES + 1)
        if len(image_data) > self.services.MAX_COVER_BYTES:
            raise ValueError('封面图片超过大小限制。')
        return image_data

    def acquire_custom_audio_source(self, audio_bytes: bytes | None, original_filename: str, title: str, artist: str, preferred_engine: str, work_dir: Path) -> tuple[Path, str]:
        if audio_bytes is not None:
            input_path = work_dir / f'input{self.services.Path(original_filename).suffix}'
            input_path.write_bytes(audio_bytes)
            return (input_path, original_filename)
        if not title.strip():
            raise ValueError('请提供本地音频，或先搜索并填写歌曲标题。')
        search_url = self.services.build_download_query('', title, artist, True)
        downloaded, _ = self.services.fetch_media_stream(search_url, title, artist, preferred_engine, work_dir)
        return (downloaded, self.services.make_tag_export_filename(artist, title, '', 'mp3'))

    def find_executable(self, name: str) -> list[str]:
        python_exe = self.services.Path(self.services.sys.executable)
        exe_name = f'{name}.exe' if self.services.os.name == 'nt' else name
        local_path = python_exe.parent / exe_name
        module_name = {'yt-dlp': 'yt_dlp', 'spotdl': 'spotdl'}.get(name)
        if module_name and (not getattr(self.services.sys, 'frozen', False)):
            try:
                if self.services.importlib.util.find_spec(module_name):
                    return [self.services.sys.executable, '-m', module_name]
            except (ImportError, ValueError):
                pass
        if local_path.exists():
            return [str(local_path)]
        which_path = self.services.shutil.which(name)
        if which_path:
            return [which_path]
        if name == 'yt-dlp':
            return [self.services.sys.executable, '-m', 'yt_dlp']
        return [name]

    def get_ytdlp_js_runtime_args(self) -> list[str]:
        """Enable a supported JS runtime explicitly for YouTube challenge solving."""
        runtime_names = (('deno', 'deno'), ('node', 'node'), ('quickjs', 'qjs'))
        app_dir = self.services.Path(self.services.sys.executable).resolve().parent
        for runtime, executable in runtime_names:
            runtime_path = next((str(candidate) for candidate in (app_dir / f'{executable}.exe', app_dir / executable) if candidate.is_file()), None) or self.services.shutil.which(executable)
            if runtime_path:
                return ['--js-runtimes', f'{runtime}:{runtime_path}']
        return []

    def log_downloader_failure(self, engine: str, proc: subprocess.CompletedProcess[str]) -> None:
        """Expose a short actionable error in the server console without dumping huge logs."""
        details = (proc.stderr or proc.stdout or '').strip()
        if details:
            lines = [line.strip() for line in details.splitlines() if line.strip()]
            print(f'[{engine} 失败详情] ' + ' | '.join(lines[-4:])[-1200:])
        else:
            print(f'[{engine} 失败详情] 进程退出码：{proc.returncode}，没有提供错误输出。')
        self.services.sys.stdout.flush()

    def fetch_with_ytdlp(self, url: str, title: str, artist: str, base_dir: Path) -> tuple[Path | None, str]:
        target_url = url.strip()
        if 'spotify.com' in target_url:
            clean_title = self.services.re.sub('\\s*-\\s*Topic$', '', title, flags=self.services.re.IGNORECASE).strip()
            clean_artist = '' if artist in {'未知艺人', 'Unknown Artist'} or artist.strip() == clean_title else artist.strip()
            if clean_artist:
                search_query = f'{clean_artist} {clean_title}'.strip()
            else:
                search_query = f'{clean_title}'.strip()
            if not search_query or search_query == 'Official Audio':
                search_query = 'music'
            target_url = f'ytsearch1:{search_query}'
            print(f'[yt-dlp 引擎] 检索关键词: {search_query}')
        cmd = self.services.find_executable('yt-dlp') + self.services.get_ytdlp_js_runtime_args() + ['-x', '--audio-format', 'mp3', '--no-playlist', '--print', 'after_move:filepath', '--print', 'webpage_url', '-o', str(base_dir / 'ytdlp_%(id)s.%(ext)s'), '--', target_url]
        print(f'[MusicDesk 调度] 尝试 [yt-dlp] 抓取音频...')
        self.services.sys.stdout.flush()
        proc = self.services.subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', env=self.services.get_env_with_utf8(), shell=False, timeout=300)
        source_url = ''
        if proc.returncode == 0 and proc.stdout.strip():
            lines = [line.strip() for line in proc.stdout.strip().splitlines() if line.strip()]
            for line in lines:
                if line.startswith('http://') or line.startswith('https://'):
                    source_url = line
        mp3_files = list(base_dir.glob('ytdlp_*.mp3'))
        if mp3_files:
            latest = max(mp3_files, key=lambda p: p.stat().st_mtime)
            if not source_url:
                video_id = latest.stem.replace('ytdlp_', '')
                source_url = f'https://www.youtube.com/watch?v={video_id}'
            print(f'[MusicDesk 成功] yt-dlp 成功提取: {latest.name}')
            print(f'[MusicDesk 音频来源] {source_url}')
            self.services.sys.stdout.flush()
            return (latest, source_url)
        self.services.log_downloader_failure('yt-dlp', proc)
        failure_text = f"{proc.stderr or ''}\n{proc.stdout or ''}".lower()
        if any((marker in failure_text for marker in ('javascript runtime', 'js runtime', 'javascript challenge'))):
            raise RuntimeError('YouTube 下载需要 Deno 或 Node.js 来处理 JavaScript 验证。请更新便携版，或在电脑安装 Deno/Node.js 后重启 MusicDesk。')
        print(f'[yt-dlp 抓取失败]')
        self.services.sys.stdout.flush()
        return (None, '')

    def fetch_with_spotdl(self, url: str, base_dir: Path) -> tuple[Path | None, str]:
        print(f'[MusicDesk 调度] 尝试 [spotdl] 下载...')
        self.services.sys.stdout.flush()
        cmd = self.services.find_executable('spotdl') + ['download', url.strip()]
        proc = self.services.subprocess.run(cmd, cwd=str(base_dir), capture_output=True, text=True, encoding='utf-8', errors='replace', env=self.services.get_env_with_utf8(), shell=False, timeout=300)
        if proc.returncode == 0:
            mp3_files = list(base_dir.glob('*.mp3'))
            if mp3_files:
                latest = max(mp3_files, key=lambda p: p.stat().st_mtime)
                print(f'[MusicDesk 音频来源] {url}')
                self.services.sys.stdout.flush()
                return (latest, url)
        self.services.log_downloader_failure('spotdl', proc)
        print(f'[spotdl 下载未成功]')
        self.services.sys.stdout.flush()
        return (None, '')

    def fetch_media_stream(self, url: str, title: str='', artist: str='', preferred_engine: str='ytdlp', temp_dir: str | Path | None=None) -> tuple[Path, str]:
        base_dir = self.services.Path(temp_dir) if temp_dir else self.services.Path(self.services.tempfile.gettempdir())
        if url.startswith('musicdesk-query:'):
            query = url.removeprefix('musicdesk-query:').strip()
            if not query:
                raise ValueError('搜索词不能为空。')
            search_engines = {'ytdlp': lambda: self.services.fetch_with_ytdlp('ytsearch1:' + query, title, artist, base_dir), 'spotdl': lambda: self.services.fetch_with_spotdl(query, base_dir)}
            first_engine = preferred_engine if preferred_engine in search_engines else 'ytdlp'
            for engine in (first_engine, 'spotdl' if first_engine == 'ytdlp' else 'ytdlp'):
                res_file, source_url = search_engines[engine]()
                if res_file and res_file.is_file():
                    return (res_file, '' if source_url == query else source_url)
            raise ValueError('没有找到可下载的匹配音频，请尝试调整关键词。')
        engines = {'ytdlp': lambda: self.services.fetch_with_ytdlp(url, title, artist, base_dir)}
        if 'spotify.com' in url.lower():
            engines['spotdl'] = lambda: self.services.fetch_with_spotdl(url, base_dir)
        valid_engine = preferred_engine if preferred_engine in engines else 'ytdlp'
        priority_order = [valid_engine] + [name for name in engines if name != valid_engine]
        for eng_name in priority_order:
            res_file, source_url = engines[eng_name]()
            if res_file and res_file.is_file():
                return (res_file, source_url)
        raise ValueError('所有配置的下载引擎均无法匹配或提取该歌曲。')

    def process_and_export_media(self, source_path: str | Path, meta_info: dict, cover_path: str | Path, export_format: str, output_dir: str | Path, *, cleanup_source: bool=True, bitrate: str='192', lyrics_text: str='', track_num: str='', genre: str='', composer: str='', disc_num: str='') -> Path:
        source = self.services.Path(source_path)
        cover = self.services.Path(cover_path)
        fmt = str(export_format).strip().lower().lstrip('.')
        if not source.is_file():
            raise ValueError('Cached media file does not exist')
        ffmpeg = self.services.find_ffmpeg_exe()
        if not ffmpeg:
            raise ValueError('FFmpeg is not installed or available on PATH')
        title = meta_info.get('title', '未知标题').strip()
        artist = meta_info.get('artist', '未知艺人').strip()
        albumartist = meta_info.get('albumartist', '').strip() or artist
        album = meta_info.get('album', '').strip()
        year = meta_info.get('year', '').strip()
        track_num = meta_info.get('track_num', '').strip()
        destination_dir = self.services.Path(output_dir)
        destination_dir.mkdir(parents=True, exist_ok=True)
        base = self.services.SAFE_NAME.sub('_', f'{artist} - {title}').strip(' .') or 'audio'
        if fmt not in self.services.FORMATS:
            raise ValueError('不支持的音频格式。')
        bitrate_value = str(bitrate).strip()
        if bitrate_value not in {'128', '192', '256', '320'}:
            bitrate_value = '192'
        destination = destination_dir / self.services.limit_filename_length(f'{base}.{fmt}')
        with self.services.tempfile.TemporaryDirectory(prefix='musicdesk-export-', dir=destination_dir) as work:
            staged = self.services.Path(work) / f'export.{fmt}'
            codec_args = {'mp3': ['-c:a', 'libmp3lame', '-b:a', f'{bitrate_value}k'], 'm4a': ['-c:a', 'aac', '-b:a', f'{bitrate_value}k'], 'ogg': ['-c:a', 'libvorbis', '-b:a', f'{bitrate_value}k'], 'flac': ['-c:a', 'flac'], 'wav': ['-c:a', 'pcm_s16le']}[fmt]
            proc = self.services.subprocess.run([ffmpeg, '-nostdin', '-v', 'error', '-y', '-i', str(source), '-map', '0:a:0', '-vn', *codec_args, str(staged)], capture_output=True, timeout=300, env=self.services.get_env_with_utf8())
            if proc.returncode or not staged.is_file():
                detail = proc.stderr.decode('utf-8', errors='replace').strip() if proc.stderr else ''
                raise ValueError('FFmpeg 处理音频失败' + (f'：{detail[-500:]}' if detail else ''))
            lyrics_text = self.services.normalize_lyrics(lyrics_text or self.services.fetch_lrc_lyrics(title, artist), str(meta_info.get('lyrics_format') or 'auto'))
            try:
                from mutagen.id3 import APIC, TALB, TCOM, TCON, TDRC, TIT2, TPE1, TPE2, TRCK, TPOS, USLT
                if fmt == 'mp3':
                    from mutagen.id3 import ID3
                    tags = ID3()
                    tags.add(TIT2(encoding=3, text=title))
                    tags.add(TPE1(encoding=3, text=artist))
                    tags.add(TPE2(encoding=3, text=albumartist))
                    if album:
                        tags.add(TALB(encoding=3, text=album))
                    if year:
                        tags.add(TDRC(encoding=3, text=year))
                    if track_num:
                        tags.add(TRCK(encoding=3, text=track_num))
                    if disc_num:
                        tags.add(TPOS(encoding=3, text=disc_num))
                    if genre:
                        tags.add(TCON(encoding=3, text=genre))
                    if composer:
                        tags.add(TCOM(encoding=3, text=composer))
                    if lyrics_text:
                        tags.add(USLT(encoding=3, lang='eng', desc='', text=lyrics_text))
                    if cover.is_file() and cover.stat().st_size > 0:
                        mime = 'image/png' if cover.suffix.lower() == '.png' else 'image/jpeg'
                        tags.add(APIC(encoding=3, mime=mime, type=3, desc='Cover', data=cover.read_bytes()))
                    tags.save(staged, v2_version=3)
                elif fmt == 'wav':
                    from mutagen.wave import WAVE
                    from mutagen.id3 import ID3
                    audio = WAVE(staged)
                    if audio.tags is None:
                        audio.add_tags()
                    tags = audio.tags
                    tags.add(TIT2(encoding=3, text=title))
                    tags.add(TPE1(encoding=3, text=artist))
                    tags.add(TPE2(encoding=3, text=albumartist))
                    if album:
                        tags.add(TALB(encoding=3, text=album))
                    if year:
                        tags.add(TDRC(encoding=3, text=year))
                    if track_num:
                        tags.add(TRCK(encoding=3, text=track_num))
                    if disc_num:
                        tags.add(TPOS(encoding=3, text=disc_num))
                    if genre:
                        tags.add(TCON(encoding=3, text=genre))
                    if composer:
                        tags.add(TCOM(encoding=3, text=composer))
                    if lyrics_text:
                        tags.add(USLT(encoding=3, lang='eng', desc='', text=lyrics_text))
                    if cover.is_file() and cover.stat().st_size > 0:
                        mime = 'image/png' if cover.suffix.lower() == '.png' else 'image/jpeg'
                        tags.add(APIC(encoding=3, mime=mime, type=3, desc='Cover', data=cover.read_bytes()))
                    audio.save()
                else:
                    from mutagen import File as MutagenFile
                    from mutagen.mp4 import MP4, MP4Cover
                    from mutagen.flac import FLAC, Picture
                    audio = MutagenFile(staged, easy=False)
                    if audio is None:
                        raise ValueError('无法识别导出的音频容器。')
                    if isinstance(audio, MP4):
                        tags = audio.tags
                        if tags is None:
                            audio.add_tags()
                            tags = audio.tags
                        for key, value in (('©nam', title), ('©ART', artist), ('aART', albumartist), ('©alb', album), ('©day', year), ('©gen', genre), ('©wrt', composer), ('©lyr', lyrics_text)):
                            if value:
                                tags[key] = [str(value)]
                        if track_num:
                            tags['trkn'] = [(int(track_num.split('/')[0]), int(track_num.split('/')[1]) if '/' in track_num else 0)]
                        if disc_num:
                            tags['disk'] = [(int(disc_num.split('/')[0]), int(disc_num.split('/')[1]) if '/' in disc_num else 0)]
                        if cover.is_file() and cover.stat().st_size > 0:
                            image_format = MP4Cover.FORMAT_PNG if cover.suffix.lower() == '.png' else MP4Cover.FORMAT_JPEG
                            tags['covr'] = [MP4Cover(cover.read_bytes(), imageformat=image_format)]
                        audio.save()
                    elif isinstance(audio, FLAC) or fmt == 'ogg':
                        if audio.tags is None:
                            audio.add_tags()
                        tags = audio.tags
                        pairs = (('title', title), ('artist', artist), ('album', album), ('albumartist', albumartist), ('date', year), ('tracknumber', track_num), ('discnumber', disc_num), ('genre', genre), ('composer', composer), ('lyrics', lyrics_text))
                        for key, value in pairs:
                            if value:
                                tags[key] = [str(value)]
                        if cover.is_file() and cover.stat().st_size > 0:
                            picture = Picture()
                            picture.data = cover.read_bytes()
                            picture.type = 3
                            picture.mime = 'image/png' if cover.suffix.lower() == '.png' else 'image/jpeg'
                            picture.desc = 'Cover'
                            if hasattr(audio, 'clear_pictures'):
                                audio.clear_pictures()
                                audio.add_picture(picture)
                            else:
                                import base64
                                tags['metadata_block_picture'] = [self.services.base64.b64encode(picture.write()).decode('ascii')]
                        audio.save()
                    else:
                        raise ValueError('此音频容器暂不支持写入元数据。')
            except Exception as exc:
                raise ValueError(f'写入音频标签失败：{exc}') from exc
            self.services.os.replace(staged, destination)
        if cleanup_source:
            source.unlink(missing_ok=True)
        return destination

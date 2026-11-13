"""Desktop metadata lookup adapters for MusicBrainz, Spotify, and yt-dlp."""
from __future__ import annotations


class MetadataService:
    """Run metadata lookups against the compatibility app's shared dependencies."""

    def __init__(self, services):
        self.services = services

    def search_ytdlp_metadata(self, query: str) -> dict:
        """Use yt-dlp's search result as a metadata fallback when public catalogs miss."""
        s = self.services
        search_url = "ytsearch1:" + " ".join(query.split())
        command = s.find_executable("yt-dlp") + s.get_ytdlp_js_runtime_args() + [
            "--dump-json", "--no-warnings", "--no-playlist", search_url,
        ]
        process = s.subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=s.get_env_with_utf8(), shell=False, timeout=45,
        )
        if process.returncode != 0 or not process.stdout.strip():
            details = (process.stderr or process.stdout or "").strip().splitlines()
            detail = " ".join(details[-2:])[-400:]
            raise ValueError(detail or "yt-dlp 没有找到匹配的视频。")

        try:
            info = s.json.loads(process.stdout.splitlines()[0])
        except (s.json.JSONDecodeError, IndexError) as exc:
            raise ValueError("yt-dlp 返回了无法读取的搜索结果。") from exc

        title = str(info.get("track") or info.get("title") or "").strip()
        artist = str(info.get("artist") or info.get("creator") or info.get("uploader") or info.get("channel") or "").strip()
        url = str(info.get("webpage_url") or "").strip()
        if not url:
            video_id = str(info.get("id") or "").strip()
            extractor = str(info.get("extractor_key") or info.get("ie_key") or "").lower()
            if video_id and ("youtube" in extractor or not extractor):
                url = f"https://www.youtube.com/watch?v={s.urllib.parse.quote(video_id)}"
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
                             or s.urllib.parse.urlparse(url).hostname in {"youtube.com", "www.youtube.com", "youtu.be"}):
                thumbnail = f"https://i.ytimg.com/vi/{s.urllib.parse.quote(video_id)}/hqdefault.jpg"
        thumbnail = thumbnail or None
        return {
            "title": title, "artist": artist or "未知艺人", "album": str(info.get("album") or ""),
            "albumartist": artist or "未知艺人", "year": year, "lyrics": "", "cover": thumbnail,
            "thumbnail": thumbnail, "url": url,
            "preview_url": url if s.urllib.parse.urlparse(url).hostname in {
                "youtube.com", "www.youtube.com", "youtu.be", "m.youtube.com"
            } else "",
            "provider": "yt-dlp",
        }

    def fetch_youtube_rich_metadata(self, url: str) -> dict:
        s = self.services
        meta = {"title": "", "artist": "", "album": "", "year": "", "thumbnail": None}
        try:
            cmd = s.find_executable("yt-dlp") + ["--dump-json", "--no-playlist", url]
            proc = s.subprocess.run(
                cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                env=s.get_env_with_utf8(), shell=False, timeout=45,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                info = s.json.loads(proc.stdout)
                meta["title"] = info.get("track") or info.get("title") or ""
                meta["artist"] = info.get("artist") or info.get("uploader") or info.get("channel") or ""
                meta["album"] = info.get("album") or ""
                release_date = str(info.get("release_date") or info.get("upload_date") or "")
                if len(release_date) >= 4:
                    meta["year"] = release_date[:4]
                elif info.get("release_year"):
                    meta["year"] = str(info.get("release_year"))
                meta["thumbnail"] = info.get("thumbnail")
        except Exception as exc:
            print(f"[MusicDesk YouTube 元数据抓取提示]: {exc}")
        return meta

    def lookup_metadata_by_keyword(self, query: str, album_hint: str = "") -> dict:
        s = self.services
        artist, title = s.parse_metadata_search_query(query)
        if not title:
            raise ValueError("请输入“作者 - 标题”或歌曲标题。")

        metadata = (s.lookup_musicbrainz_metadata(title, artist, album_hint) if album_hint
                    else s.lookup_musicbrainz_metadata(title, artist))
        lyric_track = s.search_lrc_track(title, artist)
        found_artist = metadata.get("artist") or artist
        if found_artist in {"未知艺人", "Unknown Artist", title} and lyric_track:
            found_artist = lyric_track.get("artistName") or found_artist
        if not any(metadata.get(field) for field in ("album", "year", "cover_url")) and not lyric_track:
            fallback = s.search_ytdlp_metadata(query)
            fallback["lyrics"] = s.fetch_lrc_lyrics(fallback["title"], fallback["artist"])
            return fallback
        if artist == "未知艺人" and found_artist in {"未知艺人", title}:
            fallback = s.search_ytdlp_metadata(query)
            fallback["lyrics"] = s.fetch_lrc_lyrics(fallback["title"], fallback["artist"])
            return fallback

        cover = None
        cover_url = metadata.get("cover_url")
        if cover_url:
            parsed = s.urllib.parse.urlparse(cover_url)
            if parsed.scheme == "https" and parsed.hostname == "coverartarchive.org":
                try:
                    request = s.urllib.request.Request(cover_url, headers={"User-Agent": "MusicDesk/1.0"})
                    with s.urllib.request.urlopen(request, timeout=6) as response:
                        image_data = response.read(8 * 1024 * 1024 + 1)
                        content_type = response.headers.get_content_type()
                    if len(image_data) <= 8 * 1024 * 1024 and content_type.startswith("image/"):
                        cover = f"data:{content_type};base64," + s.base64.b64encode(image_data).decode("ascii")
                except Exception:
                    pass

        return {
            "title": title, "artist": found_artist,
            "album": metadata.get("album") or (lyric_track or {}).get("albumName", ""),
            "albumartist": found_artist, "year": metadata.get("year", ""),
            "lyrics": ((lyric_track or {}).get("syncedLyrics") or (lyric_track or {}).get("plainLyrics")
                       or s.fetch_lrc_lyrics(title, found_artist)),
            "cover": cover, "provider": "MusicBrainz",
        }

    def search_metadata_candidates(self, query: str, limit: int = 8) -> list[dict]:
        s = self.services
        artist, title = s.parse_metadata_search_query(query)
        if not title:
            raise ValueError("请输入“作者 - 标题”或歌曲标题。")
        clean_artist = "" if artist in {"未知艺人", "Unknown Artist"} or artist.strip() == title.strip() else artist.strip()
        result = s.musicbrainzngs.search_recordings(query=s.build_musicbrainz_search_query(title, clean_artist), limit=25)
        candidates, seen = [], set()
        for recording in result.get("recording-list", []):
            credit = recording.get("artist-credit", [])
            names = [part.get("artist", {}).get("name", "") if isinstance(part, dict) else "" for part in credit]
            artist_name = ", ".join(name for name in names if name)
            releases = [rel for rel in recording.get("release-list", []) if isinstance(rel, dict)]
            releases.sort(key=lambda rel: (
                (rel.get("release-group") or {}).get("type", "").lower() == "album", bool(rel.get("date")),
            ), reverse=True)
            release = releases[0] if releases else {}
            item = {
                "id": recording.get("id", ""), "title": recording.get("title", ""), "artist": artist_name,
                "album": release.get("title", ""), "year": str(release.get("date", ""))[:4],
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

    def fetch_spotify_oembed(self, raw_url: str) -> dict:
        s = self.services
        meta = {"title": "", "artist": "", "thumbnail": None}
        try:
            endpoint = "https://open.spotify.com/oembed?url=" + s.urllib.parse.quote(raw_url, safe="")
            req = s.urllib.request.Request(endpoint, headers={"User-Agent": "Mozilla/5.0"})
            with s.urllib.request.urlopen(req, timeout=6) as response:
                data = s.json.loads(response.read().decode("utf-8"))
                raw_title = s.html_module.unescape(str(data.get("title", ""))).strip()
                meta["thumbnail"] = data.get("thumbnail_url")
                meta["artist"] = s.html_module.unescape(str(data.get("author_name", ""))).strip()
                if " - " in raw_title and not meta["artist"]:
                    parts = raw_title.split(" - ", 1)
                    meta["artist"], meta["title"] = parts[0].strip(), parts[1].strip()
                else:
                    meta["title"] = raw_title
        except Exception as exc:
            print(f"[MusicDesk] Spotify oEmbed 解析提示: {exc}")
        return meta

    def fetch_spotify_embed_html(self, track_id: str) -> dict:
        s = self.services
        meta = {"title": "", "artist": "", "thumbnail": None}
        try:
            url = f"https://open.spotify.com/embed/track/{track_id}"
            req = s.urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": "ja,en-US;q=0.9,en;q=0.8"
            })
            with s.urllib.request.urlopen(req, timeout=6) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
                title_m = s.re.search(r'<meta property="og:title" content="([^"]+)"', html)
                artist_m = s.re.search(r'<meta property="twitter:audio:artist_name" content="([^"]+)"', html) or \
                           s.re.search(r'<meta name="music:musician" content="([^"]+)"', html)
                img_m = s.re.search(r'<meta property="og:image" content="([^"]+)"', html)
                if title_m: meta["title"] = s.html_module.unescape(title_m.group(1)).strip()
                if artist_m: meta["artist"] = s.html_module.unescape(artist_m.group(1)).strip()
                if img_m: meta["thumbnail"] = img_m.group(1).strip()
        except Exception:
            pass
        return meta

    def lookup_musicbrainz_metadata(self, title: str, artist: str, known_album: str = "") -> dict:
        s = self.services
        print(f"[MusicDesk - MusicBrainz 检索] 正在查找: {title} - {artist} (已知专辑: {known_album})")
        res_meta = {"artist": artist, "album": known_album, "year": "", "track_num": "", "cover_url": None}
        if not title or title == "未知标题":
            return res_meta
        try:
            clean_artist = "" if artist in {"未知艺人", "Unknown Artist"} or artist.strip() == title.strip() else artist.strip()
            query = s.build_musicbrainz_search_query(title, clean_artist, known_album)
            result = s.musicbrainzngs.search_recordings(query=query, limit=15)
            recordings = result.get("recording-list", [])
            if not recordings and known_album:
                query_fallback = s.build_musicbrainz_search_query(title, clean_artist)
                result = s.musicbrainzngs.search_recordings(query=query_fallback, limit=15)
                recordings = result.get("recording-list", [])

            album_releases, single_releases = [], []
            for rec in recordings:
                artist_credit = rec.get("artist-credit", [])
                if artist_credit and isinstance(artist_credit[0], dict):
                    mb_artist = artist_credit[0].get("artist", {}).get("name", "")
                    if mb_artist and (not clean_artist or res_meta["artist"] in {"未知艺人", title}):
                        res_meta["artist"] = mb_artist
                for rel in rec.get("release-list", []):
                    rel_group = rel.get("release-group", {})
                    primary_type = rel_group.get("type", "").lower()
                    secondary_types = [t.lower() for t in rel_group.get("secondary-type-list", [])]
                    if "live" in secondary_types or "remix" in secondary_types:
                        continue
                    date_str = rel.get("date", "")
                    year = date_str.split("-")[0] if date_str else "9999"
                    item = {"id": rel.get("id"), "title": rel.get("title", ""),
                            "year": year if year != "9999" else "", "is_album": primary_type == "album"}
                    (album_releases if primary_type == "album" else single_releases).append(item)

            candidate_releases = sorted(album_releases, key=lambda r: r["year"] or "9999") + \
                                 sorted(single_releases, key=lambda r: r["year"] or "9999")
            for rel in candidate_releases:
                rel_id, album_name, year = rel["id"], rel["title"], rel["year"]
                cover_url = None
                try:
                    test_url = f"https://coverartarchive.org/release/{rel_id}/front-500"
                    req = s.urllib.request.Request(test_url, method='HEAD', headers={"User-Agent": "MusicDesk/1.0"})
                    with s.urllib.request.urlopen(req, timeout=3):
                        cover_url = test_url
                except Exception:
                    cover_url = None
                if not res_meta["album"]:
                    res_meta["album"] = album_name
                if not res_meta["year"]:
                    res_meta["year"] = year
                if cover_url:
                    res_meta["cover_url"] = cover_url
                    res_meta["album"], res_meta["year"] = album_name, year
                    print(f"[MusicDesk 成功] 命中优先原画专辑封面 [{album_name} ({year})]: {cover_url}")
                    return res_meta
        except Exception as exc:
            print(f"[MusicDesk - MusicBrainz 提示]: {exc}")
        return res_meta

    def lookup_metadata(self, raw_url: str) -> dict:
        s = self.services
        link = s.parse_share_url(raw_url)
        title, artist, album, year, track_num, thumbnail = "未知标题", "未知艺人", "", "", "", None
        if link["provider"] == "spotify":
            oembed_data = s.fetch_spotify_oembed(link["url"])
            if oembed_data.get("title"): title = oembed_data["title"]
            if oembed_data.get("artist"): artist = oembed_data["artist"]
            if oembed_data.get("thumbnail"): thumbnail = oembed_data["thumbnail"]
            if title == "未知标题" or artist == "未知艺人":
                embed_data = s.fetch_spotify_embed_html(link["id"])
                if title == "未知标题" and embed_data.get("title"): title = embed_data["title"]
                if artist == "未知艺人" and embed_data.get("artist"): artist = embed_data["artist"]
                if not thumbnail and embed_data.get("thumbnail"): thumbnail = embed_data["thumbnail"]
        elif link["provider"] == "youtube":
            yt_rich = s.fetch_youtube_rich_metadata(link["url"])
            if yt_rich.get("title"): title = yt_rich["title"]
            if yt_rich.get("artist"): artist = yt_rich["artist"]
            if yt_rich.get("album"): album = yt_rich["album"]
            if yt_rich.get("year"): year = yt_rich["year"]
            if yt_rich.get("thumbnail"): thumbnail = yt_rich["thumbnail"]
            if title == "未知标题":
                try:
                    endpoint = "https://www.youtube.com/oembed?format=json&url=" + s.urllib.parse.quote(link["url"], safe="")
                    req = s.urllib.request.Request(endpoint, headers={"User-Agent": "MusicDesk/1.0"})
                    with s.urllib.request.urlopen(req, timeout=6) as response:
                        data = s.json.loads(response.read())
                        title, artist = data.get("title", title), data.get("author_name", artist)
                        if not thumbnail: thumbnail = data.get("thumbnail_url")
                except Exception:
                    pass
        artist = s.re.sub(r"\s*-\s*Topic$", "", artist, flags=s.re.IGNORECASE).strip()
        if title and title != "未知标题":
            mb_meta = s.lookup_musicbrainz_metadata(title, artist, known_album=album)
            if mb_meta.get("artist") and (artist == "未知艺人" or artist == title): artist = mb_meta["artist"]
            if mb_meta.get("album"): album = mb_meta["album"]
            if mb_meta.get("year"): year = mb_meta["year"]
            if mb_meta.get("cover_url"): thumbnail = mb_meta["cover_url"]
        if title == "未知标题":
            raise ValueError("未能读取到该音频链接信息，请检查链接或网络连接后重试。")
        return {
            "provider": link["provider"], "id": link["id"], "url": link["url"],
            "title": title, "artist": artist, "album": album, "year": year, "track_num": track_num,
            "thumbnail": thumbnail,
        }

"""LRCLIB lookup and plain/synchronized lyric fallback for desktop workflows."""
from __future__ import annotations


class LyricsService:
    """Perform public lyrics lookups through the app's shared HTTP dependencies."""

    def __init__(self, services):
        self.services = services

    def fetch_lrc_lyrics(self, title: str, artist: str) -> str:
        s = self.services
        if not title or title == "未知标题":
            return ""
        try:
            clean_artist = "" if artist in {"未知艺人", "Unknown Artist"} else artist.strip()
            query = f"track_name={s.urllib.parse.quote(title)}"
            if clean_artist:
                query += f"&artist_name={s.urllib.parse.quote(clean_artist)}"
            url = f"https://lrclib.net/api/get?{query}"
            req = s.urllib.request.Request(url, headers={"User-Agent": "MusicDesk/1.0"})
            with s.urllib.request.urlopen(req, timeout=5) as resp:
                data = s.json.loads(resp.read().decode("utf-8"))
                synced = data.get("syncedLyrics", "")
                if synced:
                    print("[MusicDesk 歌词成功] 成功检索到 LRC 同步歌词")
                    return synced
                plain = data.get("plainLyrics", "")
                if plain:
                    return plain
        except Exception:
            pass

        result = s.search_lrc_track(title, artist)
        if result:
            lyrics = result.get("syncedLyrics") or result.get("plainLyrics") or ""
            if lyrics:
                print("[MusicDesk 歌词成功] 通过曲名检索找到歌词")
            return lyrics
        return ""

    def search_lrc_track(self, title: str, artist: str) -> dict | None:
        s = self.services
        if not title:
            return None
        clean_artist = "" if artist in {"未知艺人", "Unknown Artist"} or artist.strip() == title.strip() else artist.strip()
        query = " ".join(part for part in (clean_artist, title.strip()) if part)
        search_url = "https://lrclib.net/api/search?" + s.urllib.parse.urlencode({"q": query})
        request = s.urllib.request.Request(search_url, headers={"User-Agent": "MusicDesk/1.0"})
        try:
            with s.urllib.request.urlopen(request, timeout=6) as response:
                results = s.json.loads(response.read().decode("utf-8"))
        except Exception:
            return None

        if not isinstance(results, list):
            return None
        normalize = lambda value: s.re.sub(r"[^\w]", "", str(value or "").casefold())
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
        return max(candidates, key=lambda item: (
            bool(item.get("syncedLyrics")), bool(item.get("plainLyrics")), bool(item.get("albumName"))
        ))

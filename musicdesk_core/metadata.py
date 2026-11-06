"""Shared source URL and metadata-query parsing utilities."""

from __future__ import annotations

import re
import urllib.parse


def split_artist_title(query: str, default_artist: str = "") -> tuple[str, str]:
    """Split an artist/title query while supporting the common dash variants."""
    query = " ".join((query or "").split())
    match = re.match(r"^(.+?)\s+[-–—]\s+(.+)$", query)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return default_artist, query


def parse_metadata_search_query(query: str) -> tuple[str, str]:
    """Desktop form: title-only searches use the localized unknown-artist label."""
    return split_artist_title(query, default_artist="未知艺人")


def parse_share_url(raw: str) -> dict:
    """Validate and canonicalize supported Spotify and YouTube share URLs."""
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


def quote_musicbrainz_phrase(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def build_musicbrainz_search_query(title: str, artist: str = "", album: str = "") -> str:
    terms = [f"recording:{quote_musicbrainz_phrase(title)}"]
    if artist:
        terms.append(f"artist:{quote_musicbrainz_phrase(artist)}")
    if album:
        terms.append(f"release:{quote_musicbrainz_phrase(album)}")
    return " AND ".join(terms)

"""Shared, platform-independent MusicDesk processing primitives."""

from .media import (
    SAFE_NAME,
    build_audio_trim_args,
    build_conversion_args,
    limit_filename_length,
    make_tag_export_filename,
)
from .lyrics import normalize_lyrics, parse_lrc_timestamps, shift_lrc_timestamps
from .metadata import (
    build_musicbrainz_search_query,
    parse_metadata_search_query,
    parse_share_url,
    quote_musicbrainz_phrase,
    split_artist_title,
)

__all__ = [
    "SAFE_NAME",
    "build_audio_trim_args",
    "build_conversion_args",
    "limit_filename_length",
    "make_tag_export_filename",
    "shift_lrc_timestamps",
    "parse_lrc_timestamps",
    "normalize_lyrics",
    "build_musicbrainz_search_query",
    "parse_metadata_search_query",
    "parse_share_url",
    "quote_musicbrainz_phrase",
    "split_artist_title",
]

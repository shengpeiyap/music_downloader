"""Shared, platform-independent MusicDesk processing primitives."""

from .media import (
    SAFE_NAME,
    build_audio_trim_args,
    build_conversion_args,
    limit_filename_length,
    make_tag_export_filename,
    shift_lrc_timestamps,
)

__all__ = [
    "SAFE_NAME",
    "build_audio_trim_args",
    "build_conversion_args",
    "limit_filename_length",
    "make_tag_export_filename",
    "shift_lrc_timestamps",
]

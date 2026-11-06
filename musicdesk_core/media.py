"""Platform-independent audio command, lyric timing, and filename helpers."""

from __future__ import annotations

import math
import os
import re
from pathlib import Path


SAFE_NAME = re.compile(r"[^\w .()-]+", re.UNICODE)


def build_audio_trim_args(input_path: str | Path, output_path: str | Path, start: float, end: float) -> list[str]:
    """Build FFmpeg arguments for an optional validated [start, end) range."""
    if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end < 0:
        raise ValueError("音频裁剪时间无效。")
    if end and end <= start:
        raise ValueError("裁剪终点必须晚于起点。")
    args = ["-nostdin", "-v", "error", "-y"]
    if start > 0:
        args.extend(["-ss", f"{start:.3f}"])
    args.extend(["-i", str(input_path)])
    if end > 0:
        args.extend(["-t", f"{end - start:.3f}"])
    args.extend(["-map", "0:a:0", "-vn", str(output_path)])
    return args


def build_conversion_args(ffmpeg: str, input_path: str | Path, output_path: str | Path) -> list[str]:
    """Convert the first audio stream while ignoring embedded cover-art video streams."""
    return [ffmpeg, "-nostdin", "-v", "error", "-i", str(input_path), "-map", "0:a:0", "-vn", "-y", str(output_path)]


def limit_filename_length(filename: str, max_utf16_units: int = 240) -> str:
    """Keep an exported filename below Windows' per-component limit, including extension."""
    stem, suffix = os.path.splitext(filename)
    suffix_units = sum(2 if ord(char) > 0xFFFF else 1 for char in suffix)
    budget = max(1, max_utf16_units - suffix_units)
    kept = []
    used = 0
    for char in stem:
        units = 2 if ord(char) > 0xFFFF else 1
        if used + units > budget:
            break
        kept.append(char)
        used += units
    return "".join(kept).rstrip(" .") + suffix


def make_tag_export_filename(
    artist: str,
    title: str,
    original_filename: str,
    export_format: str,
    append_text: str = "",
) -> str:
    artist = artist.strip() or "未知艺人"
    title = title.strip() or Path(original_filename).stem or "未知标题"
    suffix = SAFE_NAME.sub("_", append_text).strip(" ._-()")
    base_name = f"{artist} - {title}" + (f" - {suffix}" if suffix else "")
    name = SAFE_NAME.sub("_", f"{base_name}.{export_format}").strip(" .")
    return limit_filename_length(name or f"未知艺人 - 未知标题.{export_format}")

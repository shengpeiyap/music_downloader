"""Shared LRC timestamp parsing and trimming helpers."""

from __future__ import annotations

import re


_LINE_TIMESTAMP = re.compile(r"\[(\d{1,3}):(\d{2})(?:[.:](\d{1,3}))?\]")
_WORD_TIMESTAMP = re.compile(r"<(\d{1,3}):(\d{2})(?:[.:](\d{1,3}))?>")
_ANY_TIMESTAMP = re.compile(r"(?P<open>\[|<)(?P<minutes>\d{1,3}):(?P<seconds>\d{2})(?:[.:](?P<fraction>\d{1,3}))?(?P<close>\]|>)")
_SUBTITLE_TIMESTAMP = re.compile(r"(?:(?P<h>\d{2}):)?(?P<m>\d{2}):(?P<s>\d{2})[,.](?P<ms>\d{1,3})\s*-->\s*")


def normalize_lyrics(lyrics: str, source_format: str = "auto") -> str:
    """Normalize plain text, LRC, enhanced LRC, SRT, or WebVTT into readable text/LRC."""
    text = str(lyrics or "").replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n").strip()
    fmt = (source_format or "auto").lower()
    if fmt not in {"auto", "plain", "lrc", "enhanced-lrc", "srt", "vtt"}:
        raise ValueError("不支持的歌词格式。")
    # Automatic detection only picks a subtitle format when a real cue timestamp
    # exists, so ordinary lyrics that merely contain "-->" stay plain text.
    has_cue = bool(_SUBTITLE_TIMESTAMP.search(text))
    if fmt == "auto":
        if has_cue:
            fmt = "vtt" if text.startswith("WEBVTT") else "srt"
        elif _LINE_TIMESTAMP.search(text):
            fmt = "lrc"
        else:
            fmt = "plain"
    if fmt in {"srt", "vtt"}:
        if text and not has_cue:
            raise ValueError("歌词内容不是有效的 SRT 或 WebVTT 字幕。")
        converted = []
        lines = text.splitlines()
        index = 0
        while index < len(lines):
            match = _SUBTITLE_TIMESTAMP.search(lines[index])
            if match:
                milliseconds = int(match.group("ms").ljust(3, "0")[:3])
                centiseconds = round(milliseconds / 10)
                total = (int(match.group("h") or 0) * 3600 + int(match.group("m")) * 60 + int(match.group("s"))) * 100 + centiseconds
                minutes, remainder = divmod(total, 6000)
                index += 1
                cue = []
                while index < len(lines) and lines[index].strip() and not _SUBTITLE_TIMESTAMP.search(lines[index]):
                    # A bare number directly before a timestamp is the next cue's index,
                    # but a bare number elsewhere is real lyric text (for example "1999").
                    if lines[index].strip().isdigit() and index + 1 < len(lines) and _SUBTITLE_TIMESTAMP.search(lines[index + 1]):
                        break
                    value = re.sub(r"<[^>]+>", "", lines[index]).strip()
                    if value:
                        cue.append(value)
                    index += 1
                if cue:
                    converted.append(f"[{minutes:02d}:{remainder // 100:02d}.{remainder % 100:02d}]" + " ".join(cue))
            else:
                index += 1
        return "\n".join(converted)
    if fmt == "plain":
        return "\n".join(line.strip() for line in text.splitlines() if line.strip())
    return text


def _timestamp_milliseconds(minutes: str, seconds: str, fraction: str | None) -> int:
    fraction_ms = int((fraction or "0").ljust(3, "0")[:3])
    return (int(minutes) * 60 + int(seconds)) * 1000 + fraction_ms


def parse_lrc_timestamps(lyrics: str) -> list[tuple[str, int]]:
    """Return SYLT entries from standard LRC or enhanced word-timed LRC."""
    entries: list[tuple[str, int]] = []
    for line in lyrics.splitlines():
        line_timestamps = list(_LINE_TIMESTAMP.finditer(line))
        content_start = line_timestamps[-1].end() if line_timestamps else 0
        content = line[content_start:]
        word_timestamps = list(_WORD_TIMESTAMP.finditer(content))

        if word_timestamps:
            for index, match in enumerate(word_timestamps):
                end = word_timestamps[index + 1].start() if index + 1 < len(word_timestamps) else len(content)
                text = content[match.end():end].strip()
                if text:
                    entries.append((text, _timestamp_milliseconds(*match.groups())))
            continue

        text = content.strip()
        if text:
            for match in line_timestamps:
                entries.append((text, _timestamp_milliseconds(*match.groups())))
    return sorted(entries, key=lambda entry: entry[1])


def shift_lrc_timestamps(lyrics: str, offset_seconds: float) -> str:
    """Shift line and word timestamps for an exported audio segment."""
    def shift(match: re.Match) -> str:
        source_ms = _timestamp_milliseconds(
            match.group("minutes"), match.group("seconds"), match.group("fraction")
        )
        if source_ms < offset_seconds * 1000:
            return ""
        shifted_centiseconds = round((source_ms / 1000 - offset_seconds) * 100)
        minutes, remainder = divmod(shifted_centiseconds, 6000)
        return f"{match.group('open')}{minutes:02d}:{remainder // 100:02d}.{remainder % 100:02d}{match.group('close')}"

    shifted_lines = []
    for line in lyrics.splitlines():
        timestamps = list(_ANY_TIMESTAMP.finditer(line))
        if timestamps and all(shift(match) == "" for match in timestamps):
            continue
        shifted_lines.append(_ANY_TIMESTAMP.sub(shift, line))
    return "\n".join(shifted_lines)

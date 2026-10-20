"""On-device yt-dlp adapter. Audio is saved in the app cache before SAF export."""

from __future__ import annotations

import json
import re
from pathlib import Path

import yt_dlp


def _validate_source(source: str) -> str:
    source = (source or "").strip()
    if not (source.startswith("https://") or source.startswith("http://") or source.startswith("ytsearch1:")):
        raise ValueError("只支持 HTTP(S) 音乐链接或 yt-dlp 关键词搜索。")
    return source


def extract_metadata(source: str) -> str:
    """Resolve one public track or search result without downloading audio."""
    source = _validate_source(source)
    options = {"noplaylist": True, "quiet": True, "no_warnings": True, "skip_download": True, "cachedir": False}
    with yt_dlp.YoutubeDL(options) as downloader:
        info = downloader.extract_info(source, download=False)
        if info and "entries" in info:
            info = next((entry for entry in info["entries"] if entry), None)
    if not info:
        raise RuntimeError("没有找到可用的曲目资料。")
    return json.dumps({
        "title": info.get("track") or info.get("title") or "未知曲目",
        "artist": info.get("artist") or info.get("creator") or info.get("uploader") or info.get("channel") or "未知艺人",
        "url": info.get("webpage_url") or info.get("original_url") or "",
        "thumbnail": info.get("thumbnail") or "",
        "duration": info.get("duration") or 0,
        "provider": "yt-dlp",
    }, ensure_ascii=False)


def download_audio(source: str, work_dir: str) -> str:
    """Download one audio item and return JSON containing path and actual title."""
    source = _validate_source(source)

    destination = Path(work_dir).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    options = {
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "outtmpl": str(destination / "%(title).120s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": False,
        "cachedir": False,
        "restrictfilenames": False,
    }

    with yt_dlp.YoutubeDL(options) as downloader:
        info = downloader.extract_info(source, download=True)
        if not info:
            raise RuntimeError("下载器没有返回音频信息。")
        if "entries" in info:
            info = next((entry for entry in info["entries"] if entry), None)
        if not info:
            raise RuntimeError("没有找到可下载的音频。")
        candidates = [Path(item["filepath"]) for item in info.get("requested_downloads", []) if item.get("filepath")]
        if not candidates:
            candidates = [Path(downloader.prepare_filename(info))]
        audio_path = next((item for item in candidates if item.is_file() and item.stat().st_size), None)
        if audio_path is None:
            audio_path = next((item for item in destination.iterdir() if item.is_file() and not item.name.endswith(".part")), None)
        if audio_path is None:
            raise RuntimeError("下载结束，但没有找到生成的音频文件。")

    title = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", "_", str(info.get("title") or audio_path.stem)).strip()
    return json.dumps({"path": str(audio_path), "title": title}, ensure_ascii=False)

"""Playlist parsing and a one-at-a-time batch download queue.

The queue knows nothing about yt-dlp or FFmpeg: the caller passes in ``process_track``, which
turns one playlist entry into a finished audio file. That keeps this module easy to test.
"""
from __future__ import annotations

import re
import shutil
import tempfile
import threading
import time
import urllib.parse
import uuid
import zipfile
from pathlib import Path
from typing import Callable

MAX_BATCH_TRACKS = 200
JOB_TTL_SECONDS = 60 * 60
_VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")
_LIST_ID = re.compile(r"[A-Za-z0-9_-]{10,64}")
_YOUTUBE_HOSTS = {"music.youtube.com", "youtube.com", "www.youtube.com"}
_SAFE_NAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def parse_playlist_url(raw: str) -> dict:
    """Accept only https YouTube / YouTube Music playlist links and return a canonical URL."""
    try:
        parts = urllib.parse.urlsplit(str(raw).strip())
    except ValueError as exc:
        raise ValueError("请输入有效的 YouTube Music 播放列表链接。") from exc
    if parts.scheme != "https" or (parts.hostname or "").lower() not in _YOUTUBE_HOSTS:
        raise ValueError("批量下载目前支持 YouTube / YouTube Music 的播放列表链接（https）。")
    list_id = urllib.parse.parse_qs(parts.query).get("list", [""])[0]
    if parts.path != "/playlist" or not _LIST_ID.fullmatch(list_id):
        raise ValueError("请粘贴播放列表链接（地址里包含 /playlist?list=…）。")
    return {"id": list_id, "url": f"https://www.youtube.com/playlist?list={list_id}"}


def is_playlist_url(raw: str) -> bool:
    try:
        parse_playlist_url(raw)
        return True
    except ValueError:
        return False


def clean_playlist_entry(entry: dict) -> dict | None:
    """Turn a yt-dlp flat-playlist entry into the few fields the UI and queue need."""
    if not isinstance(entry, dict):
        return None
    video_id = str(entry.get("id") or "")
    if not _VIDEO_ID.fullmatch(video_id):
        return None
    title = str(entry.get("track") or entry.get("title") or "").strip()
    if not title or title in {"[Private video]", "[Deleted video]"}:
        return None
    artist = str(entry.get("artist") or "").strip()
    if not artist and isinstance(entry.get("artists"), list) and entry["artists"]:
        artist = str(entry["artists"][0]).strip()
    if not artist:
        artist = str(entry.get("uploader") or entry.get("channel") or "").strip()
    artist = re.sub(r"\s*-\s*Topic$", "", artist)
    if not entry.get("track") and " - " in title and (not artist or artist.casefold() not in title.casefold()):
        head, _, tail = title.partition(" - ")
        if head.strip() and tail.strip():
            artist, title = head.strip(), tail.strip()
    try:
        duration = int(float(entry.get("duration") or 0))
    except (TypeError, ValueError):
        duration = 0
    return {
        "id": video_id,
        "title": title[:256],
        "artist": (artist or "未知艺人")[:256],
        "duration": duration,
        "thumbnail": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
    }


def unique_name(folder: Path, name: str) -> Path:
    """Return folder/name, or 'name (1)', 'name (2)'… when that file already exists."""
    name = _SAFE_NAME.sub("_", name).strip(" .") or "track"
    candidate = folder / name
    stem, suffix, number = candidate.stem, candidate.suffix, 1
    while candidate.exists():
        candidate = folder / f"{stem} ({number}){suffix}"
        number += 1
    return candidate


class BatchJob:
    def __init__(self, tracks: list[dict], options: dict):
        self.id = uuid.uuid4().hex
        self.tracks = tracks
        self.options = options
        self.workdir = Path(tempfile.mkdtemp(prefix="musicdesk-batch-"))
        self.files_dir = self.workdir / "files"
        self.files_dir.mkdir()
        self.state = "queued"          # queued | running | done | cancelled | error
        self.index = 0                 # tracks finished, successfully or not
        self.current = ""
        self.failed: list[dict] = []
        self.succeeded = 0
        self.zip_path: Path | None = None
        self.created = time.time()
        self.cancel_event = threading.Event()
        self.lock = threading.Lock()

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "id": self.id, "state": self.state, "total": len(self.tracks), "done": self.index,
                "succeeded": self.succeeded, "current": self.current, "failed": list(self.failed),
                "ready": self.zip_path is not None,
            }

    def run(self, process_track: Callable[[dict, dict, Path], Path]) -> None:
        with self.lock:
            self.state = "running"
        try:
            for track in self.tracks:
                if self.cancel_event.is_set():
                    break
                with self.lock:
                    self.current = f"{track['artist']} - {track['title']}"
                try:
                    path = process_track(track, self.options, self.files_dir)
                    with self.lock:
                        self.succeeded += 1
                except Exception as exc:  # one bad track must not stop the rest
                    message = " ".join(str(exc).split())[:300] or "下载失败"
                    with self.lock:
                        self.failed.append({"title": track["title"], "artist": track["artist"], "error": message})
                with self.lock:
                    self.index += 1
            files = sorted(p for p in self.files_dir.iterdir() if p.is_file())
            if files:
                archive = self.workdir / "musicdesk-batch.zip"
                with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as bundle:
                    for file in files:
                        bundle.write(file, file.name)
                with self.lock:
                    self.zip_path = archive
            with self.lock:
                self.state = "cancelled" if self.cancel_event.is_set() else "done"
                self.current = ""
        except Exception as exc:
            with self.lock:
                self.state = "error"
                self.failed.append({"title": "", "artist": "", "error": str(exc)[:300]})

    def cleanup(self) -> None:
        shutil.rmtree(self.workdir, ignore_errors=True)


class BatchManager:
    """Runs at most one batch at a time and forgets finished jobs after an hour."""

    def __init__(self):
        self._jobs: dict[str, BatchJob] = {}
        self._lock = threading.Lock()

    def prune(self) -> None:
        with self._lock:
            for job_id, job in list(self._jobs.items()):
                if job.state in {"done", "cancelled", "error"} and time.time() - job.created > JOB_TTL_SECONDS:
                    job.cleanup()
                    del self._jobs[job_id]

    def active(self) -> BatchJob | None:
        with self._lock:
            return next((j for j in self._jobs.values() if j.state in {"queued", "running"}), None)

    def start(self, tracks: list[dict], options: dict, process_track) -> BatchJob:
        self.prune()
        if not tracks:
            raise ValueError("请至少选择一首歌曲。")
        if len(tracks) > MAX_BATCH_TRACKS:
            raise ValueError(f"一次最多下载 {MAX_BATCH_TRACKS} 首。")
        if self.active():
            raise RuntimeError("已有批量任务正在进行，请等它完成或先取消。")
        job = BatchJob(tracks, options)
        with self._lock:
            self._jobs[job.id] = job
        threading.Thread(target=job.run, args=(process_track,), daemon=True).start()
        return job

    def get(self, job_id: str) -> BatchJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def cancel(self, job_id: str) -> bool:
        job = self.get(job_id)
        if not job:
            return False
        job.cancel_event.set()
        return True

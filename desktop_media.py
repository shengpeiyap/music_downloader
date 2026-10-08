"""Native file selection and private local-audio serving for the desktop app."""
from __future__ import annotations

import json
import mimetypes
import os
import secrets
import threading
from pathlib import Path


AUDIO_SUFFIXES = {".mp3", ".m4a", ".flac", ".wav", ".ogg"}
_AUDIO_FILE_TYPES = ("Audio files (*.mp3;*.m4a;*.flac;*.wav;*.ogg)",)


class DesktopMediaBridge:
    """Methods exposed to pywebview's JavaScript API."""

    def __init__(self, server, state_path: str | Path | None = None):
        self.server = server
        self.window = None
        app_data = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        self.state_path = Path(state_path) if state_path else app_data / "MusicDesk" / "playback-state.json"
        self.state_lock = threading.Lock()
        if not hasattr(server, "desktop_media_files"):
            server.desktop_media_files = {}
            server.desktop_media_lock = threading.Lock()

    def select_audio_files(self):
        from webview import FileDialog

        paths = self.window.create_file_dialog(
            FileDialog.OPEN, allow_multiple=True, file_types=_AUDIO_FILE_TYPES
        ) or ()
        return self._register_files(paths)

    def select_music_folder(self):
        from webview import FileDialog

        folders = self.window.create_file_dialog(FileDialog.FOLDER) or ()
        if not folders:
            return []
        root = Path(folders[0])
        paths = (
            path for path in root.rglob("*")
            if path.is_file() and path.suffix.lower() in AUDIO_SUFFIXES
        )
        return self._register_files(paths, root)

    def restore_audio_files(self):
        state = self.load_playback_state()
        paths = state.get("desktopFiles", []) if isinstance(state, dict) else []
        return self._register_files(paths)

    def load_playback_state(self):
        try:
            value = json.loads(self.state_path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def save_playback_state(self, raw_state: str):
        if not isinstance(raw_state, str) or len(raw_state) > 2_000_000:
            return False
        try:
            state = json.loads(raw_state)
        except json.JSONDecodeError:
            return False
        if not isinstance(state, dict):
            return False
        state["desktopFiles"] = [
            path for path in state.get("desktopFiles", [])
            if isinstance(path, str) and len(path) < 32768
        ][:5000]
        try:
            with self.state_lock:
                self.state_path.parent.mkdir(parents=True, exist_ok=True)
                temp_path = self.state_path.with_suffix(".tmp")
                temp_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
                os.replace(temp_path, self.state_path)
            return True
        except OSError:
            return False

    def _register_files(self, paths, root: Path | None = None):
        records = []
        for raw_path in paths:
            try:
                path = Path(raw_path).resolve(strict=True)
                if not path.is_file() or path.suffix.lower() not in AUDIO_SUFFIXES:
                    continue
                stat = path.stat()
            except (OSError, TypeError, ValueError):
                continue
            token = secrets.token_urlsafe(24)
            with self.server.desktop_media_lock:
                self.server.desktop_media_files[token] = path
            try:
                folder = path.parent.relative_to(root).as_posix() if root else "已选歌曲"
            except ValueError:
                folder = path.parent.name
            records.append({
                "path": str(path),
                "name": path.name,
                "size": stat.st_size,
                "lastModified": int(stat.st_mtime * 1000),
                "folderPath": folder or "已选文件夹",
                "url": f"/api/local-audio/{token}",
            })
        return records


def serve_local_audio(handler, token: str) -> None:
    """Stream only files explicitly selected by this desktop session, including seek ranges."""
    server = handler.server
    path = resolve_selected_audio(server, token)
    if path is None:
        handler.send_error(404)
        return
    try:
        size = path.stat().st_size
        start, end, status = 0, size - 1, 200
        range_header = handler.headers.get("Range", "")
        if range_header:
            if not range_header.startswith("bytes=") or "," in range_header:
                handler.send_error(416)
                return
            bounds = range_header[6:].split("-", 1)
            start = int(bounds[0]) if bounds[0] else 0
            end = int(bounds[1]) if len(bounds) > 1 and bounds[1] else size - 1
            if start < 0 or start >= size or end < start:
                handler.send_response(416)
                handler.send_header("Content-Range", f"bytes */{size}")
                handler.end_headers()
                return
            end = min(end, size - 1)
            status = 206
        length = max(0, end - start + 1)
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        handler.send_response(status)
        handler.send_header("Content-Type", content_type)
        handler.send_header("Accept-Ranges", "bytes")
        handler.send_header("Content-Length", str(length))
        if status == 206:
            handler.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        handler.send_header("Cache-Control", "no-store")
        handler.end_headers()
        if getattr(handler, "command", "GET") == "HEAD":
            return
        with path.open("rb") as audio:
            audio.seek(start)
            remaining = length
            while remaining:
                chunk = audio.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                handler.wfile.write(chunk)
                remaining -= len(chunk)
    except (OSError, ValueError):
        handler.send_error(404)


def resolve_selected_audio(server, token: str) -> Path | None:
    lock = getattr(server, "desktop_media_lock", None)
    files = getattr(server, "desktop_media_files", None)
    if lock is None or files is None:
        return None
    with lock:
        path = files.get(token)
    try:
        return path if path is not None and path.is_file() and path.suffix.lower() in AUDIO_SUFFIXES else None
    except OSError:
        return None

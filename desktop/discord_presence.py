"""Opt-in Discord Rich Presence for the local desktop player."""
from __future__ import annotations

import json
import os
import struct
import sys
import threading
import time
import uuid
from typing import Any


class DiscordIPCClient:
    """Minimal Windows Discord RPC client using only the standard library."""

    OP_HANDSHAKE = 0
    OP_FRAME = 1
    OP_PING = 3
    OP_PONG = 4

    @staticmethod
    def _kernel32():
        import ctypes
        from ctypes import wintypes

        api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.CreateFileW.restype = wintypes.HANDLE
        api.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                    wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        api.WaitNamedPipeW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
        api.WriteFile.argtypes = [wintypes.HANDLE, wintypes.LPCVOID, wintypes.DWORD,
                                  ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID]
        api.ReadFile.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
                                 ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID]
        api.SetNamedPipeHandleState.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD),
                                                ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD)]
        api.CloseHandle.argtypes = [wintypes.HANDLE]
        return api

    def __init__(self, application_id: str):
        self.application_id = application_id
        self._handle = None

    @staticmethod
    def _frame(opcode: int, payload: dict[str, Any]) -> bytes:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return struct.pack("<II", opcode, len(body)) + body

    def _write(self, data: bytes) -> None:
        import ctypes
        from ctypes import wintypes

        kernel32 = self._kernel32()
        written = wintypes.DWORD()
        buffer = ctypes.create_string_buffer(data)
        if not kernel32.WriteFile(self._handle, buffer, len(data), ctypes.byref(written), None):
            raise OSError(ctypes.get_last_error(), "Discord IPC 写入失败")
        if written.value != len(data):
            raise OSError("Discord IPC 消息未完整写入")

    def _read_exact(self, size: int, deadline: float) -> bytes:
        import ctypes
        from ctypes import wintypes

        kernel32 = self._kernel32()
        result = bytearray()
        while len(result) < size:
            if time.monotonic() >= deadline:
                raise TimeoutError("Discord IPC 响应超时")
            chunk = ctypes.create_string_buffer(size - len(result))
            read = wintypes.DWORD()
            if kernel32.ReadFile(self._handle, chunk, len(chunk), ctypes.byref(read), None):
                if not read.value:
                    raise OSError("Discord IPC 已断开")
                result.extend(chunk.raw[:read.value])
                continue
            error = ctypes.get_last_error()
            # A nonblocking named pipe reports ERROR_NO_DATA while Discord has no frame ready.
            if error in (2, 109, 233):
                raise OSError(error, "Discord IPC 已断开")
            if error == 234:  # ERROR_MORE_DATA
                result.extend(chunk.raw[:read.value])
                continue
            if error == 997:  # ERROR_IO_PENDING, if the implementation changes to overlapped IO
                time.sleep(0.01)
                continue
            # PIPE_NOWAIT reports ERROR_NO_DATA (232) while Discord has no frame ready.
            if error == 232:
                time.sleep(0.01)
                continue
            raise OSError(error, "Discord IPC 读取失败")
        return bytes(result)

    def _read_frame(self, timeout: float = 3.0) -> tuple[int, dict[str, Any]]:
        deadline = time.monotonic() + timeout
        header = self._read_exact(8, deadline)
        opcode, size = struct.unpack("<II", header)
        if size > 1024 * 1024:
            raise ValueError("Discord IPC 响应过大")
        body = self._read_exact(size, deadline)
        payload = json.loads(body.decode("utf-8")) if body else {}
        if not isinstance(payload, dict):
            raise ValueError("Discord IPC 响应格式无效")
        if opcode == self.OP_PING:
            self._write(struct.pack("<II", self.OP_PONG, len(body)) + body)
        return opcode, payload

    def poll(self) -> None:
        self._read_frame(timeout=0.2)

    def connect(self) -> None:
        if sys.platform != "win32":
            raise OSError("Discord 状态分享目前仅支持 Windows 桌面版")
        import ctypes
        from ctypes import wintypes

        kernel32 = self._kernel32()
        handle = None
        for index in range(10):
            pipe = rf"\\.\pipe\discord-ipc-{index}"
            if not kernel32.WaitNamedPipeW(pipe, 150):
                continue
            candidate = kernel32.CreateFileW(pipe, 0xC0000000, 0, None, 3, 0, None)
            if candidate != wintypes.HANDLE(-1).value:
                handle = candidate
                break
        if handle is None:
            raise ConnectionError("找不到 Discord 桌面版 IPC 管道")
        self._handle = handle
        mode = wintypes.DWORD(0x00000001)  # PIPE_READMODE_BYTE (0) | PIPE_NOWAIT (1)
        if not kernel32.SetNamedPipeHandleState(self._handle, ctypes.byref(mode), None, None):
            self.close()
            raise OSError(ctypes.get_last_error(), "无法配置 Discord IPC 管道")
        self._write(self._frame(self.OP_HANDSHAKE, {"v": 1, "client_id": self.application_id}))
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            opcode, response = self._read_frame(max(0.05, deadline - time.monotonic()))
            if opcode == self.OP_FRAME and response.get("evt") == "READY":
                return
            if response.get("evt") == "ERROR":
                raise ConnectionError("Discord 拒绝了 MusicDesk 的 RPC 握手")
        raise TimeoutError("等待 Discord RPC 握手超时")

    def _request(self, command: str, args: dict[str, Any]) -> None:
        nonce = str(uuid.uuid4())
        self._write(self._frame(self.OP_FRAME, {"cmd": command, "args": args, "nonce": nonce}))
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            opcode, response = self._read_frame(max(0.05, deadline - time.monotonic()))
            if opcode == self.OP_FRAME and response.get("nonce") == nonce:
                data = response.get("data")
                if response.get("evt") == "ERROR" or (isinstance(data, dict) and data.get("code")):
                    raise RuntimeError("Discord RPC 请求失败")
                return
        raise TimeoutError("等待 Discord RPC 回复超时")

    def update(self, *, details: str | None = None, state: str | None = None,
               start: int | None = None, end: int | None = None) -> None:
        activity: dict[str, Any] = {}
        if details:
            activity["details"] = details
        if state:
            activity["state"] = state
        timestamps = {key: value for key, value in (("start", start), ("end", end)) if value is not None}
        if timestamps:
            activity["timestamps"] = timestamps
        self._request("SET_ACTIVITY", {"pid": os.getpid(), "activity": activity})

    def clear(self) -> None:
        if self._handle is not None:
            self._request("SET_ACTIVITY", {"pid": os.getpid(), "activity": None})

    def close(self) -> None:
        if self._handle is None:
            return
        handle, self._handle = self._handle, None
        self._kernel32().CloseHandle(handle)


def clean_payload(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Discord 状态数据无效。")
    app_id = value.get("application_id", "")
    if not isinstance(app_id, str) or not app_id.isascii() or not app_id.isdigit() or not 17 <= len(app_id) <= 20:
        raise ValueError("请输入 Discord Developer Portal 中的应用程序 ID。")
    title = value.get("title", "")
    artist = value.get("artist", "")
    if not isinstance(title, str) or not isinstance(artist, str):
        raise ValueError("歌曲标题和歌手必须是文本。")
    try:
        duration = max(0, min(int(value.get("duration", 0)), 24 * 60 * 60))
        position = max(0, min(int(float(value.get("position", 0))), duration))
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("播放进度无效。") from exc
    has_track = value.get("has_track", bool(title.strip()))
    share_details = value.get("share_details", True)
    if not isinstance(has_track, bool) or not isinstance(share_details, bool):
        raise ValueError("歌曲信息分享选项无效。")
    return {
        "application_id": app_id,
        "title": title.strip()[:128],
        "artist": artist.strip()[:128],
        "duration": duration,
        "position": position,
        "playing": value.get("playing") is True,
        "has_track": has_track,
        "share_details": share_details,
    }


def build_presence_fields(payload: dict[str, Any], now: int | None = None) -> dict[str, Any] | None:
    if not payload["has_track"]:
        return None
    now = int(time.time()) if now is None else int(now)
    is_playing = payload["playing"] and payload["duration"] > 0
    start = now - payload["position"] if is_playing else None
    end = start + payload["duration"] if start is not None else None
    artist = payload["artist"]
    fields = {}
    if payload["share_details"]:
        fields["details"] = payload["title"]
        fields["state"] = artist if is_playing else (f"已暂停 · {artist}" if artist else "已暂停")
    if start is not None:
        fields.update(start=start, end=end)
    return fields


class DiscordPresenceManager:
    """Keep RPC work off the HTTP/audio threads and coalesce rapid player events."""

    def __init__(self):
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._desired: dict[str, Any] | None = None
        self._thread: threading.Thread | None = None
        self._client = None
        self._connected = False
        self._message = "未连接"

    def update(self, payload: dict[str, Any] | None) -> dict[str, Any]:
        with self._lock:
            self._desired = payload
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run, name="MusicDesk-DiscordPresence", daemon=True)
                self._thread.start()
            self._message = "正在更新 Discord 状态…" if payload else "正在关闭 Discord 状态…"
        self._wake.set()
        return self.status()

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {"connected": self._connected, "message": self._message}

    def close(self) -> None:
        self._stop.set()
        self._wake.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=2)

    def _disconnect(self) -> None:
        client, self._client = self._client, None
        self._connected = False
        if client is not None:
            try:
                client.clear()
            except Exception:
                pass
            try:
                client.close()
            except Exception:
                pass

    def _run(self) -> None:
        active_app_id = None
        while not self._stop.is_set():
            timeout = 0.25 if self._client is not None else 5
            woke = self._wake.wait(timeout=timeout)
            self._wake.clear()
            if self._stop.is_set():
                break
            if not woke and self._client is not None:
                try:
                    self._client.poll()
                except TimeoutError:
                    pass
                except Exception:
                    self._disconnect()
                    active_app_id = None
                    with self._lock:
                        self._message = "Discord 连接中断；正在尝试重连"
                continue
            with self._lock:
                payload = self._desired
            if payload is None:
                self._disconnect()
                with self._lock:
                    self._message = "已关闭"
                continue
            app_id = payload["application_id"]
            try:
                if self._client is None or active_app_id != app_id:
                    self._disconnect()
                    self._client = DiscordIPCClient(app_id)
                    self._client.connect()
                    active_app_id = app_id
                self._connected = True
                activity = build_presence_fields(payload)
                if activity is None:
                    self._client.clear()
                    message = "已连接；播放歌曲时显示状态"
                elif not payload["share_details"]:
                    self._client.update(**activity)
                    message = "已连接；歌曲信息已隐藏"
                else:
                    self._client.update(**activity)
                    message = "已连接并正在分享播放状态" if payload["playing"] and payload["duration"] > 0 else "已连接；歌曲已暂停"
                with self._lock:
                    self._message = message
            except Exception:
                self._disconnect()
                active_app_id = None
                with self._lock:
                    self._message = "无法连接 Discord；请确认 Discord 桌面版已开启"
                # Retry periodically while enabled, but wake immediately for a new setting.
                self._wake.wait(timeout=5)
                self._wake.clear()
        self._disconnect()


_manager: DiscordPresenceManager | None = None
_manager_lock = threading.Lock()


def get_manager() -> DiscordPresenceManager:
    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = DiscordPresenceManager()
            import atexit

            atexit.register(_manager.close)
        return _manager


def get_status() -> dict[str, Any]:
    with _manager_lock:
        manager = _manager
    return manager.status() if manager else {"connected": False, "message": "状态分享尚未启动"}

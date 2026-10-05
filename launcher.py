"""Start MusicDesk in a native window with a browser fallback."""
from __future__ import annotations

import os
import sys
import threading
import webbrowser
from http.server import ThreadingHTTPServer
from pathlib import Path

from app import Handler, ROOT


def main() -> None:
    if getattr(sys, "frozen", False):
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    url = f"http://127.0.0.1:{server.server_port}"
    threading.Thread(target=server.serve_forever, daemon=True).start()

    try:
        import webview

        webview.create_window(
            "MusicDesk", url, width=1200, height=860, min_size=(800, 600)
        )
        webview.start()
    except Exception:
        # Keep the user able to run the app when WebView2 is unavailable.
        webbrowser.open(url)
        _show_browser_fallback(url)
    finally:
        server.shutdown()
        server.server_close()


def _show_browser_fallback(url: str) -> None:
    import tkinter as tk
    from tkinter import messagebox

    window = tk.Tk()
    window.title("MusicDesk is running")
    window.geometry("380x150")
    icon = ROOT / "icon.ico"
    if icon.is_file():
        window.iconbitmap(str(icon))
    tk.Label(window, text="MusicDesk 已在浏览器中打开。", padx=20, pady=18).pack()
    tk.Button(window, text="重新打开 MusicDesk", command=lambda: webbrowser.open(url)).pack()

    def close_app() -> None:
        if messagebox.askyesno("退出 MusicDesk", "关闭 MusicDesk 服务吗？"):
            window.destroy()

    window.protocol("WM_DELETE_WINDOW", close_app)
    window.mainloop()


if __name__ == "__main__":
    main()

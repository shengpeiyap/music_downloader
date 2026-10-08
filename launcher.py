"""Start MusicDesk in a native desktop window (or the system browser via --browser).

默认：强制使用 pywebview 原生窗口（Edge WebView2 on Windows，不回退到外部浏览器）
显式 --browser：启动本地 HTTP 服务后用系统默认浏览器打开，与 start.bat 行为一致
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
import webbrowser
from http.server import ThreadingHTTPServer
from pathlib import Path

from app import Handler, ROOT


def enable_file_downloads(webview_module) -> None:
    webview_module.settings["ALLOW_DOWNLOADS"] = True


def create_native_window(webview_module, url: str):
    """Create the app window using the pywebview API supported by the bundle."""
    return webview_module.create_window(
        title="MusicDesk",
        url=url,
        width=1200,
        height=860,
        min_size=(800, 600),
        background_color="#121218",
    )


def _find_icon() -> str | None:
    p = ROOT / "icon.ico"
    if p.is_file():
        return str(p)
    return None


def _show_error_dialog(title: str, body: str) -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox

        window = tk.Tk()
        window.withdraw()
        icon = _find_icon()
        if icon:
            try:
                window.iconbitmap(icon)
            except Exception:
                pass
        messagebox.showerror(title, body)
        window.destroy()
    except Exception:
        print(f"[{title}] {body}", file=sys.__stderr__)


def _show_browser_mode(url: str, shutdown_server) -> None:
    import tkinter as tk
    from tkinter import messagebox

    webbrowser.open(url)

    window = tk.Tk()
    window.title("MusicDesk 服务已启动")
    window.geometry("460x190")
    icon = _find_icon()
    if icon:
        try:
            window.iconbitmap(icon)
        except Exception:
            pass
    tk.Label(
        window,
        text=f"MusicDesk 已在默认浏览器中打开。\n\n访问地址：{url}\n关闭此对话框后，MusicDesk 服务将停止。",
        padx=24,
        pady=20,
        justify="left",
    ).pack()
    tk.Button(window, text="再次在浏览器中打开", command=lambda: webbrowser.open(url)).pack(
        pady=(0, 12)
    )

    def close_app() -> None:
        if messagebox.askyesno("退出 MusicDesk", "确认关闭 MusicDesk 后台服务吗？"):
            try:
                shutdown_server()
            finally:
                window.destroy()

    window.protocol("WM_DELETE_WINDOW", close_app)
    try:
        window.mainloop()
    finally:
        try:
            shutdown_server()
        except Exception:
            pass


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="MusicDesk",
        description="MusicDesk - 本地音乐元数据、格式转换、标签封装、播放工具",
    )
    parser.add_argument(
        "--browser",
        action="store_true",
        help="使用系统默认浏览器打开（而不是原生窗口）",
    )
    parser.add_argument(
        "--lan",
        action="store_true",
        help="绑定 0.0.0.0 允许局域网访问（需配合 --token 使用更安全）",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="指定 HTTP 服务端口（默认 0 由系统分配可用端口）",
    )
    parser.add_argument(
        "--token",
        type=str,
        default=None,
        help="指定 API Bearer Token（默认每次启动随机生成，仅 --lan 模式下需要手动提供时使用）",
    )
    args = parser.parse_args()

    if getattr(sys, "frozen", False):
        devnull = open(os.devnull, "w", encoding="utf-8")
        sys.stdout = devnull
        sys.stderr = devnull

    if args.lan:
        bind = "0.0.0.0"
    else:
        bind = "127.0.0.1"

    server = ThreadingHTTPServer((bind, args.port), Handler)
    actual_port = server.server_port
    if bind == "0.0.0.0":
        url = f"http://127.0.0.1:{actual_port}"
    else:
        url = f"http://127.0.0.1:{actual_port}"

    def shutdown() -> None:
        try:
            server.shutdown()
        finally:
            server.server_close()

    threading.Thread(target=server.serve_forever, daemon=True).start()

    if args.browser:
        try:
            _show_browser_mode(url, shutdown)
        finally:
            try:
                shutdown()
            except Exception:
                pass
        return

    try:
        import webview
    except Exception as e:
        body = (
            "无法启动 MusicDesk 原生桌面窗口：缺少 pywebview。\n"
            "请通过项目仓库安装 requirements-build.txt 后重新构建。\n\n"
            "临时方案：使用命令行参数 --browser 在系统默认浏览器中打开。"
            f"\n\n详细信息：{e}"
        )
        _show_error_dialog("MusicDesk 启动失败", body)
        shutdown()
        sys.exit(2)

    try:
        enable_file_downloads(webview)
        create_native_window(webview, url)
        webview.start(debug=False, func=None)
    except Exception as e:
        body = (
            "无法启动 MusicDesk 原生窗口。请确认便携版文件完整；若错误提示 WebView2 缺失，"
            "请安装 Microsoft Edge WebView2 Runtime：\n"
            "https://developer.microsoft.com/microsoft-edge/webview2/\n\n"
            "临时方案：使用命令行参数 MusicDesk.exe --browser 在默认浏览器打开。\n\n"
            f"详细错误：{e}"
        )
        _show_error_dialog("MusicDesk 原生窗口启动失败", body)
        shutdown()
        sys.exit(3)
    finally:
        try:
            shutdown()
        except Exception:
            pass


if __name__ == "__main__":
    main()

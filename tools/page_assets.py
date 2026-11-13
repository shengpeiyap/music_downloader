"""Find the local files index.html loads, and read the page together with them.

The page is being split out of one large index.html into scripts and stylesheets under
web/. Two things must then follow every new file automatically:

- tools/sync_android_assets.py copies each of them into the Android assets;
- tests read the page *with* its scripts, so a function moving into web/ does not hide
  it from the checks that look for it.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "index.html"
# Loaded from page code rather than a tag (DEFAULT_COVER), so it is listed explicitly.
EXTRA_ASSETS = ("default_song_img.png",)

_SCRIPT = re.compile(r'<script\b[^>]*\bsrc="([^"]+)"')
_STYLESHEET = re.compile(r'<link\b[^>]*\brel="stylesheet"[^>]*\bhref="([^"]+)"|<link\b[^>]*\bhref="([^"]+)"[^>]*\brel="stylesheet"')


def _is_local(ref: str) -> bool:
    return not re.match(r"^(?:[a-z]+:)?//", ref, re.I) and not ref.startswith(("data:", "#"))


def local_assets(page: Path = PAGE) -> list[str]:
    """Page-relative paths of local scripts and stylesheets, in the order the page loads them."""
    html = Path(page).read_text(encoding="utf-8")
    found: list[tuple[int, str]] = [(m.start(), m.group(1)) for m in _SCRIPT.finditer(html)]
    found += [(m.start(), m.group(1) or m.group(2)) for m in _STYLESHEET.finditer(html)]
    ordered = [ref for _, ref in sorted(found)]
    return [ref for ref in dict.fromkeys(ordered) if _is_local(ref)]


def shared_files(page: Path = PAGE) -> list[str]:
    """Everything the Android app and the portable build must ship next to index.html."""
    return ["index.html", *local_assets(page), *EXTRA_ASSETS]


def page_source(page: Path = PAGE) -> str:
    """index.html followed by the text of every local script and stylesheet it loads."""
    page = Path(page)
    parts = [page.read_text(encoding="utf-8")]
    for ref in local_assets(page):
        parts.append(f"\n/* ---- {ref} ---- */\n" + (page.parent / ref).read_text(encoding="utf-8"))
    return "".join(parts)

"""Copy the shared web UI from the repository root into the Android assets.

The root files are the single source of truth. Run this after editing them:

    python tools/sync_android_assets.py          # copy
    python tools/sync_android_assets.py --check  # exit 1 if the copies differ
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "android" / "app" / "src" / "main" / "assets"
SHARED = ("index.html", "i18n.js", "library_sort.js", "default_song_img.png")


def differing() -> list[str]:
    return [name for name in SHARED if not (ASSETS / name).exists() or (ROOT / name).read_bytes() != (ASSETS / name).read_bytes()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="only report differences")
    args = parser.parse_args()
    stale = differing()
    if args.check:
        if stale:
            print("Android assets are out of date: " + ", ".join(stale), file=sys.stderr)
            return 1
        return 0
    for name in stale:
        shutil.copyfile(ROOT / name, ASSETS / name)
        print(f"updated {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

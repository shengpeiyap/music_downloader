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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from page_assets import ROOT, shared_files  # noqa: E402

ASSETS = ROOT / "android" / "app" / "src" / "main" / "assets"
# Derived from the scripts and stylesheets index.html loads, so files split out into web/
# are copied without editing this list.
SHARED = tuple(shared_files())


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
        (ASSETS / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, ASSETS / name)
        print(f"updated {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

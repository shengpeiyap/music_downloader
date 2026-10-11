"""Create the portable Windows package from the PyInstaller output folder."""
from __future__ import annotations

from pathlib import Path
import shutil
import zipfile


ROOT = Path(__file__).resolve().parent


def create_portable_archive(
    package_dir: Path = ROOT / "dist" / "MusicDesk",
    archive_path: Path = ROOT / "dist" / "MusicDesk-portable.zip",
) -> Path:
    package_dir = Path(package_dir)
    archive_path = Path(archive_path)
    if not package_dir.is_dir():
        raise FileNotFoundError(f"Portable app folder not found: {package_dir}")

    # yt-dlp needs an external JS runtime for current YouTube challenge solving.
    # Keep it beside yt-dlp.exe so the portable build can find it without PATH setup.
    bundled_runtime = False
    for runtime in ("deno", "node", "qjs"):
        runtime_path = shutil.which(runtime)
        if runtime_path:
            runtime_file = Path(runtime_path)
            shutil.copy2(runtime_file, package_dir / runtime_file.name)
            bundled_runtime = True
            break
    if not bundled_runtime:
        print("Warning: no JavaScript runtime found; YouTube downloads require Deno, Node.js 22+, or QuickJS.")

    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
        for file_path in sorted(package_dir.rglob("*")):
            if file_path.is_file():
                archive.write(file_path, file_path.relative_to(package_dir).as_posix())
    return archive_path


if __name__ == "__main__":
    output = create_portable_archive()
    print(f"Portable package: {output}")

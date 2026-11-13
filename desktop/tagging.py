"""Desktop audio-tag reading and cover-art normalization."""
from __future__ import annotations

import base64
from io import BytesIO

from PIL import Image


class TaggingService:
    """Read existing tags and normalize artwork through app compatibility hooks."""

    def __init__(self, services):
        self.services = services

    def load_music_tag(self, path: str):
        """Load metadata support on demand so the web app still starts on lean installs."""
        try:
            import music_tag
        except ImportError as exc:
            raise RuntimeError("音频标签功能缺少 music-tag 依赖，请重新安装 requirements.txt 中的依赖。") from exc
        return music_tag.load_file(path)

    def read_music_metadata(self, path: str, filename: str) -> dict:
        s = self.services
        audio = s.load_music_tag(path)

        def get_tag(name: str) -> str:
            # music-tag coerces some fields to int and raises on values such as "3/12" (FLAC/OGG).
            try:
                return str(audio[name]) if audio[name] else ""
            except (KeyError, ValueError, TypeError):
                return ""

        cover = None
        try:
            artwork = audio["artwork"]
            if artwork and artwork.values:
                image = artwork.first
                cover = f"data:{image.mime or 'image/jpeg'};base64," + base64.b64encode(image.data).decode("ascii")
        except (KeyError, IndexError, ValueError):
            # music-tag raises KeyError for an M4A that has no 'covr' atom; a missing cover is fine.
            cover = None

        def raw_vorbis_number(key: str) -> str:
            try:
                import mutagen
                easy = mutagen.File(path, easy=True)
                values = easy.get(key) if easy is not None else None
                return str(values[0]) if values else ""
            except Exception:
                return ""

        def number_with_total(number_key: str, total_key: str) -> str:
            number = get_tag(number_key)
            total = get_tag(total_key)
            if not number:
                # "3/12" style values are kept verbatim by FLAC/OGG; read them straight from the file.
                combined = raw_vorbis_number(number_key)
                if combined:
                    return combined
            if number in {"", "0"}:
                return ""
            return f"{number}/{total}" if total not in {"", "0"} else number

        return {
            "filename": filename,
            "title": get_tag("title"),
            "artist": get_tag("artist"),
            "album": get_tag("album"),
            "albumartist": get_tag("albumartist"),
            "year": get_tag("year"),
            "track_num": number_with_total("tracknumber", "totaltracks"),
            "disc_num": number_with_total("discnumber", "totaldiscs"),
            "genre": get_tag("genre"),
            "composer": get_tag("composer"),
            "lyrics": s.normalize_lyrics(get_tag("lyrics")),
            "lyrics_fields": s.describe_embedded_lyrics(path),
            "cover": cover,
        }

    def crop_yt_padding_smart(self, img_bytes: bytes) -> bytes:
        if not img_bytes:
            return img_bytes
        try:
            img = Image.open(BytesIO(img_bytes)).convert("RGB")
            w, h = img.size
            min_dim = min(w, h)
            left = (w - min_dim) // 2
            top = (h - min_dim) // 2
            img_sq = img.crop((left, top, left + min_dim, top + min_dim))

            sq_w, sq_h = img_sq.size
            pixels = img_sq.load()
            bg_color = pixels[0, 0]

            def is_similar(c1, c2, tol=25):
                return sum(abs(a - b) for a, b in zip(c1, c2)) < tol

            top_b, bottom_b, left_b, right_b = 0, sq_h, 0, sq_w
            for y in range(sq_h // 2):
                if not all(is_similar(pixels[x, y], bg_color) for x in range(0, sq_w, 5)):
                    top_b = y
                    break
            for y in range(sq_h - 1, sq_h // 2, -1):
                if not all(is_similar(pixels[x, y], bg_color) for x in range(0, sq_w, 5)):
                    bottom_b = y + 1
                    break
            for x in range(sq_w // 2):
                if not all(is_similar(pixels[x, y], bg_color) for y in range(0, sq_h, 5)):
                    left_b = x
                    break
            for x in range(sq_w - 1, sq_w // 2, -1):
                if not all(is_similar(pixels[x, y], bg_color) for y in range(0, sq_h, 5)):
                    right_b = x + 1
                    break

            if right_b - left_b > 50 and bottom_b - top_b > 50:
                img_final = img_sq.crop((left_b, top_b, right_b, bottom_b))
            else:
                img_final = img_sq
            output = BytesIO()
            img_final.save(output, format="JPEG", quality=95)
            return output.getvalue()
        except Exception as exc:
            print(f"[MusicDesk 智能裁剪提示]: {exc}")
            return img_bytes

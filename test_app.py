import unittest
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app import fetch_media_stream, find_ffmpeg, parse_share_url, process_and_export_media
import tempfile
from pathlib import Path


class FfmpegResolutionTests(unittest.TestCase):
    def test_prefers_app_managed_ffmpeg(self):
        with patch.dict(sys.modules, {"imageio_ffmpeg": SimpleNamespace(get_ffmpeg_exe=lambda: sys.executable)}):
            with patch("app.shutil.which", return_value="system-ffmpeg"):
                self.assertEqual(find_ffmpeg(), sys.executable)

    def test_falls_back_to_system_ffmpeg(self):
        with patch.dict(sys.modules, {"imageio_ffmpeg": None}):
            with patch("app.shutil.which", return_value="system-ffmpeg"):
                self.assertEqual(find_ffmpeg(), "system-ffmpeg")


class ShareUrlTests(unittest.TestCase):
    def test_spotify_track(self):
        self.assertEqual(parse_share_url("https://open.spotify.com/track/abc123?si=xyz"), {
            "provider": "spotify", "id": "abc123", "url": "https://open.spotify.com/track/abc123"
        })

    def test_youtube_music_video(self):
        result = parse_share_url("https://music.youtube.com/watch?v=dQw4w9WgXcQ&list=abc")
        self.assertEqual(result["provider"], "youtube")
        self.assertEqual(result["id"], "dQw4w9WgXcQ")

    def test_short_youtube_link(self):
        self.assertEqual(parse_share_url("https://youtu.be/dQw4w9WgXcQ")["id"], "dQw4w9WgXcQ")

    def test_rejects_untrusted_or_unsupported_urls(self):
        for url in ("http://open.spotify.com/track/abc", "https://example.com/track/abc", "https://open.spotify.com/album/abc"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                parse_share_url(url)


class FetchMediaStreamTests(unittest.TestCase):
    def test_streams_response_to_temp_file(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.geturl.return_value = "https://media.example/audio"
        response.read.side_effect = [b"media", b""]
        with tempfile.TemporaryDirectory() as directory, patch("app.urllib.request.urlopen", return_value=response):
            path = fetch_media_stream("https://media.example/audio", directory)
            try:
                self.assertEqual(Path(path).read_bytes(), b"media")
                self.assertEqual(Path(path).parent, Path(directory))
            finally:
                Path(path).unlink()

    def test_rejects_non_http_and_private_ip_urls(self):
        for url in ("file:///etc/passwd", "http://127.0.0.1/media"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                fetch_media_stream(url)


class ProcessAndExportTests(unittest.TestCase):
    def test_exports_mp3_with_id3_and_cover_then_cleans_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "cached.bin"
            cover = root / "cover.jpg"
            output = root / "out"
            source.write_bytes(b"source")
            cover.write_bytes(b"cover-data")

            def fake_ffmpeg(args, **kwargs):
                Path(args[-1]).write_bytes(b"mp3-data")
                return SimpleNamespace(returncode=0)

            with patch("app.find_ffmpeg", return_value="ffmpeg"), patch("app.subprocess.run", side_effect=fake_ffmpeg), \
                 patch("mutagen.id3.ID3.save") as save:
                result = process_and_export_media(source, "Song", "Artist", cover, "MP3", output)

            self.assertEqual(result.read_bytes(), b"mp3-data")
            self.assertFalse(source.exists())
            save.assert_called_once()

    def test_rejects_non_mp3_id3_export(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "cached.bin"
            cover = Path(directory) / "cover.jpg"
            source.write_bytes(b"source")
            cover.write_bytes(b"cover")
            with self.assertRaises(ValueError):
                process_and_export_media(source, "Song", "Artist", cover, "flac", directory)


if __name__ == "__main__":
    unittest.main()

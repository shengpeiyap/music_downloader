import unittest
import sys
from types import SimpleNamespace
from unittest.mock import patch

from app import find_ffmpeg, parse_share_url


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


if __name__ == "__main__":
    unittest.main()

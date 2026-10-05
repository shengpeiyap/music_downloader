import unittest
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app import fetch_media_stream, fetch_spotify_embed_html, fetch_spotify_oembed, find_ffmpeg, lookup_metadata, parse_share_url, process_and_export_media
import tempfile
from pathlib import Path
from contextlib import redirect_stdout
from io import StringIO


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
    def test_spotify_embed_metadata_decodes_entities(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = (
            b'<meta property="og:title" content="Song &amp; More">'
            b'<meta name="music:musician" content="Artist Name">'
            b'<meta property="og:image" content="https://img.example/cover.jpg">'
        )
        with patch("app.urllib.request.urlopen", return_value=response):
            result = fetch_spotify_embed_html("abc123")
        self.assertEqual(result["title"], "Song & More")
        self.assertEqual(result["artist"], "Artist Name")
        self.assertEqual(result["thumbnail"], "https://img.example/cover.jpg")

    def test_musicbrainz_can_fill_unknown_artist(self):
        with patch("app.fetch_spotify_oembed", return_value={"title": "Song", "artist": "", "thumbnail": "https://img.example/cover.jpg"}), \
             patch("app.fetch_spotify_embed_html", return_value={"title": "Song", "artist": "", "thumbnail": None}), \
             patch("app.lookup_musicbrainz_metadata", return_value={
                 "artist": "Artist", "album": "Album", "year": "2000", "track_num": "", "cover_url": None
             }) as lookup:
            result = lookup_metadata("https://open.spotify.com/track/abc123")
        lookup.assert_called_once_with("Song", "\u672a\u77e5\u827a\u4eba", known_album="")
        self.assertEqual(result["artist"], "Artist")

    def test_spotify_oembed_reads_public_title_and_thumbnail(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b'{"title":"Song","thumbnail_url":"https://img.example/cover.jpg"}'
        with patch("app.urllib.request.urlopen", return_value=response) as open_url:
            result = fetch_spotify_oembed("https://open.spotify.com/track/abc123")
        self.assertEqual(result["title"], "Song")
        self.assertEqual(result["thumbnail"], "https://img.example/cover.jpg")
        self.assertIn("open.spotify.com/oembed?url=", open_url.call_args.args[0].full_url)

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
    def test_ytdlp_execution(self):
        def mock_run(cmd, **kwargs):
            # 找到输出路径参数中的基目录
            base_dir = Path(cmd[cmd.index("-o") + 1]).parent
            fake_mp3 = base_dir / "ytdlp_dQw4w9WgXcQ.mp3"
            fake_mp3.write_bytes(b"media")
            return SimpleNamespace(returncode=0, stdout="success", stderr="")

        with tempfile.TemporaryDirectory() as directory, patch("app.subprocess.run", side_effect=mock_run), redirect_stdout(StringIO()):
            path, source_url = fetch_media_stream("https://www.youtube.com/watch?v=dQw4w9WgXcQ", temp_dir=directory)
            self.assertTrue(path.exists())
            self.assertEqual(path.read_bytes(), b"media")
            self.assertEqual(source_url, "https://www.youtube.com/watch?v=dQw4w9WgXcQ")


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
                result = process_and_export_media(
                    source, {"title": "Song", "artist": "Artist"}, cover, "MP3", output
                )

            self.assertEqual(result.read_bytes(), b"mp3-data")
            self.assertFalse(source.exists())
            save.assert_called_once()


if __name__ == "__main__":
    unittest.main()

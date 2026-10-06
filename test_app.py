import unittest
import sys
import io
import wave
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from PIL import Image

from app import fetch_lrc_lyrics, fetch_media_stream, fetch_spotify_embed_html, fetch_spotify_oembed, find_ffmpeg, load_music_tag, lookup_metadata, lookup_metadata_by_keyword, make_tag_export_filename, multipart_fields, multipart_text, parse_metadata_search_query, parse_share_url, process_and_export_media, read_music_metadata
import tempfile
from pathlib import Path
from contextlib import redirect_stdout
from io import StringIO
from launcher import enable_file_downloads
from package_portable import create_portable_archive


class FfmpegResolutionTests(unittest.TestCase):
    def test_prefers_app_managed_ffmpeg(self):
        with patch.dict(sys.modules, {"imageio_ffmpeg": SimpleNamespace(get_ffmpeg_exe=lambda: sys.executable)}):
            with patch("app.shutil.which", return_value="system-ffmpeg"):
                self.assertEqual(find_ffmpeg(), sys.executable)

    def test_falls_back_to_system_ffmpeg(self):
        with patch.dict(sys.modules, {"imageio_ffmpeg": None}):
            with patch("app.shutil.which", return_value="system-ffmpeg"):
                self.assertEqual(find_ffmpeg(), "system-ffmpeg")


class DesktopLauncherTests(unittest.TestCase):
    def test_enables_native_file_downloads(self):
        webview_module = SimpleNamespace(settings={})
        enable_file_downloads(webview_module)
        self.assertTrue(webview_module.settings["ALLOW_DOWNLOADS"])

    def test_portable_archive_keeps_app_relative_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "MusicDesk"
            (package / "_internal").mkdir(parents=True)
            (package / "MusicDesk.exe").write_bytes(b"app")
            (package / "_internal" / "music_tag.py").write_bytes(b"dependency")
            archive_path = create_portable_archive(package, root / "package.zip")

            import zipfile
            with zipfile.ZipFile(archive_path) as archive:
                self.assertEqual(set(archive.namelist()), {"MusicDesk.exe", "_internal/music_tag.py"})
                self.assertIsNone(archive.testzip())


class LocalTagMetadataTests(unittest.TestCase):
    def test_multipart_text_uses_utf8_for_chinese_form_fields(self):
        boundary = "musicdesk-boundary"
        raw = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"title\"\r\n\r\n"
            "月明かり\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"artist\"\r\n"
            "Content-Type: text/plain; charset=UTF-8\r\n\r\nヨルシカ\r\n"
            f"--{boundary}--\r\n"
        ).encode("utf-8")
        fields = multipart_fields(f"multipart/form-data; boundary={boundary}", raw)

        self.assertEqual(multipart_text(fields, "title"), "月明かり")
        self.assertEqual(multipart_text(fields, "artist"), "ヨルシカ")

    def test_tag_export_filename_uses_artist_and_title(self):
        self.assertEqual(
            make_tag_export_filename("ヨルシカ", "月明かり", "source.wav", "mp3"),
            "ヨルシカ - 月明かり.mp3",
        )
        self.assertEqual(
            make_tag_export_filename("", "", "source track.wav", "mp3"),
            "未知艺人 - source track.mp3",
        )

    def test_keyword_query_accepts_artist_title_or_title(self):
        self.assertEqual(parse_metadata_search_query("  ヨルシカ - 月明かり  "), ("ヨルシカ", "月明かり"))
        self.assertEqual(parse_metadata_search_query("月明かり"), ("未知艺人", "月明かり"))

    def test_keyword_search_uses_metadata_and_lyrics_sources(self):
        with patch("app.lookup_musicbrainz_metadata", return_value={
            "artist": "Artist", "album": "Album", "year": "2020", "cover_url": None
        }) as musicbrainz, patch("app.fetch_lrc_lyrics", return_value="[00:01.00]Lyric") as lyrics:
            result = lookup_metadata_by_keyword("Artist - Track")

        musicbrainz.assert_called_once_with("Track", "Artist")
        lyrics.assert_called_once_with("Track", "Artist")
        self.assertEqual(result["title"], "Track")
        self.assertEqual(result["album"], "Album")
        self.assertEqual(result["lyrics"], "[00:01.00]Lyric")

    def test_load_music_tag_is_imported_on_demand(self):
        fake_audio = object()
        fake_module = SimpleNamespace(load_file=lambda path: (path, fake_audio))
        with patch.dict(sys.modules, {"music_tag": fake_module}):
            self.assertEqual(load_music_tag("song.mp3"), ("song.mp3", fake_audio))

    def test_reads_tags_and_first_of_multiple_embedded_covers(self):
        class Values:
            def __init__(self, value="", values=None, first=None):
                self.value = value
                self.values = values if values is not None else ([value] if value else [])
                self.first = first

            def __bool__(self):
                return bool(self.values)

            def __str__(self):
                return str(self.value)

        cover = SimpleNamespace(mime="image/png", data=b"png-cover")
        tags = {
            "title": Values("Track"), "artist": Values("Artist"), "album": Values(),
            "albumartist": Values(), "year": Values("2024"), "lyrics": Values(),
            "artwork": Values(values=[cover, cover], first=cover),
        }
        class Audio:
            def __getitem__(self, key):
                return tags[key]
        with patch("app.load_music_tag", return_value=Audio()):
            result = read_music_metadata("song.mp3", "song.mp3")

        self.assertEqual(result["title"], "Track")
        self.assertEqual(result["artist"], "Artist")
        self.assertEqual(result["album"], "")
        self.assertEqual(result["cover"], "data:image/png;base64,cG5nLWNvdmVy")

    def test_music_tag_round_trips_wav_tags_and_artwork(self):
        import music_tag

        with tempfile.TemporaryDirectory() as directory:
            audio_path = Path(directory) / "tagged.wav"
            with wave.open(str(audio_path), "wb") as audio_file:
                audio_file.setnchannels(1)
                audio_file.setsampwidth(2)
                audio_file.setframerate(8000)
                audio_file.writeframes(b"\0\0" * 800)

            image_buffer = io.BytesIO()
            Image.new("RGB", (2, 2), "red").save(image_buffer, format="PNG")
            tags = music_tag.load_file(str(audio_path))
            tags["title"] = "Tag test"
            tags["artwork"] = image_buffer.getvalue()
            tags.save()

            result = read_music_metadata(str(audio_path), audio_path.name)

        self.assertEqual(result["title"], "Tag test")
        self.assertTrue(result["cover"].startswith("data:image/png;base64,"))


class ShareUrlTests(unittest.TestCase):
    def test_spotify_embed_metadata_decodes_entities(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = (
            b'<meta property="og:title" content="Song &amp; More">'
            b'<meta name="music:musician" content="Artist Name">'
            b'<meta property="og:image" content="https://img.example/cover.jpg">'
        )
        with patch("app.urllib.request.urlopen", return_value=response), redirect_stdout(StringIO()):
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


class LyricsLookupTests(unittest.TestCase):
    def test_fetches_synced_lyrics_from_lrclib(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b'{"syncedLyrics":"[00:01.00]Hello"}'
        with patch("app.urllib.request.urlopen", return_value=response), redirect_stdout(StringIO()):
            lyrics = fetch_lrc_lyrics("Song", "Artist")
        self.assertEqual(lyrics, "[00:01.00]Hello")

    def test_skips_lookup_without_a_track_title(self):
        with patch("app.urllib.request.urlopen") as open_url:
            self.assertEqual(fetch_lrc_lyrics("未知标题", "Artist"), "")
        open_url.assert_not_called()


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
                 patch("mutagen.id3.ID3.save") as save, patch("app.fetch_lrc_lyrics", return_value=""):
                result = process_and_export_media(
                    source, {"title": "Song", "artist": "Artist"}, cover, "MP3", output
                )

            self.assertEqual(result.read_bytes(), b"mp3-data")
            self.assertFalse(source.exists())
            save.assert_called_once()


if __name__ == "__main__":
    unittest.main()

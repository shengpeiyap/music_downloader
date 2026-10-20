import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).parents[2] / "main" / "python" / "musicdesk_downloader.py"
SPEC = importlib.util.spec_from_file_location("musicdesk_downloader", MODULE_PATH)
musicdesk_downloader = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(musicdesk_downloader)


class DownloaderTests(unittest.TestCase):
    def test_rejects_unsupported_source_without_starting_ytdlp(self):
        with patch.object(musicdesk_downloader.yt_dlp, "YoutubeDL") as youtube_dl:
            with self.assertRaisesRegex(ValueError, "只支持"):
                musicdesk_downloader.download_audio("file:///private/file.mp3", "unused")
        youtube_dl.assert_not_called()

    def test_extracts_first_search_result_metadata_without_downloading(self):
        class FakeYoutubeDL:
            def __init__(self, options):
                self.options = options

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def extract_info(self, source, download):
                self.request = (source, download)
                return {"entries": [None, {
                    "title": "Track", "artist": "Artist", "webpage_url": "https://example.test/track",
                    "thumbnail": "https://example.test/cover.jpg", "duration": 123,
                }]}

        with patch.object(musicdesk_downloader.yt_dlp, "YoutubeDL", FakeYoutubeDL):
            result = json.loads(musicdesk_downloader.extract_metadata("ytsearch1:Artist Track"))

        self.assertEqual(result["title"], "Track")
        self.assertEqual(result["artist"], "Artist")
        self.assertEqual(result["url"], "https://example.test/track")
        self.assertEqual(result["duration"], 123)

    def test_search_metadata_overrides_source_fields_for_download_tags(self):
        info, cover = musicdesk_downloader._combine_metadata(
            {"title": "YouTube title", "artist": "Channel", "thumbnail": "https://example.test/source.jpg"},
            json.dumps({"title": "Catalog title", "artist": "Catalog artist", "album": "Catalog album", "albumartist": "Album artist", "year": "2021", "lyrics": "[00:01.00]line", "cover": "data:image/jpeg;base64,/9j/"}),
        )
        self.assertEqual(info["title"], "Catalog title")
        self.assertEqual(info["artist"], "Catalog artist")
        self.assertEqual(info["album"], "Catalog album")
        self.assertEqual(info["album_artist"], "Album artist")
        self.assertEqual(info["release_year"], "2021")
        self.assertEqual(info["lyrics"], "[00:01.00]line")
        self.assertEqual(cover, "data:image/jpeg;base64,/9j/")

    def test_writes_available_tags_to_mutagen_comment_container(self):
        class FakeAudio:
            def __init__(self):
                self.tags = {}
                self.saved = False

            def save(self):
                self.saved = True

        audio = FakeAudio()
        with patch.object(musicdesk_downloader.mutagen, "File", return_value=audio):
            result = musicdesk_downloader._write_metadata(Path("sample.ogg"), {
                "title": "Sample", "artist": "Artist", "album": "Album", "release_date": "20240615",
            }, None)

        self.assertTrue(result)
        self.assertEqual(audio.tags["title"], ["Sample"])
        self.assertEqual(audio.tags["artist"], ["Artist"])
        self.assertEqual(audio.tags["album"], ["Album"])
        self.assertEqual(audio.tags["date"], ["2024"])
        self.assertTrue(audio.saved)

    def test_download_embeds_tags_and_thumbnail_status_in_result(self):
        with tempfile.TemporaryDirectory() as directory:
            audio_file = Path(directory) / "sample.m4a"

            class FakeYoutubeDL:
                def __init__(self, options):
                    self.options = options

                def __enter__(self):
                    return self

                def __exit__(self, *_args):
                    return False

                def extract_info(self, source, download):
                    audio_file.write_bytes(b"audio")
                    return {
                        "title": "Sample / Track", "artist": "Artist", "thumbnail": "https://example.test/cover.jpg",
                        "requested_downloads": [{"filepath": str(audio_file)}],
                    }

                @staticmethod
                def prepare_filename(_info):
                    return str(audio_file)

            with patch.object(musicdesk_downloader.yt_dlp, "YoutubeDL", FakeYoutubeDL), \
                 patch.object(musicdesk_downloader, "_download_thumbnail", return_value=(b"cover", "image/jpeg", Path("cover.jpg"))) as thumbnail, \
                 patch.object(musicdesk_downloader, "_write_metadata", return_value=True) as write_metadata:
                result = json.loads(musicdesk_downloader.download_audio_with_metadata("https://example.test/song", directory, json.dumps({"title": "Catalog Track", "artist": "Catalog Artist"})))

            self.assertEqual(result["path"], str(audio_file))
            self.assertEqual(result["title"], "Catalog Track")
            self.assertTrue(result["metadata_embedded"])
            self.assertTrue(result["cover_embedded"])
            thumbnail.assert_called_once()
            write_metadata.assert_called_once()
            self.assertEqual(write_metadata.call_args.args[1]["artist"], "Catalog Artist")

    def test_returns_untagged_file_when_container_is_not_supported(self):
        with tempfile.TemporaryDirectory() as directory:
            audio_file = Path(directory) / "sample.webm"
            audio_file.write_bytes(b"audio")
            with patch.object(musicdesk_downloader.mutagen, "File", return_value=None):
                result = musicdesk_downloader._write_metadata(audio_file, {"title": "Sample"}, None)
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()

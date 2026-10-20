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

    def test_downloads_one_result_and_returns_file_metadata(self):
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
                    self.request = (source, download)
                    audio_file.write_bytes(b"audio")
                    return {"title": "Sample / Track", "requested_downloads": [{"filepath": str(audio_file)}]}

                @staticmethod
                def prepare_filename(_info):
                    return str(audio_file)

            with patch.object(musicdesk_downloader.yt_dlp, "YoutubeDL", FakeYoutubeDL):
                result = json.loads(musicdesk_downloader.download_audio("https://example.test/song", directory))

            self.assertEqual(result["path"], str(audio_file))
            self.assertEqual(result["title"], "Sample _ Track")
            self.assertEqual(audio_file.read_bytes(), b"audio")


if __name__ == "__main__":
    unittest.main()

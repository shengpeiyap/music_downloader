import importlib.util
import json
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from musicdesk_core.metadata import build_musicbrainz_search_query, split_artist_title


MODULE_PATH = Path(__file__).parents[2] / "main" / "python" / "musicdesk_downloader.py"
sys.path.insert(0, str(Path(__file__).parents[5]))
SPEC = importlib.util.spec_from_file_location("musicdesk_downloader", MODULE_PATH)
musicdesk_downloader = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(musicdesk_downloader)


class DownloaderTests(unittest.TestCase):
    def test_parses_lrc_timestamps_for_id3_synchronised_lyrics(self):
        parsed = musicdesk_downloader._parse_lrc_timestamps(
            "[00:02.5]later\n[00:01.23][00:03.00]repeat\n[00:04.00]<00:04.10>word<00:04.50>by\nuntimed"
        )
        self.assertEqual(parsed, [("repeat", 1230), ("later", 2500), ("repeat", 3000), ("word", 4100), ("by", 4500)])

    def test_lrc_parser_skips_timestamp_only_lines_and_plain_lyrics(self):
        self.assertEqual(
            musicdesk_downloader._parse_lrc_timestamps("[00:00.00]\nplain lyric"), []
        )

    def test_parsed_lrc_can_be_serialized_as_id3_sylt(self):
        from mutagen.id3 import ID3, SYLT

        frame = SYLT(
            encoding=3, lang="eng", format=2, type=1, desc="",
            text=musicdesk_downloader._parse_lrc_timestamps("[00:01.25]line"),
        )
        tags = ID3()
        tags.add(frame)
        self.assertEqual(tags.getall("SYLT")[0].text, [("line", 1250)])

    def test_wav_tags_and_lyrics_are_preserved_by_android_packager(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "track.wav"
            with wave.open(str(source), "wb") as audio:
                audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(8000)
                audio.writeframes(b"\x00\x00" * 800)
            tagged = musicdesk_downloader._write_metadata(source, {
                "title": "Song", "artist": "Artist", "track_number": "3/12", "genre": "J-pop",
                "lyrics": "[00:01.25]line",
            }, None)
            self.assertTrue(tagged)
            from mutagen.wave import WAVE
            tags = WAVE(source).tags
            self.assertEqual(tags.getall("TIT2")[0].text, ["Song"])
            self.assertEqual(tags.getall("TRCK")[0].text, ["3/12"])
            self.assertEqual(tags.getall("USLT")[0].text, "[00:01.25]line")

    def test_packages_local_audio_without_reencoding_and_writes_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "track.mp3"
            output = Path(directory) / "packaged.mp3"
            source.write_bytes(b"source audio bytes")
            with patch.object(musicdesk_downloader, "_write_metadata", return_value=True) as write_tags:
                result = musicdesk_downloader.package_audio_file(
                    str(source), str(output), json.dumps({"title": "New title"})
                )
            self.assertEqual(result, str(output))
            self.assertEqual(output.read_bytes(), source.read_bytes())
            self.assertEqual(write_tags.call_args.args[1], {"title": "New title"})

    def test_package_accepts_the_metadata_keys_sent_by_the_android_page(self):
        page_metadata = {
            "title": "Song", "artist": "Artist", "album": "Album", "album_artist": "Album artist",
            "release_year": "2024", "track_num": "3/12", "disc_num": "1/2", "genre": "J-pop",
            "composer": "Composer", "lyrics_format": "srt", "lyrics": "1\n00:00:02,120 --> 00:00:03,000\nLine",
        }
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "track.wav"
            output = Path(directory) / "packaged.wav"
            with wave.open(str(source), "wb") as audio:
                audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(8000)
                audio.writeframes(b"\x00\x00" * 800)
            musicdesk_downloader.package_audio_file(str(source), str(output), json.dumps(page_metadata))
            from mutagen.wave import WAVE
            tags = WAVE(output).tags
            self.assertEqual(tags.getall("TRCK")[0].text, ["3/12"])
            self.assertEqual(tags.getall("TPOS")[0].text, ["1/2"])
            self.assertEqual(tags.getall("TCON")[0].text, ["J-pop"])
            self.assertEqual(tags.getall("TCOM")[0].text, ["Composer"])
            self.assertEqual(tags.getall("TPE2")[0].text, ["Album artist"])
            self.assertEqual(str(tags.getall("TDRC")[0].text[0]), "2024")
            self.assertEqual(tags.getall("USLT")[0].text, "[00:02.12]Line")

    def test_package_rejects_unknown_lyrics_format_without_leaving_output(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "track.mp3"
            output = Path(directory) / "packaged.mp3"
            source.write_bytes(b"source audio bytes")
            with self.assertRaisesRegex(ValueError, "不支持的歌词格式"):
                musicdesk_downloader.package_audio_file(
                    str(source), str(output), json.dumps({"lyrics": "x", "lyrics_format": "bogus"})
                )
            self.assertFalse(output.exists())

    def test_package_refuses_empty_source(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "empty.mp3"
            source.touch()
            with self.assertRaisesRegex(ValueError, "为空"):
                musicdesk_downloader.package_audio_file(str(source), str(Path(directory) / "out.mp3"), "{}")

    def test_reads_local_tags_for_android_custom_form(self):
        class FakeAudio(dict):
            pass

        with patch.object(musicdesk_downloader.mutagen, "File", return_value=FakeAudio({
            "title": ["Song"], "artist": ["Artist"], "album": ["Album"],
            "albumartist": ["Album Artist"], "date": ["2024-09-01"], "lyrics": ["[00:01.00]line"],
        })):
            result = json.loads(musicdesk_downloader.read_local_audio_tags("unused.mp3"))
        self.assertEqual(result["title"], "Song")
        self.assertEqual(result["albumartist"], "Album Artist")
        self.assertEqual(result["year"], "2024-09-01")
        self.assertEqual(result["lyrics"], "[00:01.00]line")

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

    def test_searches_musicbrainz_and_returns_album_year_and_cover(self):
        response = {"recordings": [{
            "title": "Song", "score": 100,
            "artist-credit": [{"name": "Artist", "artist": {"name": "Artist"}}],
            "releases": [{
                "id": "release-id", "title": "Album", "date": "2020-03-12",
                "release-group": {"primary-type": "Album", "secondary-types": []},
            }],
        }]}
        with patch.object(musicdesk_downloader, "_musicbrainz_json", return_value=response) as request:
            result = json.loads(musicdesk_downloader.search_musicbrainz("Artist - Song"))

        self.assertEqual(result["title"], "Song")
        self.assertEqual(result["artist"], "Artist")
        self.assertEqual(result["album"], "Album")
        self.assertEqual(result["year"], "2020")
        self.assertEqual(result["cover"], "https://coverartarchive.org/release/release-id/front-500")
        self.assertIn("fmt=json", request.call_args.args[0])
        query = parse_qs(urlsplit(request.call_args.args[0]).query)["query"][0]
        self.assertEqual(query, build_musicbrainz_search_query("Song", "Artist"))

    def test_android_and_shared_metadata_parsers_use_the_same_artist_title_split(self):
        self.assertEqual(split_artist_title(" Artist — Song "), ("Artist", "Song"))
        self.assertEqual(musicdesk_downloader._split_metadata_query(" Artist — Song "), ("Artist", "Song"))

    def test_lyrics_lookup_uses_exact_then_search_fallback(self):
        with patch.object(musicdesk_downloader, "_json_request", side_effect=[
            RuntimeError("exact match unavailable"),
            [{"trackName": "Song", "artistName": "Artist", "syncedLyrics": "[00:01.00]line", "plainLyrics": "line"}],
        ]) as request:
            result = json.loads(musicdesk_downloader.lookup_lyrics("Song", "Artist"))
        self.assertEqual(result["lyrics"], "[00:01.00]line")
        self.assertEqual(result["synced_lyrics"], "[00:01.00]line")
        self.assertEqual(result["provider"], "LRCLIB")
        self.assertEqual(request.call_count, 2)
        self.assertIn("/api/get?", request.call_args_list[0].args[0])
        self.assertIn("/api/search?", request.call_args_list[1].args[0])

    def test_lyrics_lookup_retries_search_by_title_when_artist_query_misses(self):
        with patch.object(musicdesk_downloader, "_json_request", side_effect=[
            RuntimeError("exact match unavailable"),
            [],
            [{"trackName": "Song", "artistName": "Different Artist", "syncedLyrics": "[00:01.00]line"}],
        ]) as request:
            result = json.loads(musicdesk_downloader.lookup_lyrics("Song", "Artist"))
        self.assertEqual(result["lyrics"], "[00:01.00]line")
        self.assertEqual(request.call_count, 3)
        self.assertIn("q=Artist+Song", request.call_args_list[1].args[0])
        self.assertIn("q=Song", request.call_args_list[2].args[0])

    def test_lyrics_lookup_extracts_song_from_youtube_music_video_title(self):
        with patch.object(musicdesk_downloader, "_json_request", side_effect=[
            RuntimeError("full video title did not match"),
            {"trackName": "アンコール", "syncedLyrics": "[00:01.00]line"},
        ]) as request:
            result = json.loads(musicdesk_downloader.lookup_lyrics(
                "YOASOBI 「アンコール」 Official Music Video", "YOASOBI, Echoes"
            ))
        self.assertEqual(result["lyrics"], "[00:01.00]line")
        self.assertIn("track_name=%E3%82%A2%E3%83%B3%E3%82%B3%E3%83%BC%E3%83%AB", request.call_args_list[1].args[0])
        self.assertIn("artist_name=YOASOBI", request.call_args_list[1].args[0])

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

    def test_custom_package_metadata_includes_advanced_fields_and_normalizes_srt(self):
        metadata, _cover = musicdesk_downloader._combine_metadata({}, json.dumps({
            "track_num": "3/12", "disc_num": "1", "genre": "J-pop", "composer": "Composer",
            "lyrics_format": "srt", "lyrics": "1\n00:00:02,120 --> 00:00:03,000\nLine",
        }))
        self.assertEqual(metadata["track_number"], "3/12")
        self.assertEqual(metadata["disc_number"], "1")
        self.assertEqual(metadata["genre"], "J-pop")
        self.assertEqual(metadata["composer"], "Composer")
        self.assertEqual(metadata["lyrics"], "[00:02.12]Line")

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
            captured_options = {}

            class FakeYoutubeDL:
                def __init__(self, options):
                    self.options = options
                    captured_options.update(options)

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
            self.assertTrue(captured_options["writethumbnail"])
            self.assertEqual(result["cover_path"], "cover.jpg")
            self.assertEqual(result["tag_metadata"]["artist"], "Catalog Artist")
            self.assertEqual(result["tag_metadata"]["title"], "Catalog Track")
            thumbnail.assert_called_once()
            write_metadata.assert_called_once()
            self.assertEqual(write_metadata.call_args.args[1]["artist"], "Catalog Artist")

    def test_detects_webp_thumbnail_for_android_cover_conversion(self):
        image = b"RIFF" + (4).to_bytes(4, "little") + b"WEBP"
        self.assertEqual(musicdesk_downloader._image_mime(image), "image/webp")

    def test_download_falls_back_to_ytdlp_thumbnail_when_catalog_cover_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            audio_file = Path(directory) / "sample.m4a"

            class FakeYoutubeDL:
                def __init__(self, options): pass
                def __enter__(self): return self
                def __exit__(self, *_args): return False
                def extract_info(self, _source, download):
                    audio_file.write_bytes(b"audio")
                    return {"title": "Sample", "thumbnail": "https://example.test/ytdlp.jpg",
                            "requested_downloads": [{"filepath": str(audio_file)}]}
                @staticmethod
                def prepare_filename(_info): return str(audio_file)

            valid_cover = (b"thumbnail", "image/jpeg", Path("cover.jpg"))
            with patch.object(musicdesk_downloader.yt_dlp, "YoutubeDL", FakeYoutubeDL), \
                 patch.object(musicdesk_downloader, "_metadata_cover", side_effect=[None, valid_cover]) as cover_lookup, \
                 patch.object(musicdesk_downloader, "_write_metadata", return_value=True) as write_metadata:
                result = json.loads(musicdesk_downloader.download_audio_with_metadata(
                    "https://example.test/song", directory,
                    json.dumps({"cover": "https://coverartarchive.org/release/missing/front-500"}),
                ))

            self.assertTrue(result["cover_embedded"])
            self.assertEqual(cover_lookup.call_args_list[1].args[0], "https://example.test/ytdlp.jpg")
            self.assertEqual(write_metadata.call_args.args[2], valid_cover)

    def test_returns_untagged_file_when_container_is_not_supported(self):
        with tempfile.TemporaryDirectory() as directory:
            audio_file = Path(directory) / "sample.webm"
            audio_file.write_bytes(b"audio")
            with patch.object(musicdesk_downloader.mutagen, "File", return_value=None):
                result = musicdesk_downloader._write_metadata(audio_file, {"title": "Sample"}, None)
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()

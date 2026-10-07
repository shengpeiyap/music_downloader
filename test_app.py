import unittest
import sys
import io
import wave
import http.client
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from PIL import Image

from app import MUSICDESK_API_CAPABILITIES, MUSICDESK_API_VERSION, acquire_custom_audio_source, build_download_query, create_musicdesk_server, crop_yt_padding_smart, fetch_lrc_lyrics, fetch_media_stream, fetch_spotify_embed_html, fetch_spotify_oembed, find_ffmpeg, is_api_authorized, is_loopback_address, load_music_tag, lookup_metadata, lookup_metadata_by_keyword, make_tag_export_filename, multipart_fields, multipart_text, parse_metadata_search_query, parse_share_url, process_and_export_media, read_music_metadata
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
            (package / "_internal" / "default_song_img.png").write_bytes(b"placeholder")
            archive_path = create_portable_archive(package, root / "package.zip")

            import zipfile
            with zipfile.ZipFile(archive_path) as archive:
                self.assertEqual(set(archive.namelist()), {
                    "MusicDesk.exe", "_internal/music_tag.py", "_internal/default_song_img.png"
                })
                self.assertIsNone(archive.testzip())


class LocalTagMetadataTests(unittest.TestCase):
    def test_lyrics_reader_sends_only_fields_needed_for_lookup(self):
        page = (Path(__file__).parent / "index.html").read_text(encoding="utf-8")
        self.assertIn(
            "JSON.stringify({title: currentMetadata.title, artist: currentMetadata.artist})",
            page,
        )

    def test_default_cover_is_display_only_and_never_used_as_embedded_cover(self):
        page = (Path(__file__).parent / "index.html").read_text(encoding="utf-8")
        self.assertIn("const DEFAULT_COVER = 'default_song_img.png'", page)
        self.assertIn('img[src$="default_song_img.png"]{background:#f3f6f1;padding:12px}', page)
        self.assertIn("$('customCoverPreview').dataset.embeddedCover = d.cover || ''", page)
        self.assertTrue((Path(__file__).parent / "default_song_img.png").is_file())

    def test_custom_packaging_and_player_have_drag_drop_zones(self):
        page = (Path(__file__).parent / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="customAudioDrop"', page)
        self.assertIn('id="playlistDropZone"', page)
        self.assertIn('function setupDropZone(zone, onDrop)', page)
        self.assertIn('async function getDroppedFiles(dataTransfer)', page)
        self.assertIn('function addLocalAudioFiles(inputFiles, replace)', page)

    def test_local_player_has_removal_and_custom_transport_controls(self):
        page = (Path(__file__).parent / "index.html").read_text(encoding="utf-8")
        for control_id in (
            "previousTrackBtn", "togglePlaybackBtn", "nextTrackBtn", "playbackSeek",
            "currentTimeLabel", "durationLabel",
        ):
            self.assertIn(f'id="{control_id}"', page)
        self.assertIn("function removeLocalTrack(idx)", page)
        self.assertIn("URL.revokeObjectURL(removed.objectUrl)", page)

    def test_android_webview_mvp_has_mobile_audio_picker_and_bundled_web_assets(self):
        root = Path(__file__).parent
        page = (root / "index.html").read_text(encoding="utf-8")
        activity = (root / "android/app/src/main/java/com/musicdesk/android/MainActivity.java").read_text(encoding="utf-8")
        gradle = (root / "android/app/build.gradle.kts").read_text(encoding="utf-8")
        self.assertIn('id="audioFilesInput"', page)
        self.assertIn("MusicDeskAndroid", page)
        self.assertIn("if (!window.jsmediatags)", page)
        self.assertIn("onShowFileChooser", activity)
        self.assertIn('webView.loadUrl("file:///android_asset/index.html")', activity)
        self.assertIn("compileSdk = 36", gradle)
        self.assertEqual((root / "android/app/src/main/assets/index.html").read_bytes(), (root / "index.html").read_bytes())
        self.assertEqual((root / "android/app/src/main/assets/default_song_img.png").read_bytes(), (root / "default_song_img.png").read_bytes())
        self.assertIn("ACTION_OPEN_DOCUMENT_TREE", activity)
        self.assertIn("buildChildDocumentsUriUsingTree", activity)
        self.assertIn('webView.addJavascriptInterface(new AndroidMusicBridge(), "AndroidMusic")', activity)
        self.assertIn('webView.loadUrl("file:///android_asset/index.html")', activity)
        self.assertIn('window.onAndroidFolderPicked', page)
        self.assertIn('AndroidMusic.loadAudio(track.contentUri, idx)', page)
        self.assertIn('id="androidLibraryTab"', page)
        self.assertIn('id="androidNowPlayingTab"', page)
        self.assertIn('id="playlistCard"', page)
        self.assertIn('id="playerMainCard"', page)
        self.assertIn('body.android-app .nav-tabs', page)
        self.assertIn('id="libraryFilterTabs"', page)
        self.assertIn('id="playerLyricsViewBtn"', page)
        self.assertIn('id="androidMiniPlayer"', page)
        self.assertIn('function renderQueue()', page)
        self.assertIn('private String readArtwork(Uri source)', activity)
        self.assertNotIn('track.put("cover"', activity)

    def test_android_player_supports_repeat_shuffle_and_large_library_views(self):
        root = Path(__file__).parent
        page = (root / "index.html").read_text(encoding="utf-8")
        activity = (root / "android/app/src/main/java/com/musicdesk/android/MainActivity.java").read_text(encoding="utf-8")
        for mode in ("sequential", "repeat-one", "repeat-all", "shuffle"):
            self.assertIn(mode, page)
        self.assertIn("window.onAndroidAudioReady = (idx, contentUri, fileUri, error, artworkData)", page)
        self.assertIn("scanDocumentTree(tree, id, results, depth + 1, childPath)", activity)
        self.assertIn("while (Math.max(bounds.outWidth / sample, bounds.outHeight / sample) > 512)", activity)
        self.assertIn("int chunkSize = 100", activity)
        self.assertIn("onAndroidFolderPicked(", activity)
        self.assertIn("isFinal = true", page)
        self.assertIn("rememberFolder(tree)", activity)
        self.assertIn("preferences.getStringSet(PREF_SAVED_FOLDERS", activity)
        self.assertIn("AndroidMusic.restoreFolders()", page)
        self.assertIn("scanFolderAsync(Uri.parse(value))", activity)
        self.assertIn("id=\"queueDragHandle\"", page)
        self.assertIn("queueDragHandle.addEventListener('pointermove'", page)
        self.assertIn("AndroidMusic.setQueueOpen(false)", page)
        self.assertIn("queueOpen && webView != null", activity)
        self.assertIn("body.android-app #tab-local{flex:1", page)
        self.assertIn("data-category=\"artists\"", page)
        self.assertIn("data-category=\"albums\"", page)
        self.assertIn("data-category=\"folders\"", page)
        self.assertIn("data-category=\"favorites\"", page)

    def test_android_library_keeps_controls_fixed_and_restores_filtered_playback_queue(self):
        page = (Path(__file__).parent / "index.html").read_text(encoding="utf-8")
        self.assertIn("body.android-app{position:fixed", page)
        self.assertIn("body.android-app #localTrackList{flex:1;min-height:0", page)
        self.assertIn("let playbackQueue = []", page)
        self.assertIn("displayedTrackIndices = filtered.map", page)
        self.assertIn("function startPlayAll(mode)", page)
        self.assertIn('id="playAllSequentialBtn"', page)
        self.assertIn('id="playAllShuffleBtn"', page)
        self.assertIn("musicdesk-playback-state", page)
        self.assertIn("function tryRestoreSavedPlayback()", page)
        self.assertIn("window.pendingAudioResume = saved", page)
        self.assertIn("player.currentTime = Math.min(resume.position", page)
        self.assertIn("$('queueSheet').addEventListener('touchmove'", page)
        self.assertIn("body.android-app .player-main-card{height:100%;min-height:0", page)
        self.assertIn("document.querySelectorAll('.tab-btn')[0].textContent = '在线解析'", page)
        self.assertIn("body.android-app .tab-content:not(.active){display:none!important}", page)
        self.assertIn("function requestMusicDeskApi(path, options)", page)
        self.assertIn('id="androidApiConnectCard"', page)
        self.assertIn('id="apiServerUrl"', page)
        self.assertIn('id="apiPairingToken"', page)
        self.assertIn("Authorization: `Bearer ${androidApiConfig.token}`", page)
        self.assertIn("let androidApiConnected = false", page)
        self.assertIn("function updateAndroidApiGates()", page)
        self.assertIn("function testAndroidApiConnection(config, showProgress = true)", page)
        self.assertIn("const REQUIRED_ANDROID_API_VERSION = 1", page)
        self.assertIn("result.api_version !== REQUIRED_ANDROID_API_VERSION", page)
        self.assertIn("REQUIRED_ANDROID_API_CAPABILITIES.every", page)
        self.assertIn("此功能已锁定。请先连接电脑上的 MusicDesk 服务", page)
        self.assertIn("testAndroidApiConnection(androidApiConfig, false)", page)
        self.assertIn("async function saveApiResponse(response, fallbackName)", page)
        self.assertIn("AndroidMusic.writeDownloadChunk", page)
        manifest = (Path(__file__).parent / "android/app/src/main/AndroidManifest.xml").read_text(encoding="utf-8")
        self.assertIn('android:usesCleartextTraffic="true"', manifest)

    def test_plain_lyrics_are_rendered_without_timing_in_online_and_local_readers(self):
        page = (Path(__file__).parent / "index.html").read_text(encoding="utf-8")
        self.assertIn("function renderPlainLyrics(container, lyricText, emptyMessage)", page)
        self.assertIn("renderPlainLyrics(container, lrcText, '未检索到歌词')", page)
        self.assertIn("renderPlainLyrics(container, lrcText, '暂无内嵌歌词')", page)
        self.assertIn("class=\"plain-lyric-line\"", page)

    def test_keyword_lookup_result_becomes_youtube_search_for_download(self):
        self.assertEqual(
            build_download_query("", "月明かり", "ヨルシカ", keyword_search=True),
            "musicdesk-query:ヨルシカ - 月明かり",
        )
        self.assertEqual(
            build_download_query("https://open.spotify.com/track/id", "Track", "Artist", keyword_search=True),
            "https://open.spotify.com/track/id",
        )

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
        self.assertEqual(
            make_tag_export_filename("Artist", "Track", "source.wav", "mp3", "Live"),
            "Artist - Track - Live.mp3",
        )

    def test_keyword_query_accepts_artist_title_or_title(self):
        self.assertEqual(parse_metadata_search_query("  ヨルシカ - 月明かり  "), ("ヨルシカ", "月明かり"))
        self.assertEqual(parse_metadata_search_query("月明かり"), ("未知艺人", "月明かり"))

    def test_keyword_search_uses_metadata_and_lyrics_sources(self):
        with patch("app.lookup_musicbrainz_metadata", return_value={
            "artist": "Artist", "album": "Album", "year": "2020", "cover_url": None
        }) as musicbrainz, patch("app.search_lrc_track", return_value=None), \
             patch("app.fetch_lrc_lyrics", return_value="[00:01.00]Lyric") as lyrics:
            result = lookup_metadata_by_keyword("Artist - Track")

        musicbrainz.assert_called_once_with("Track", "Artist")
        lyrics.assert_called_once_with("Track", "Artist")
        self.assertEqual(result["title"], "Track")
        self.assertEqual(result["album"], "Album")
        self.assertEqual(result["lyrics"], "[00:01.00]Lyric")

    def test_keyword_lookup_can_use_lyrics_database_when_musicbrainz_has_no_release(self):
        lyric_track = {
            "trackName": "Elma", "artistName": "Yorushika", "albumName": "Elma",
            "syncedLyrics": "[00:01.00]Lyric", "plainLyrics": "",
        }
        with patch("app.lookup_musicbrainz_metadata", return_value={
            "artist": "未知艺人", "album": "", "year": "", "cover_url": None
        }), patch("app.search_lrc_track", return_value=lyric_track):
            result = lookup_metadata_by_keyword("Elma")

        self.assertEqual(result["artist"], "Yorushika")
        self.assertEqual(result["album"], "Elma")
        self.assertEqual(result["lyrics"], "[00:01.00]Lyric")

    def test_custom_export_can_fetch_source_when_no_local_audio_was_selected(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "downloaded.mp3"
            source.write_bytes(b"audio")
            with patch("app.fetch_media_stream", return_value=(source, "")) as fetch:
                result, filename = acquire_custom_audio_source(
                    None, "", "Track", "Artist", "spotdl", Path(directory)
                )

        fetch.assert_called_once_with("musicdesk-query:Artist - Track", "Track", "Artist", "spotdl", Path(directory))
        self.assertEqual(result, source)
        self.assertEqual(filename, "Artist - Track.mp3")

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

    def test_lyrics_search_fallback_does_not_search_unknown_artist(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b'[{"trackName":"Elma","artistName":"Yorushika","syncedLyrics":"[00:01.00]Hello"}]'

        def mock_open(request, **kwargs):
            if "/api/get?" in request.full_url:
                raise OSError("no exact result")
            self.assertIn("q=Elma", request.full_url)
            self.assertNotIn("%E6%9C%AA%E7%9F%A5", request.full_url)
            return response

        with patch("app.urllib.request.urlopen", side_effect=mock_open), redirect_stdout(StringIO()):
            self.assertEqual(fetch_lrc_lyrics("Elma", "未知艺人"), "[00:01.00]Hello")

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

    def test_keyword_download_uses_the_selected_search_engine(self):
        with tempfile.TemporaryDirectory() as directory:
            downloaded = Path(directory) / "result.mp3"
            downloaded.write_bytes(b"audio")
            with patch("app.fetch_with_spotdl", return_value=(downloaded, "Artist - Track")) as spotdl, \
                 patch("app.fetch_with_ytdlp") as ytdlp:
                result, source_url = fetch_media_stream(
                    "musicdesk-query:Artist - Track", "Track", "Artist", "spotdl", directory
                )

        spotdl.assert_called_once()
        ytdlp.assert_not_called()
        self.assertEqual(result, downloaded)
        self.assertEqual(source_url, "")


class LanApiTests(unittest.TestCase):
    def test_non_lan_mode_rejects_wildcard_bind(self):
        from app import main
        with self.assertRaises(SystemExit) as result:
            main(["--host", "0.0.0.0"])
        self.assertEqual(result.exception.code, 2)

    def test_bearer_token_comparison_and_local_mode(self):
        self.assertTrue(is_api_authorized("", ""))
        self.assertTrue(is_api_authorized("Bearer secret", "secret"))
        self.assertFalse(is_api_authorized("Bearer wrong", "secret"))
        self.assertFalse(is_api_authorized("", "secret"))

    def test_loopback_is_local_but_private_lan_ip_is_remote(self):
        self.assertTrue(is_loopback_address("127.0.0.1"))
        self.assertTrue(is_loopback_address("::1"))
        self.assertFalse(is_loopback_address("192.168.1.7"))

    def test_lan_server_auth_cors_and_api_only_surface(self):
        server = create_musicdesk_server("127.0.0.1", 0, "pairing-secret")
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
            connection.request("GET", "/")
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            response.read()

            connection.request("GET", "/api/status")
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(response.getheader("Access-Control-Allow-Origin"), "*")
            response.read()

            connection.request("GET", "/api/status", headers={"Authorization": "Bearer pairing-secret"})
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            status = __import__("json").loads(response.read())
            self.assertTrue(status["ok"])
            self.assertEqual(status["api_version"], MUSICDESK_API_VERSION)
            self.assertEqual(set(status["capabilities"]), set(MUSICDESK_API_CAPABILITIES))

            connection.request("OPTIONS", "/api/download", headers={"Origin": "null"})
            response = connection.getresponse()
            self.assertEqual(response.status, 204)
            self.assertIn("Authorization", response.getheader("Access-Control-Allow-Headers"))

            connection.close()
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=3)


class SmartPaddingCropTests(unittest.TestCase):
    def test_crops_uniform_padding_from_all_sides(self):
        canvas = Image.new("RGB", (200, 200), (240, 240, 240))
        content = Image.new("RGB", (100, 100), (20, 80, 160))
        canvas.paste(content, (50, 50))
        buf = io.BytesIO()
        canvas.save(buf, format="JPEG")

        cropped = crop_yt_padding_smart(buf.getvalue())
        result = Image.open(io.BytesIO(cropped)).convert("RGB")
        rw, rh = result.size
        corner = result.getpixel((min(5, rw - 1), min(5, rh - 1)))
        center = result.getpixel((rw // 2, rh // 2))
        self.assertLess(abs(corner[0] - 20), 40)
        self.assertLess(abs(center[0] - 20), 40)
        self.assertGreaterEqual(rw, 50)
        self.assertGreaterEqual(rh, 50)
        self.assertLessEqual(rw, 150)
        self.assertLessEqual(rh, 150)

    def test_returns_original_when_cropped_region_would_be_too_small(self):
        plain = Image.new("RGB", (120, 120), (240, 240, 240))
        tiny = Image.new("RGB", (10, 10), (20, 20, 20))
        plain.paste(tiny, (55, 55))
        buf = io.BytesIO()
        plain.save(buf, format="JPEG")

        cropped = crop_yt_padding_smart(buf.getvalue())
        result = Image.open(io.BytesIO(cropped)).convert("RGB")
        self.assertEqual(result.size, (120, 120))

    def test_handles_empty_bytes_gracefully(self):
        self.assertEqual(crop_yt_padding_smart(b""), b"")


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

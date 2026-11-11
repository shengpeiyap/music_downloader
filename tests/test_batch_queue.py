import http.client, json, sys, threading, time, unittest, zipfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from musicdesk_core import batch


def track(i, title=None):
    return {"id": f"abcdefghi{i:02d}"[:11], "title": title or f"Song {i}", "artist": "A", "duration": 100, "thumbnail": ""}


def wait(job, timeout=5):
    end = time.time() + timeout
    while job.state in ("queued", "running") and time.time() < end:
        time.sleep(0.02)


class BatchTests(unittest.TestCase):
    def test_parse_playlist_url(self):
        ok = batch.parse_playlist_url("https://music.youtube.com/playlist?list=PLabcdefghijk123")
        self.assertEqual(ok["url"], "https://www.youtube.com/playlist?list=PLabcdefghijk123")
        for bad in ("http://youtube.com/playlist?list=PLabcdefghijk123", "https://evil.com/playlist?list=PLabcdefghijk123",
                    "https://www.youtube.com/watch?v=abcdefghijk&list=PLabcdefghijk123", "https://www.youtube.com/playlist?list=x"):
            with self.assertRaises(ValueError):
                batch.parse_playlist_url(bad)

    def test_clean_entry(self):
        e = batch.clean_playlist_entry({"id": "abcdefghijk", "title": "Foo - Bar", "uploader": "X - Topic"})
        self.assertEqual((e["artist"], e["title"]), ("Foo", "Bar"))
        self.assertIsNone(batch.clean_playlist_entry({"id": "bad", "title": "t"}))
        self.assertIsNone(batch.clean_playlist_entry({"id": "abcdefghijk", "title": "[Private video]"}))

    def test_queue_skips_failures_dedupes_names_and_zips(self):
        def process(t, opts, dest):
            if t["title"] == "Song 1":
                raise ValueError("boom")
            f = batch.unique_name(dest, "same.mp3")
            f.write_bytes(b"x")
            return f
        mgr = batch.BatchManager()
        job = mgr.start([track(0), track(1), track(2)], {}, process)
        wait(job)
        snap = job.snapshot()
        self.assertEqual(snap["state"], "done")
        self.assertEqual((snap["total"], snap["succeeded"]), (3, 2))
        self.assertEqual(len(snap["failed"]), 1)
        self.assertTrue(snap["ready"])
        with zipfile.ZipFile(job.zip_path) as z:
            self.assertEqual(sorted(z.namelist()), ["same (1).mp3", "same.mp3"])
        job.cleanup()

    def test_single_active_job_and_cancel(self):
        gate = threading.Event()
        def slow(t, o, d):
            gate.wait(2)
            f = d / f"{t['id']}.mp3"; f.write_bytes(b"x"); return f
        mgr = batch.BatchManager()
        job = mgr.start([track(0), track(1), track(2)], {}, slow)
        with self.assertRaises(RuntimeError):
            mgr.start([track(3)], {}, slow)
        self.assertTrue(mgr.cancel(job.id))
        gate.set()
        wait(job)
        self.assertEqual(job.state, "cancelled")
        self.assertLess(job.snapshot()["succeeded"], 3)
        job.cleanup()

    def test_limits(self):
        mgr = batch.BatchManager()
        with self.assertRaises(ValueError):
            mgr.start([], {}, lambda *a: None)
        with self.assertRaises(ValueError):
            mgr.start([track(0)] * (batch.MAX_BATCH_TRACKS + 1), {}, lambda *a: None)


class BatchEndpointTests(unittest.TestCase):
    def test_endpoints(self):
        import app
        server = app.create_musicdesk_server("127.0.0.1", 0) if hasattr(app, "create_musicdesk_server") else None
        self.assertIsNotNone(server)
        def fake(t, o, d):
            f = d / "a.mp3"; f.write_bytes(b"x"); return f
        orig_proc, orig_list = app.process_batch_track, app.list_playlist_entries
        app.process_batch_track = fake
        app.list_playlist_entries = lambda url: {"title": "PL", "entries": [track(0), track(1)]}
        worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
        try:
            c = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            def call(method, path, body=None):
                c.request(method, path, body=json.dumps(body) if body is not None else None, headers={"Content-Type": "application/json"})
                r = c.getresponse(); return r.status, r.read()
            s, b = call("POST", "/api/playlist", {"url": "https://music.youtube.com/playlist?list=PLabcdefghijk123"})
            self.assertEqual(s, 200); self.assertEqual(len(json.loads(b)["entries"]), 2)
            s, _ = call("POST", "/api/batch", {"tracks": "nope"}); self.assertEqual(s, 400)
            s, b = call("POST", "/api/batch", {"tracks": [track(0), track(1)], "format": "mp3", "bitrate": "192"})
            self.assertEqual(s, 200); jid = json.loads(b)["job_id"]
            for _ in range(100):
                s, b = call("GET", f"/api/batch/{jid}")
                if json.loads(b)["state"] == "done": break
                time.sleep(0.05)
            self.assertEqual(json.loads(b)["succeeded"], 2)
            s, b = call("GET", f"/api/batch/{jid}/zip"); self.assertEqual(s, 200)
            self.assertTrue(b.startswith(b"PK"))
            s, _ = call("GET", "/api/batch/" + "0" * 32); self.assertEqual(s, 404)
        finally:
            app.process_batch_track, app.list_playlist_entries = orig_proc, orig_list
            server.shutdown(); server.server_close()


if __name__ == "__main__":
    unittest.main()

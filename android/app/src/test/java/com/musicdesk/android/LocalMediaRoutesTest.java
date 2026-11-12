package com.musicdesk.android;

import static org.junit.Assert.assertArrayEquals;
import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.nio.file.Files;
import org.junit.Test;

public class LocalMediaRoutesTest {
    @Test
    public void urlUsesTheCorsHostAndCachedFileName() {
        assertEquals("https://appassets.androidplatform.net/musicdesk-audio/abc-123.mp3",
                LocalMediaRoutes.urlFor(new File("/cache/musicdesk-audio/abc-123.mp3")));
    }

    @Test
    public void onlyTheMediaPathOnTheAssetHostIsIntercepted() {
        assertTrue(LocalMediaRoutes.matches("https", "appassets.androidplatform.net", "/musicdesk-audio/a.mp3"));
        assertFalse(LocalMediaRoutes.matches("http", "appassets.androidplatform.net", "/musicdesk-audio/a.mp3"));
        assertFalse(LocalMediaRoutes.matches("https", "example.com", "/musicdesk-audio/a.mp3"));
        assertFalse(LocalMediaRoutes.matches("https", "appassets.androidplatform.net", "/assets/index.html"));
    }

    @Test
    public void wholeFileWithoutRangeHeader() {
        assertArrayEquals(new long[]{0, 999}, LocalMediaRoutes.parseRange(null, 1000));
        assertArrayEquals(new long[]{0, 999}, LocalMediaRoutes.parseRange("", 1000));
    }

    @Test
    public void openEndedClosedAndSuffixRanges() {
        assertArrayEquals(new long[]{0, 999}, LocalMediaRoutes.parseRange("bytes=0-", 1000));
        assertArrayEquals(new long[]{500, 999}, LocalMediaRoutes.parseRange("bytes=500-", 1000));
        assertArrayEquals(new long[]{100, 199}, LocalMediaRoutes.parseRange("bytes=100-199", 1000));
        assertArrayEquals(new long[]{900, 999}, LocalMediaRoutes.parseRange("bytes=-100", 1000));
        assertArrayEquals(new long[]{0, 999}, LocalMediaRoutes.parseRange("bytes=-5000", 1000));
        assertArrayEquals(new long[]{990, 999}, LocalMediaRoutes.parseRange("bytes=990-5000", 1000));
    }

    @Test
    public void unsatisfiableOrMalformedRangesAreRejected() {
        assertNull(LocalMediaRoutes.parseRange("bytes=1000-", 1000));
        assertNull(LocalMediaRoutes.parseRange("bytes=200-100", 1000));
        assertNull(LocalMediaRoutes.parseRange("bytes=-0", 1000));
        assertNull(LocalMediaRoutes.parseRange("bytes=-", 1000));
        assertNull(LocalMediaRoutes.parseRange("bytes=0-10,20-30", 1000));
        assertNull(LocalMediaRoutes.parseRange("items=0-10", 1000));
    }

    @Test
    public void resolvesOnlyExistingFilesInsideTheCacheFolder() throws IOException {
        File folder = Files.createTempDirectory("musicdesk-audio").toFile();
        File track = new File(folder, "0f3c-uuid.mp3");
        try (FileOutputStream output = new FileOutputStream(track)) {
            output.write(new byte[]{1, 2, 3});
        }
        File outside = new File(folder.getParentFile(), "secret.mp3");
        assertEquals(track.getCanonicalFile(),
                LocalMediaRoutes.resolve(folder, "/musicdesk-audio/0f3c-uuid.mp3").getCanonicalFile());
        assertNull(LocalMediaRoutes.resolve(folder, "/musicdesk-audio/missing.mp3"));
        assertNull(LocalMediaRoutes.resolve(folder, "/musicdesk-audio/../secret.mp3"));
        assertNull(LocalMediaRoutes.resolve(folder, "/musicdesk-audio/..%2Fsecret.mp3"));
        assertNull(LocalMediaRoutes.resolve(folder, "/musicdesk-audio/sub/0f3c-uuid.mp3"));
        assertNull(LocalMediaRoutes.resolve(folder, "/other/0f3c-uuid.mp3"));
        assertFalse(outside.exists());
        track.delete();
        folder.delete();
    }

    @Test
    public void mimeTypesForPlayableFormats() {
        assertEquals("audio/mpeg", LocalMediaRoutes.mimeType("a.MP3"));
        assertEquals("audio/mp4", LocalMediaRoutes.mimeType("a.m4a"));
        assertEquals("audio/flac", LocalMediaRoutes.mimeType("a.flac"));
        assertEquals("audio/ogg", LocalMediaRoutes.mimeType("a.opus"));
        assertEquals("application/octet-stream", LocalMediaRoutes.mimeType("a.audio"));
    }
}

package com.musicdesk.android;

import java.io.File;
import java.io.IOException;
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Pure helpers for serving cached audio to the WebView over an https URL.
 *
 * The page is loaded from file://, and WebView treats file:// media as cross-origin, so Web Audio
 * (the equalizer) outputs silence for it. Serving the same cached file from a CORS-enabled https
 * URL lets the page process the audio. No Android types here, so this is unit-testable on the JVM.
 */
final class LocalMediaRoutes {
    static final String HOST = "appassets.androidplatform.net";
    static final String PATH_PREFIX = "/musicdesk-audio/";
    private static final Pattern SAFE_NAME = Pattern.compile("[A-Za-z0-9-]+\\.[A-Za-z0-9]{1,8}");
    private static final Pattern RANGE = Pattern.compile("^\\s*bytes\\s*=\\s*(\\d*)\\s*-\\s*(\\d*)\\s*$");

    private LocalMediaRoutes() { }

    static String urlFor(File cachedFile) {
        return "https://" + HOST + PATH_PREFIX + cachedFile.getName();
    }

    static boolean matches(String scheme, String host, String path) {
        return "https".equals(scheme) && HOST.equals(host) && path != null && path.startsWith(PATH_PREFIX);
    }

    /** The cached file a request path names, or null when the name is not one this app produced. */
    static File resolve(File folder, String path) throws IOException {
        if (path == null || !path.startsWith(PATH_PREFIX)) return null;
        String name = path.substring(PATH_PREFIX.length());
        if (!SAFE_NAME.matcher(name).matches()) return null;
        File file = new File(folder, name);
        if (!file.getCanonicalFile().getParentFile().equals(folder.getCanonicalFile())) return null;
        return file.isFile() ? file : null;
    }

    /**
     * Inclusive byte range {start, end} for a Range header, the whole file when there is no header,
     * or null when the range cannot be satisfied (the caller answers 416).
     */
    static long[] parseRange(String header, long length) {
        if (header == null || header.trim().isEmpty()) return new long[]{0, length - 1};
        Matcher match = RANGE.matcher(header);
        if (!match.matches() || length <= 0) return null;
        String first = match.group(1), last = match.group(2);
        long start, end;
        if (first.isEmpty()) {
            if (last.isEmpty()) return null;
            long suffix = Long.parseLong(last);
            if (suffix == 0) return null;
            start = Math.max(0, length - suffix);
            end = length - 1;
        } else {
            start = Long.parseLong(first);
            end = last.isEmpty() ? length - 1 : Math.min(Long.parseLong(last), length - 1);
        }
        if (start >= length || start > end) return null;
        return new long[]{start, end};
    }

    static String mimeType(String name) {
        String lower = name.toLowerCase(Locale.ROOT);
        if (lower.endsWith(".mp3")) return "audio/mpeg";
        if (lower.endsWith(".m4a") || lower.endsWith(".aac")) return "audio/mp4";
        if (lower.endsWith(".flac")) return "audio/flac";
        if (lower.endsWith(".wav")) return "audio/wav";
        if (lower.endsWith(".ogg")) return "audio/ogg";
        if (lower.endsWith(".opus")) return "audio/ogg";
        return "application/octet-stream";
    }
}

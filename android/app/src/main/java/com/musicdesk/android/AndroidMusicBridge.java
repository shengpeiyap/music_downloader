package com.musicdesk.android;

import android.app.NotificationManager;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.provider.DocumentsContract;
import android.provider.Settings;
import android.webkit.JavascriptInterface;
import android.widget.Toast;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;
import com.arthenica.ffmpegkit.FFmpegKit;
import com.arthenica.ffmpegkit.ReturnCode;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.UUID;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.Set;

/**
 * The JavaScript bridge exposed to the WebView as window.AndroidMusic. Split out of
 * MainActivity (docs/architecture-plan.md phase 3) so the Activity only handles WebView
 * lifecycle and wiring; this class holds every {@code @JavascriptInterface} entry point.
 *
 * Delegates back to {@code host} for state shared with the Activity (the WebView, executors,
 * the selected-file cache, download/queue state) and for the handful of helper methods also
 * used from {@code onActivityResult} (folder scanning, save-to-document, notify* callbacks).
 */
final class AndroidMusicBridge {
    private final MainActivity host;

    AndroidMusicBridge(MainActivity host) {
        this.host = host;
    }

    @JavascriptInterface
    public String readLocalTags(String audioName) {
        Uri sourceUri;
        synchronized (host.selectedDocumentUris) { sourceUri = host.selectedDocumentUris.get(audioName); }
        if (sourceUri == null) return "请重新选择音频文件后读取标签。";
        host.nativeDownloadExecutor.execute(() -> {
            File temp = new File(host.getCacheDir(), "musicdesk-tag-read-" + UUID.randomUUID() + extensionOf(audioName));
            try {
                copyContentToFile(sourceUri, temp);
                if (!Python.isStarted()) Python.start(new AndroidPlatform(host));
                String tags = Python.getInstance().getModule("musicdesk_downloader")
                        .callAttr("read_local_audio_tags", temp.getAbsolutePath()).toString();
                String artwork = host.readArtwork(sourceUri);
                host.runOnUiThread(() -> host.notifyLocalTagsComplete("", tags, artwork, audioName));
            } catch (Throwable failure) {
                String message = failure.getMessage() == null ? "读取音频标签失败。" : failure.getMessage();
                host.runOnUiThread(() -> host.notifyLocalTagsComplete(message, "{}", "", audioName));
            } finally { temp.delete(); }
        });
        return "";
    }

    @JavascriptInterface
    public String packageAudio(String audioName, String coverName, String coverDataUrl, String metadataJson,
                               String outputName, String outputFormat, double trimStart, double trimEnd) {
        Uri sourceUri;
        Uri coverUri;
        synchronized (host.selectedDocumentUris) {
            sourceUri = host.selectedDocumentUris.get(audioName);
            coverUri = coverName == null || coverName.isEmpty() ? null : host.selectedDocumentUris.get(coverName);
        }
        if (sourceUri == null) return "请重新选择要封装的音频文件。";
        host.nativeDownloadExecutor.execute(() -> {
            File work = new File(host.getCacheDir(), "musicdesk-package-" + UUID.randomUUID());
            File input = new File(work, host.safeDownloadFilename(audioName));
            File converted = null;
            File cover = null;
            File output = null;
            try {
                if (!work.mkdirs()) throw new IOException("无法创建临时目录");
                copyContentToFile(sourceUri, input);
                String sourceExt = extensionOf(audioName);
                String sourceFormat = sourceExt.startsWith(".") ? sourceExt.substring(1) : sourceExt;
                boolean needsTrim = trimStart > 0.01 || trimEnd > trimStart + 0.05;
                boolean needsTranscode = !sourceFormat.equalsIgnoreCase(outputFormat) || needsTrim;
                if (coverUri != null) {
                    cover = new File(work, "cover" + extensionOf(coverName));
                    copyContentToFile(coverUri, cover);
                } else if (coverDataUrl != null && coverDataUrl.startsWith("data:") && coverDataUrl.contains(",")) {
                    String mime = coverDataUrl.substring(5, coverDataUrl.indexOf(';')).toLowerCase();
                    String encoded = coverDataUrl.substring(coverDataUrl.indexOf(',') + 1);
                    cover = new File(work, mime.equals("image/png") ? "cover.png" : "cover.jpg");
                    try (FileOutputStream stream = new FileOutputStream(cover)) {
                        stream.write(android.util.Base64.decode(encoded, android.util.Base64.DEFAULT));
                    }
                }
                String ext = sourceExt.isEmpty() ? ".audio" : sourceExt;
                // The result lives in its own folder: when the exported name equals the source name
                // (same format, same title) input and output must not be the same file.
                File outDir = new File(work, "out");
                if (!outDir.mkdirs()) throw new IOException("无法创建临时目录");
                output = new File(outDir, host.safeDownloadFilename(outputName));
                String requestedExt = "." + outputFormat.toLowerCase();
                if (!output.getName().toLowerCase().endsWith(requestedExt)) {
                    output = new File(outDir, host.safeDownloadFilename(outputName) + requestedExt);
                }
                File tagSource = input;
                if (needsTranscode) {
                    converted = new File(work, "converted" + requestedExt);
                    transcodeAudio(input, converted, outputFormat, trimStart, needsTrim ? trimEnd : 0);
                    tagSource = converted;
                }
                if (!Python.isStarted()) Python.start(new AndroidPlatform(host));
                Python.getInstance().getModule("musicdesk_downloader").callAttr("package_audio_file",
                        tagSource.getAbsolutePath(), output.getAbsolutePath(), metadataJson == null ? "{}" : metadataJson,
                        cover == null ? "" : cover.getAbsolutePath());
                File packaged = output;
                host.runOnUiThread(() -> host.saveCustomOutput(packaged));
            } catch (Throwable failure) {
                if (output != null) output.delete();
                String message = failure.getMessage() == null ? "本机封装失败。" : failure.getMessage();
                host.runOnUiThread(() -> host.notifyCustomPackageComplete(message, ""));
            } finally {
                input.delete();
                if (converted != null) converted.delete();
                if (cover != null) cover.delete();
                work.delete();
            }
        });
        return "";
    }

    @JavascriptInterface
    public String convertAudio(String audioName, String outputFormat) {
        Uri sourceUri;
        synchronized (host.selectedDocumentUris) { sourceUri = host.selectedDocumentUris.get(audioName); }
        if (sourceUri == null) return "请重新选择要转换的音频文件。";
        if (!isSupportedAudioFormat(outputFormat)) return "不支持的导出格式。";
        Uri selectedUri = sourceUri;
        host.nativeDownloadExecutor.execute(() -> {
            File work = new File(host.getCacheDir(), "musicdesk-convert-" + UUID.randomUUID());
            File input = new File(work, host.safeDownloadFilename(audioName));
            File output = null;
            try {
                if (!work.mkdirs()) throw new IOException("无法创建临时目录");
                copyContentToFile(selectedUri, input);
                String base = audioName == null ? "converted" : audioName.replaceFirst("(?i)\\.[^.]+$", "");
                File outDir = new File(work, "out");
                if (!outDir.mkdirs()) throw new IOException("无法创建临时目录");
                output = new File(outDir, host.safeDownloadFilename(base + "." + outputFormat.toLowerCase()));
                transcodeAudio(input, output, outputFormat, 0, 0);
                File converted = output;
                host.runOnUiThread(() -> host.saveConversionOutput(converted));
            } catch (Throwable failure) {
                String message = failure.getMessage() == null ? "音频转换失败。" : failure.getMessage();
                if (output != null) output.delete();
                host.runOnUiThread(() -> host.notifyAndroidConvertComplete(message, ""));
            } finally {
                input.delete();
                work.delete();
            }
        });
        return "";
    }

    private boolean isSupportedAudioFormat(String format) {
        return "mp3".equalsIgnoreCase(format) || "m4a".equalsIgnoreCase(format)
                || "flac".equalsIgnoreCase(format) || "wav".equalsIgnoreCase(format)
                || "ogg".equalsIgnoreCase(format);
    }

    private void transcodeAudio(File input, File output, String format, double trimStart, double trimEnd) throws IOException {
        ArrayList<String> args = new ArrayList<>();
        args.add("-y");
        args.add("-i");
        args.add(input.getAbsolutePath());
        if (trimStart > 0.01) {
            args.add("-ss");
            args.add(String.format(java.util.Locale.US, "%.3f", trimStart));
        }
        if (trimEnd > trimStart + 0.05) {
            args.add("-t");
            args.add(String.format(java.util.Locale.US, "%.3f", trimEnd - trimStart));
        }
        args.add("-map"); args.add("0:a:0");
        args.add("-map_metadata"); args.add("0");
        args.add("-vn");
        if ("mp3".equalsIgnoreCase(format)) {
            args.add("-c:a"); args.add("libmp3lame"); args.add("-q:a"); args.add("2");
        } else if ("m4a".equalsIgnoreCase(format)) {
            args.add("-c:a"); args.add("aac"); args.add("-b:a"); args.add("192k");
        } else if ("flac".equalsIgnoreCase(format)) {
            args.add("-c:a"); args.add("flac");
        } else if ("wav".equalsIgnoreCase(format)) {
            args.add("-c:a"); args.add("pcm_s16le");
        } else if ("ogg".equalsIgnoreCase(format)) {
            args.add("-c:a"); args.add("libvorbis"); args.add("-q:a"); args.add("5");
        } else {
            throw new IOException("不支持的导出格式：" + format);
        }
        args.add(output.getAbsolutePath());
        com.arthenica.ffmpegkit.FFmpegSession session = FFmpegKit.executeWithArguments(args.toArray(new String[0]));
        if (!ReturnCode.isSuccess(session.getReturnCode()) || !output.isFile() || output.length() == 0) {
            String details = session.getOutput();
            if (details != null && details.length() > 500) details = details.substring(details.length() - 500);
            throw new IOException("FFmpeg 转换失败。" + (details == null || details.trim().isEmpty() ? "" : "\n" + details));
        }
    }

    private void transcodeCoverToJpeg(File input, File output) throws IOException {
        String[] args = new String[]{"-y", "-i", input.getAbsolutePath(), "-frames:v", "1", "-q:v", "2", output.getAbsolutePath()};
        com.arthenica.ffmpegkit.FFmpegSession session = FFmpegKit.executeWithArguments(args);
        if (!ReturnCode.isSuccess(session.getReturnCode()) || !output.isFile() || output.length() == 0) {
            String details = session.getOutput();
            if (details != null && details.length() > 300) details = details.substring(details.length() - 300);
            throw new IOException("封面转换失败。" + (details == null || details.trim().isEmpty() ? "" : "\n" + details));
        }
    }

    private void copyContentToFile(Uri uri, File destination) throws IOException {
        try (InputStream input = host.getContentResolver().openInputStream(uri);
             FileOutputStream output = new FileOutputStream(destination)) {
            if (input == null) throw new IOException("无法读取选择的文件。");
            byte[] buffer = new byte[64 * 1024];
            int count;
            while ((count = input.read(buffer)) != -1) output.write(buffer, 0, count);
        }
    }

    private String extensionOf(String filename) {
        if (filename == null) return "";
        int dot = filename.lastIndexOf('.');
        return dot < 0 ? "" : filename.substring(dot);
    }

    @JavascriptInterface
    public String getAppVersion() {
        try { return host.getPackageManager().getPackageInfo(host.getPackageName(), 0).versionName; }
        catch (PackageManager.NameNotFoundException ignored) { return "unknown"; }
    }

    @JavascriptInterface
    public String hasNotificationPermission() {
        if (Build.VERSION.SDK_INT >= 33
                && host.checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) return "false";
        if (Build.VERSION.SDK_INT >= 24) {
            NotificationManager manager = host.getSystemService(NotificationManager.class);
            return manager != null && manager.areNotificationsEnabled() ? "true" : "false";
        }
        return "true";
    }

    @JavascriptInterface
    public void openNotificationSettings() {
        host.runOnUiThread(() -> {
            Intent intent = new Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS)
                    .putExtra(Settings.EXTRA_APP_PACKAGE, host.getPackageName());
            try { host.startActivity(intent); }
            catch (RuntimeException ignored) { openAppSettings(); }
        });
    }

    @JavascriptInterface
    public void openAppSettings() {
        host.runOnUiThread(() -> {
            Intent intent = new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                    Uri.parse("package:" + host.getPackageName()));
            try { host.startActivity(intent); } catch (RuntimeException ignored) { }
        });
    }

    @JavascriptInterface
    public String getSavedFolders() {
        JSONArray folders = new JSONArray();
        SharedPreferences preferences = host.getSharedPreferences(MainActivity.PREFS_NAME, host.MODE_PRIVATE);
        Set<String> saved = new HashSet<>(preferences.getStringSet(MainActivity.PREF_SAVED_FOLDERS, new HashSet<>()));
        Set<String> granted = new HashSet<>();
        for (android.content.UriPermission permission : host.getContentResolver().getPersistedUriPermissions()) {
            if (permission.isReadPermission()) granted.add(permission.getUri().toString());
        }
        for (String value : saved) {
            Uri tree = Uri.parse(value);
            String documentId = DocumentsContract.getTreeDocumentId(tree);
            String path = documentId == null ? "" : documentId.replaceFirst("^[^:]+:", "");
            JSONObject item = new JSONObject();
            try {
                item.put("uri", value);
                item.put("name", path.isEmpty() ? documentId : path);
                item.put("authorized", granted.contains(value));
                folders.put(item);
            } catch (org.json.JSONException ignored) { }
        }
        return folders.toString();
    }

    @JavascriptInterface
    public String removeSavedFolder(String value) {
        SharedPreferences preferences = host.getSharedPreferences(MainActivity.PREFS_NAME, host.MODE_PRIVATE);
        Set<String> saved = new HashSet<>(preferences.getStringSet(MainActivity.PREF_SAVED_FOLDERS, new HashSet<>()));
        if (!saved.remove(value)) return "false";
        preferences.edit().putStringSet(MainActivity.PREF_SAVED_FOLDERS, saved).apply();
        Uri tree = Uri.parse(value);
        for (android.content.UriPermission permission : host.getContentResolver().getPersistedUriPermissions()) {
            if (permission.getUri().equals(tree)) {
                int flags = (permission.isReadPermission() ? Intent.FLAG_GRANT_READ_URI_PERMISSION : 0)
                        | (permission.isWritePermission() ? Intent.FLAG_GRANT_WRITE_URI_PERMISSION : 0);
                try { if (flags != 0) host.getContentResolver().releasePersistableUriPermission(tree, flags); }
                catch (SecurityException ignored) { }
            }
        }
        return "true";
    }

    @JavascriptInterface
    public String rescanSavedFolder(String value) {
        Set<String> saved = new HashSet<>(host.getSharedPreferences(MainActivity.PREFS_NAME, host.MODE_PRIVATE)
                .getStringSet(MainActivity.PREF_SAVED_FOLDERS, new HashSet<>()));
        if (!saved.contains(value)) return "false";
        Uri tree = Uri.parse(value);
        boolean authorized = false;
        for (android.content.UriPermission permission : host.getContentResolver().getPersistedUriPermissions()) {
            if (permission.getUri().equals(tree) && permission.isReadPermission()) authorized = true;
        }
        if (!authorized) return "false";
        host.scanFolderAsync(tree);
        return "true";
    }

    @JavascriptInterface
    public void checkForUpdates() {
        host.updateExecutor.execute(() -> {
            JSONObject result = new JSONObject();
            HttpURLConnection connection = null;
            try {
                String current = getAppVersion();
                connection = (HttpURLConnection) new URL("https://api.github.com/repos/shengpeiyap/music_downloader/releases/latest").openConnection();
                connection.setRequestMethod("GET");
                connection.setConnectTimeout(7000);
                connection.setReadTimeout(7000);
                connection.setRequestProperty("Accept", "application/vnd.github+json");
                connection.setRequestProperty("User-Agent", "MusicDesk-Android/" + current);
                int status = connection.getResponseCode();
                if (status != HttpURLConnection.HTTP_OK) throw new IOException("GitHub 返回状态 " + status);
                ByteArrayOutputStream output = new ByteArrayOutputStream();
                try (InputStream input = connection.getInputStream()) {
                    byte[] buffer = new byte[4096];
                    int count;
                    while ((count = input.read(buffer)) != -1) output.write(buffer, 0, count);
                }
                JSONObject release = new JSONObject(output.toString("UTF-8"));
                result.put("ok", true);
                result.put("current", current);
                result.put("latest", release.optString("tag_name", ""));
                result.put("url", release.optString("html_url", "https://github.com/shengpeiyap/music_downloader/releases"));
                result.put("notes", release.optString("body", ""));
            } catch (Exception error) {
                try { result.put("ok", false); result.put("error", error.getMessage() == null ? "无法连接 GitHub" : error.getMessage()); }
                catch (org.json.JSONException ignored) { }
            } finally {
                if (connection != null) connection.disconnect();
            }
            String payload = JSONObject.quote(result.toString());
            host.runOnUiThread(() -> { if (host.webView != null) host.webView.evaluateJavascript("window.onAndroidUpdateCheck && window.onAndroidUpdateCheck(" + payload + ")", null); });
        });
    }

    @JavascriptInterface
    public void openReleasePage(String value) {
        Uri uri = Uri.parse(value == null ? "" : value);
        if (!"https".equals(uri.getScheme()) || !"github.com".equals(uri.getHost())) return;
        host.runOnUiThread(() -> { try { host.startActivity(new Intent(Intent.ACTION_VIEW, uri)); } catch (RuntimeException ignored) { } });
    }

    @JavascriptInterface
    public void pickFolder() {
        host.runOnUiThread(() -> {
            Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT_TREE);
            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION);
            host.startActivityForResult(intent, MainActivity.FOLDER_CHOOSER_REQUEST);
        });
    }

    @JavascriptInterface
    public void restoreFolders() {
        SharedPreferences preferences = host.getSharedPreferences(MainActivity.PREFS_NAME, host.MODE_PRIVATE);
        Set<String> saved = new HashSet<>(preferences.getStringSet(MainActivity.PREF_SAVED_FOLDERS, new HashSet<>()));
        if (saved.isEmpty()) return;
        host.runOnUiThread(() -> {
            if (host.webView != null) host.webView.evaluateJavascript(
                    "document.getElementById('androidScopeNote').textContent='正在恢复上次的曲库…';document.getElementById('androidScopeNote').style.display='block'", null);
        });
        host.folderExecutor.execute(() -> {
            JSONArray cached = host.readTrackCache();
            if (cached.length() > 0) host.runOnUiThread(() -> host.publishTrackChunks(cached, true));
            JSONArray refreshed = new JSONArray();
            for (String value : saved) {
                JSONArray fresh = host.scanTree(Uri.parse(value));
                host.mergeCachedTracks(fresh);
                host.saveTrackCache();
                for (int i = 0; i < fresh.length(); i++) refreshed.put(fresh.optJSONObject(i));
            }
            if (refreshed.length() > 0) host.runOnUiThread(() -> host.publishTrackChunks(refreshed, true));
        });
    }

    @JavascriptInterface
    public void updatePlayback(String payload) {
        try {
            JSONObject state = new JSONObject(payload);
            host.playbackActive = state.optBoolean("playing");
            if (state.optBoolean("playing") && Build.VERSION.SDK_INT >= 33
                    && host.checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
                host.runOnUiThread(() -> host.requestPermissions(new String[]{android.Manifest.permission.POST_NOTIFICATIONS}, MainActivity.NOTIFICATION_PERMISSION_REQUEST));
            }
            Intent intent = new Intent(host, MusicPlaybackService.class)
                    .setAction(MusicPlaybackService.ACTION_UPDATE)
                    .putExtra(MusicPlaybackService.EXTRA_TITLE, state.optString("title"))
                    .putExtra(MusicPlaybackService.EXTRA_ARTIST, state.optString("artist"))
                    .putExtra(MusicPlaybackService.EXTRA_ALBUM, state.optString("album"))
                    .putExtra(MusicPlaybackService.EXTRA_PLAYING, state.optBoolean("playing"))
                    .putExtra(MusicPlaybackService.EXTRA_POSITION, state.optDouble("position", 0))
                    .putExtra(MusicPlaybackService.EXTRA_DURATION, state.optDouble("duration", 0))
                    .putExtra(MusicPlaybackService.EXTRA_MODE, state.optString("mode", "sequential"))
                    .putExtra(MusicPlaybackService.EXTRA_ARTWORK, state.optString("artwork"));
            if (Build.VERSION.SDK_INT >= 26) host.startForegroundService(intent); else host.startService(intent);
        } catch (Exception ignored) { }
    }

    @JavascriptInterface
    public void stopPlayback() {
        host.playbackActive = false;
        host.stopService(new Intent(host, MusicPlaybackService.class));
    }

    @JavascriptInterface
    public void setQueueOpen(boolean open) {
        host.queueOpen = open;
    }

    @JavascriptInterface
    public void loadAudio(String contentUri, int index) {
        host.audioExecutor.execute(() -> {
            String localUri = null;
            String artworkData = "";
            String error = "";
            File cached = null;
            try {
                Uri source = Uri.parse(contentUri);
                artworkData = host.readArtwork(source);
                String extension = ".audio";
                String path = source.getLastPathSegment();
                if (path != null && path.matches("(?i).*\\.(mp3|m4a|flac|wav|ogg|opus|aac|wma)$")) {
                    extension = path.substring(path.lastIndexOf('.'));
                }
                File folder = new File(host.getCacheDir(), "musicdesk-audio");
                if (!folder.exists() && !folder.mkdirs()) throw new java.io.IOException("无法创建音频缓存目录");
                cached = new File(folder, host.cacheKey(contentUri) + extension);
                if (!cached.isFile() || cached.length() == 0) {
                    try (InputStream input = host.getContentResolver().openInputStream(source);
                         FileOutputStream output = new FileOutputStream(cached)) {
                        if (input == null) throw new java.io.IOException("无法读取所选音频");
                        byte[] buffer = new byte[64 * 1024];
                        int count;
                        while ((count = input.read(buffer)) != -1) output.write(buffer, 0, count);
                    }
                }
                // Served over https with CORS so the Web Audio equalizer can process it.
                localUri = LocalMediaRoutes.urlFor(cached);
            } catch (Exception failure) {
                if (cached != null) cached.delete();
                error = failure.getMessage() == null ? "读取音频失败" : failure.getMessage();
            }
            final String resultUri = localUri;
            final String resultError = error;
            String script = "window.onAndroidAudioReady && window.onAndroidAudioReady(" + index + ","
                    + JSONObject.quote(contentUri) + "," + JSONObject.quote(resultUri == null ? "" : resultUri)
                    + "," + JSONObject.quote(resultError) + "," + JSONObject.quote(artworkData) + ")";
            host.runOnUiThread(() -> {
                if (host.webView != null) host.webView.evaluateJavascript(script, null);
            });
            if (cached != null && resultUri != null) {
                // Embedded lyrics are read after playback has been handed over, so a slow tag parse never delays audio.
                String lyrics = "";
                try {
                    if (!Python.isStarted()) Python.start(new AndroidPlatform(host));
                    lyrics = Python.getInstance().getModule("musicdesk_downloader")
                            .callAttr("read_local_lyrics", cached.getAbsolutePath()).toString();
                } catch (Throwable ignored) { }
                String lyricsScript = "window.onAndroidLyrics && window.onAndroidLyrics("
                        + JSONObject.quote(contentUri) + "," + JSONObject.quote(lyrics) + ")";
                host.runOnUiThread(() -> {
                    if (host.webView != null) host.webView.evaluateJavascript(lyricsScript, null);
                });
            }
        });
    }

    @JavascriptInterface
    public void loadArtwork(String contentUri) {
        if (contentUri == null || contentUri.isEmpty()) return;
        host.artworkExecutor.execute(() -> {
            String data = host.readArtworkThumbnail(contentUri);
            String script = "window.onAndroidArtwork && window.onAndroidArtwork("
                    + JSONObject.quote(contentUri) + "," + JSONObject.quote(data) + ")";
            host.runOnUiThread(() -> {
                if (host.webView != null) host.webView.evaluateJavascript(script, null);
            });
        });
    }

    @JavascriptInterface
    public void releaseAudio(String contentUri) {
        File folder = new File(host.getCacheDir(), "musicdesk-audio");
        File[] cachedFiles = folder.listFiles();
        if (cachedFiles == null) return;
        for (File file : cachedFiles) {
            if (file.getName().startsWith(host.cacheKey(contentUri))) file.delete();
        }
    }

    @JavascriptInterface
    public void createDownload(String filename, String mimeType) {
        host.runOnUiThread(() -> {
            if (host.downloadOutput != null) cancelDownload();
            Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT);
            intent.addCategory(Intent.CATEGORY_OPENABLE);
            String contentType = mimeType == null ? "" : mimeType.split(";", 2)[0].trim();
            intent.setType(contentType.isEmpty() ? "application/octet-stream" : contentType);
            intent.putExtra(Intent.EXTRA_TITLE, host.safeDownloadFilename(filename));
            try {
                host.startActivityForResult(intent, MainActivity.DOWNLOAD_DESTINATION_REQUEST);
            } catch (RuntimeException error) {
                host.notifyDownloadReady("无法打开保存位置选择器。");
            }
        });
    }

    @JavascriptInterface
    public String lookupWithYtDlp(String source) {
        if (source == null || source.trim().isEmpty()) return "请输入 YouTube 分享链接或关键词。";
        host.nativeDownloadExecutor.execute(() -> {
            try {
                if (!Python.isStarted()) Python.start(new AndroidPlatform(host));
                String result = Python.getInstance().getModule("musicdesk_downloader")
                        .callAttr("extract_metadata", source).toString();
                host.runOnUiThread(() -> host.notifyNativeMetadataComplete("", result));
            } catch (Throwable failure) {
                String message = failure.getMessage();
                if (message == null || message.trim().isEmpty()) message = "本机曲目搜索失败。";
                String error = message;
                host.runOnUiThread(() -> host.notifyNativeMetadataComplete(error, ""));
            }
        });
        return "";
    }

    @JavascriptInterface
    public String searchMusicBrainz(String query) {
        if (query == null || query.trim().isEmpty()) return "请输入歌曲名或“作者 - 标题”。";
        host.nativeDownloadExecutor.execute(() -> {
            try {
                if (!Python.isStarted()) Python.start(new AndroidPlatform(host));
                String result = Python.getInstance().getModule("musicdesk_downloader")
                        .callAttr("search_musicbrainz", query).toString();
                host.runOnUiThread(() -> host.notifyNativeMetadataComplete("", result));
            } catch (Throwable failure) {
                String message = failure.getMessage();
                if (message == null || message.trim().isEmpty()) message = "MusicBrainz 曲目检索失败。";
                String error = message;
                host.runOnUiThread(() -> host.notifyNativeMetadataComplete(error, ""));
            }
        });
        return "";
    }

    @JavascriptInterface
    public String searchCandidates(String query) {
        if (query == null || query.trim().isEmpty()) return "请输入歌曲名或“作者 - 标题”。";
        host.nativeDownloadExecutor.execute(() -> {
            try {
                if (!Python.isStarted()) Python.start(new AndroidPlatform(host));
                String result = Python.getInstance().getModule("musicdesk_downloader")
                        .callAttr("search_candidates", query).toString();
                host.runOnUiThread(() -> host.notifyNativeCandidatesComplete("", result));
            } catch (Throwable failure) {
                String message = failure.getMessage();
                if (message == null || message.trim().isEmpty()) message = "搜索其他匹配结果失败。";
                String error = message;
                host.runOnUiThread(() -> host.notifyNativeCandidatesComplete(error, ""));
            }
        });
        return "";
    }

    @JavascriptInterface
    public String lookupLyrics(String title, String artist) {
        if (title == null || title.trim().isEmpty()) return "请先读取歌曲信息。";
        host.nativeDownloadExecutor.execute(() -> {
            try {
                if (!Python.isStarted()) Python.start(new AndroidPlatform(host));
                String result = Python.getInstance().getModule("musicdesk_downloader")
                        .callAttr("lookup_lyrics", title, artist == null ? "" : artist).toString();
                host.runOnUiThread(() -> host.notifyNativeLyricsComplete("", result));
            } catch (Throwable failure) {
                String message = failure.getMessage();
                if (message == null || message.trim().isEmpty()) message = "歌词检索失败。";
                String error = message;
                host.runOnUiThread(() -> host.notifyNativeLyricsComplete(error, ""));
            }
        });
        return "";
    }

    @JavascriptInterface
    public String downloadWithYtDlp(String source, String metadataJson) {
        if (source == null || source.trim().isEmpty()) return "没有可下载的曲目链接或搜索词。";
        host.nativeDownloadExecutor.execute(() -> {
            File workDir = new File(host.getCacheDir(), "musicdesk-native-download");
            deleteChildren(workDir);
            try {
                if (!Python.isStarted()) Python.start(new AndroidPlatform(host));
                String result = Python.getInstance().getModule("musicdesk_downloader")
                        .callAttr("download_audio_with_metadata", source, workDir.getAbsolutePath(), metadataJson == null ? "{}" : metadataJson).toString();
                JSONObject data = new JSONObject(result);
                File downloaded = new File(data.optString("path", ""));
                if (!downloaded.isFile() || downloaded.length() == 0) throw new IOException("下载器没有生成有效音频文件。");
                JSONObject tagMetadata = data.optJSONObject("tag_metadata");
                if (tagMetadata == null) tagMetadata = new JSONObject(metadataJson == null ? "{}" : metadataJson);

                File audioForTagging = downloaded;
                File converted = null;
                if (!".mp3".equalsIgnoreCase(extensionOf(downloaded.getName()))) {
                    converted = new File(workDir, downloaded.getName().replaceFirst("(?i)\\.[^.]+$", "") + "-converted.mp3");
                    transcodeAudio(downloaded, converted, "mp3", 0, 0);
                    audioForTagging = converted;
                }

                String artist = tagMetadata.optString("artist", "").trim();
                String title = tagMetadata.optString("title", data.optString("title", "MusicDesk-download")).trim();
                String outputBase = (artist.isEmpty() ? "" : artist + " - ") + title;
                File tagged = new File(workDir, host.safeDownloadFilename(outputBase) + ".mp3");
                if (tagged.equals(downloaded) || tagged.equals(audioForTagging)) {
                    tagged = new File(workDir, "MusicDesk-" + UUID.randomUUID() + ".mp3");
                }

                String coverPath = data.optString("cover_path", "");
                File cover = coverPath.isEmpty() ? null : new File(coverPath);
                File jpegCover = null;
                String warning = "";
                if (cover != null && cover.isFile()) {
                    jpegCover = new File(workDir, "cover-musicdesk.jpg");
                    try {
                        transcodeCoverToJpeg(cover, jpegCover);
                        cover = jpegCover;
                    } catch (IOException coverFailure) {
                        jpegCover.delete();
                        cover = null;
                        warning = "音频已转为 MP3，但封面转换失败，未能嵌入。";
                    }
                } else {
                    cover = null;
                    warning = "音频已转为 MP3，但未能获取封面。";
                }

                if (!Python.isStarted()) Python.start(new AndroidPlatform(host));
                Python.getInstance().getModule("musicdesk_downloader").callAttr("package_audio_file",
                        audioForTagging.getAbsolutePath(), tagged.getAbsolutePath(), tagMetadata.toString(),
                        cover == null ? "" : cover.getAbsolutePath());
                downloaded.delete();
                if (converted != null) converted.delete();
                host.saveNativeDownload(tagged, warning, data.optString("lyrics_status", ""));
            } catch (Throwable failure) {
                String message = failure.getMessage();
                if (message == null || message.trim().isEmpty()) message = "本机 yt-dlp 下载失败。";
                String error = message;
                host.runOnUiThread(() -> host.notifyNativeDownloadComplete(error, "", ""));
            }
        });
        return "";
    }

    private void deleteChildren(File directory) {
        File[] files = directory.listFiles();
        if (files != null) for (File file : files) {
            if (file.isDirectory()) deleteChildren(file);
            file.delete();
        }
    }

    @JavascriptInterface
    public synchronized String writeDownloadChunk(String base64Data) {
        if (host.downloadOutput == null) return "保存目标已关闭。";
        try {
            byte[] bytes = android.util.Base64.decode(base64Data, android.util.Base64.DEFAULT);
            host.downloadOutput.write(bytes);
            return "";
        } catch (IOException | IllegalArgumentException error) {
            return "写入下载文件失败：" + error.getMessage();
        }
    }

    @JavascriptInterface
    public synchronized String finishDownload() {
        try {
            if (host.downloadOutput != null) host.downloadOutput.close();
            host.downloadOutput = null;
            host.downloadUri = null;
            host.runOnUiThread(() -> Toast.makeText(host, "文件已保存", Toast.LENGTH_SHORT).show());
            return "";
        } catch (IOException error) {
            cancelDownload();
            host.runOnUiThread(() -> Toast.makeText(host, "保存文件失败", Toast.LENGTH_LONG).show());
            return "保存文件失败：" + error.getMessage();
        }
    }

    @JavascriptInterface
    public synchronized void cancelDownload() {
        try {
            if (host.downloadOutput != null) host.downloadOutput.close();
        } catch (IOException ignored) {
            // The canceled or failed download is already unusable.
        }
        host.downloadOutput = null;
        if (host.downloadUri != null) {
            try { DocumentsContract.deleteDocument(host.getContentResolver(), host.downloadUri); }
            catch (Exception ignored) { /* Some document providers do not support deletion. */ }
            host.downloadUri = null;
        }
    }
}

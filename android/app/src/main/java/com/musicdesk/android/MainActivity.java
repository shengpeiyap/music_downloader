package com.musicdesk.android;

import android.app.Activity;
import android.app.NotificationManager;
import android.content.Intent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.IntentFilter;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.os.Build;
import android.media.MediaMetadataRetriever;
import android.database.Cursor;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.provider.DocumentsContract;
import android.provider.OpenableColumns;
import android.provider.Settings;
import android.view.ViewGroup;
import android.webkit.JavascriptInterface;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.widget.Toast;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;
import com.arthenica.ffmpegkit.FFmpegKit;
import com.arthenica.ffmpegkit.ReturnCode;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.ByteArrayOutputStream;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.UUID;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.Set;
import java.util.HashMap;
import java.util.Map;

public final class MainActivity extends Activity {
    private static final int FILE_CHOOSER_REQUEST = 4102;
    static final int FOLDER_CHOOSER_REQUEST = 4103;
    static final int DOWNLOAD_DESTINATION_REQUEST = 4104;
    static final String PREFS_NAME = "musicdesk-library";
    static final String PREF_SAVED_FOLDERS = "saved-folder-uris";
    static final int NOTIFICATION_PERMISSION_REQUEST = 4105;
    private static final int CUSTOM_OUTPUT_REQUEST = 4106;
    private static final int CONVERT_OUTPUT_REQUEST = 4107;

    WebView webView;
    private ValueCallback<Uri[]> fileSelectionCallback;
    OutputStream downloadOutput;
    Uri downloadUri;
    private File pendingNativeDownload;
    private File pendingCustomOutput;
    private File pendingConversionOutput;
    private String pendingNativeDownloadWarning = "";
    private String pendingNativeDownloadLyricsStatus = "";
    volatile boolean queueOpen;
    final ExecutorService folderExecutor = Executors.newSingleThreadExecutor();
    final ExecutorService audioExecutor = Executors.newSingleThreadExecutor();
    final ExecutorService artworkExecutor = Executors.newSingleThreadExecutor();
    final ExecutorService updateExecutor = Executors.newSingleThreadExecutor();
    final ExecutorService nativeDownloadExecutor = Executors.newSingleThreadExecutor();
    private final Map<String, JSONObject> cachedTracks = new HashMap<>();
    final Map<String, Uri> selectedDocumentUris = new HashMap<>();
    private boolean mediaReceiverRegistered;
    volatile boolean playbackActive;
    private final BroadcastReceiver mediaCommandReceiver = new BroadcastReceiver() {
        @Override public void onReceive(Context context, Intent intent) {
            String command = intent.getStringExtra(MusicPlaybackService.EXTRA_COMMAND);
            if (webView != null && command != null) {
                long position = intent.getLongExtra(MusicPlaybackService.EXTRA_POSITION, -1);
                webView.evaluateJavascript("window.onAndroidMediaCommand && window.onAndroidMediaCommand(" + JSONObject.quote(command) + "," + position + ")", null);
            }
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().setStatusBarColor(Color.rgb(12, 15, 13));
        getWindow().setNavigationBarColor(Color.rgb(12, 15, 13));

        webView = new WebView(this);
        webView.setBackgroundColor(Color.rgb(12, 15, 13));
        webView.setLayoutParams(new ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT));

        WebSettings settings = webView.getSettings();
        settings.setSupportZoom(false);
        settings.setBuiltInZoomControls(false);
        settings.setDisplayZoomControls(false);
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(true);
        settings.setAllowContentAccess(true);
        settings.setAllowFileAccessFromFileURLs(false);
        settings.setAllowUniversalAccessFromFileURLs(false);
        settings.setMediaPlaybackRequiresUserGesture(false);
        settings.setUserAgentString(settings.getUserAgentString() + " MusicDeskAndroid/" + BuildConfig.VERSION_NAME);

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                if (!LocalMediaRoutes.matches(uri.getScheme(), uri.getHost(), uri.getPath())) return null;
                return serveCachedAudio(request);
            }

            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                if ("file".equals(uri.getScheme())
                        && uri.getPath() != null
                        && uri.getPath().startsWith("/android_asset/")) {
                    return false;
                }
                if ("https".equals(uri.getScheme()) || "http".equals(uri.getScheme())) {
                    try {
                        startActivity(new Intent(Intent.ACTION_VIEW, uri));
                    } catch (RuntimeException ignored) {
                        // Keep the app open if no external browser is available.
                    }
                }
                return true;
            }
        });
        webView.addJavascriptInterface(new AndroidMusicBridge(this), "AndroidMusic");
        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(
                    WebView view,
                    ValueCallback<Uri[]> filePathCallback,
                    FileChooserParams fileChooserParams) {
                if (fileSelectionCallback != null) {
                    fileSelectionCallback.onReceiveValue(null);
                }
                fileSelectionCallback = filePathCallback;
                try {
                    Intent chooser = Intent.createChooser(
                            fileChooserParams.createIntent(), "选择音乐文件");
                    startActivityForResult(chooser, FILE_CHOOSER_REQUEST);
                    return true;
                } catch (RuntimeException error) {
                    fileSelectionCallback = null;
                    filePathCallback.onReceiveValue(null);
                    return false;
                }
            }
        });

        setContentView(webView);
        IntentFilter mediaFilter = new IntentFilter(MusicPlaybackService.ACTION_MEDIA_COMMAND);
        if (Build.VERSION.SDK_INT >= 33) registerReceiver(mediaCommandReceiver, mediaFilter, Context.RECEIVER_NOT_EXPORTED);
        else registerReceiver(mediaCommandReceiver, mediaFilter);
        mediaReceiverRegistered = true;
        webView.loadUrl("file:///android_asset/index.html");
    }

    @Override
    protected void onResume() {
        super.onResume();
        WebView currentWebView = webView;
        if (currentWebView != null) currentWebView.postDelayed(() -> {
            if (webView == currentWebView) currentWebView.evaluateJavascript(
                    "window.refreshAndroidSettings && window.refreshAndroidSettings()", null);
        }, 300);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        if (requestCode == DOWNLOAD_DESTINATION_REQUEST) {
            if (pendingNativeDownload != null) {
                File source = pendingNativeDownload;
                pendingNativeDownload = null;
                if (resultCode != RESULT_OK || data == null || data.getData() == null) {
                    source.delete();
                    notifyNativeDownloadComplete("已取消保存文件。", "", "");
                    return;
                }
                copyNativeDownloadToDocument(source, data.getData());
                return;
            }
            if (resultCode != RESULT_OK || data == null || data.getData() == null) {
                notifyDownloadReady("已取消保存文件。");
                return;
            }
            try {
                downloadOutput = getContentResolver().openOutputStream(data.getData(), "wt");
                if (downloadOutput == null) throw new IOException("无法创建目标文件");
                downloadUri = data.getData();
                notifyDownloadReady("");
            } catch (IOException | SecurityException error) {
                notifyDownloadReady("无法创建目标文件：" + error.getMessage());
            }
            return;
        }
        if (requestCode == FILE_CHOOSER_REQUEST) {
            Uri[] selectedUris = WebChromeClient.FileChooserParams.parseResult(resultCode, data);
            if (selectedUris != null) {
                synchronized (selectedDocumentUris) {
                    for (Uri uri : selectedUris) {
                        String name = queryDisplayName(uri);
                        if (!name.isEmpty()) selectedDocumentUris.put(name, uri);
                    }
                    while (selectedDocumentUris.size() > 32) {
                        selectedDocumentUris.remove(selectedDocumentUris.keySet().iterator().next());
                    }
                }
            }
            if (fileSelectionCallback != null) {
                fileSelectionCallback.onReceiveValue(selectedUris);
                fileSelectionCallback = null;
            }
            return;
        }
        if (requestCode == CUSTOM_OUTPUT_REQUEST) {
            File source = pendingCustomOutput;
            pendingCustomOutput = null;
            if (source == null) return;
            if (resultCode != RESULT_OK || data == null || data.getData() == null) {
                source.delete();
                File parent = source.getParentFile();
                if (parent != null) parent.delete();
                notifyCustomPackageComplete("已取消保存封装文件。", "");
                return;
            }
            copyCustomOutputToDocument(source, data.getData());
            return;
        }
        if (requestCode == CONVERT_OUTPUT_REQUEST) {
            File source = pendingConversionOutput;
            pendingConversionOutput = null;
            if (source == null) return;
            if (resultCode != RESULT_OK || data == null || data.getData() == null) {
                source.delete();
                File parent = source.getParentFile();
                if (parent != null) parent.delete();
                notifyAndroidConvertComplete("已取消保存转换文件。", "");
                return;
            }
            copyConversionOutputToDocument(source, data.getData());
            return;
        }
        if (requestCode == FOLDER_CHOOSER_REQUEST) {
            if (resultCode == RESULT_OK && data != null && data.getData() != null) {
                Uri tree = data.getData();
                if (webView != null) webView.evaluateJavascript(
                        "document.getElementById('androidScopeNote').textContent='正在扫描文件夹中的音频…';document.getElementById('androidScopeNote').style.display='block'", null);
                try {
                    getContentResolver().takePersistableUriPermission(tree,
                            data.getFlags() & (Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_WRITE_URI_PERMISSION));
                    rememberFolder(tree);
                } catch (SecurityException ignored) {
                    // The current picker session still grants access even if persistence is unavailable.
                }
                scanFolderAsync(tree);
            }
            return;
        }
        super.onActivityResult(requestCode, resultCode, data);
    }

    void notifyDownloadReady(String error) {
        if (webView == null) return;
        webView.evaluateJavascript("window.onAndroidDownloadReady && window.onAndroidDownloadReady(" + JSONObject.quote(error) + ")", null);
    }

    void notifyNativeDownloadComplete(String error, String filename, String warning) {
        notifyNativeDownloadComplete(error, filename, warning, "");
    }

    void notifyNativeDownloadComplete(String error, String filename, String warning, String lyricsStatus) {
        if (webView == null) return;
        webView.evaluateJavascript("window.onAndroidNativeDownloadComplete && window.onAndroidNativeDownloadComplete("
                + JSONObject.quote(error) + "," + JSONObject.quote(filename) + "," + JSONObject.quote(warning)
                + "," + JSONObject.quote(lyricsStatus == null ? "" : lyricsStatus) + ")", null);
    }

    void notifyNativeMetadataComplete(String error, String metadata) {
        if (webView == null) return;
        webView.evaluateJavascript("window.onAndroidNativeMetadataComplete && window.onAndroidNativeMetadataComplete("
                + JSONObject.quote(error) + "," + JSONObject.quote(metadata) + ")", null);
    }

    void notifyNativeCandidatesComplete(String error, String result) {
        if (webView == null) return;
        webView.evaluateJavascript("window.onAndroidCandidatesComplete && window.onAndroidCandidatesComplete("
                + JSONObject.quote(error) + "," + JSONObject.quote(result) + ")", null);
    }

    void notifyNativeLyricsComplete(String error, String result) {
        if (webView == null) return;
        webView.evaluateJavascript("window.onAndroidNativeLyricsComplete && window.onAndroidNativeLyricsComplete("
                + JSONObject.quote(error) + "," + JSONObject.quote(result) + ")", null);
    }

    void notifyCustomPackageComplete(String error, String filename) {
        if (webView != null) webView.evaluateJavascript("window.onAndroidCustomPackageComplete && window.onAndroidCustomPackageComplete("
                + JSONObject.quote(error) + "," + JSONObject.quote(filename) + ")", null);
    }

    void notifyAndroidConvertComplete(String error, String filename) {
        if (webView != null) webView.evaluateJavascript("window.onAndroidConvertComplete && window.onAndroidConvertComplete("
                + JSONObject.quote(error) + "," + JSONObject.quote(filename) + ")", null);
    }

    void notifyLocalTagsComplete(String error, String tags, String artwork, String audioName) {
        if (webView != null) webView.evaluateJavascript("window.onAndroidLocalTagsComplete && window.onAndroidLocalTagsComplete("
                + JSONObject.quote(error) + "," + JSONObject.quote(tags) + "," + JSONObject.quote(artwork) + ","
                + JSONObject.quote(audioName) + ")", null);
    }

    private String queryDisplayName(Uri uri) {
        try (Cursor cursor = getContentResolver().query(uri, new String[]{OpenableColumns.DISPLAY_NAME}, null, null, null)) {
            if (cursor != null && cursor.moveToFirst()) return cursor.getString(0);
        } catch (RuntimeException ignored) { }
        return "";
    }

    private void copyCustomOutputToDocument(File source, Uri destination) {
        nativeDownloadExecutor.execute(() -> {
            String error = "";
            String filename = source.getName();
            try (InputStream input = new java.io.FileInputStream(source);
                 OutputStream output = getContentResolver().openOutputStream(destination, "wt")) {
                if (output == null) throw new IOException("无法创建目标文件");
                byte[] buffer = new byte[64 * 1024];
                int count;
                while ((count = input.read(buffer)) != -1) output.write(buffer, 0, count);
            } catch (Exception failure) {
                error = failure.getMessage() == null ? "保存封装文件失败。" : failure.getMessage();
                try { DocumentsContract.deleteDocument(getContentResolver(), destination); } catch (Exception ignored) { }
            } finally { source.delete(); }
            String resultError = error;
            String resultFilename = filename;
            runOnUiThread(() -> {
                File parent = source.getParentFile();
                if (parent != null) {
                    File grandparent = parent.getParentFile();
                    parent.delete();
                    if (grandparent != null) grandparent.delete();
                }
                notifyCustomPackageComplete(resultError, resultFilename);
            });
        });
    }

    void saveCustomOutput(File source) {
        pendingCustomOutput = source;
        runOnUiThread(() -> {
            String ext = source.getName().contains(".") ? source.getName().substring(source.getName().lastIndexOf('.')).toLowerCase() : "";
            String mime = ext.equals(".m4a") ? "audio/mp4" : ext.equals(".mp3") ? "audio/mpeg"
                    : ext.equals(".flac") ? "audio/flac" : ext.equals(".ogg") || ext.equals(".opus") ? "audio/ogg" : "audio/*";
            Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE)
                    .setType(mime).putExtra(Intent.EXTRA_TITLE, safeDownloadFilename(source.getName()));
            try { startActivityForResult(intent, CUSTOM_OUTPUT_REQUEST); }
            catch (RuntimeException failure) {
                pendingCustomOutput = null;
                source.delete();
                notifyCustomPackageComplete("无法打开保存位置选择器。", "");
            }
        });
    }

    void saveConversionOutput(File source) {
        pendingConversionOutput = source;
        runOnUiThread(() -> {
            String sourceName = source.getName();
            int dot = sourceName.lastIndexOf('.');
            String ext = dot < 0 ? "" : sourceName.substring(dot).toLowerCase();
            String mime = ext.equals(".m4a") ? "audio/mp4" : ext.equals(".mp3") ? "audio/mpeg"
                    : ext.equals(".flac") ? "audio/flac" : ext.equals(".ogg") ? "audio/ogg" : "audio/wav";
            Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE)
                    .setType(mime).putExtra(Intent.EXTRA_TITLE, safeDownloadFilename(source.getName()));
            try { startActivityForResult(intent, CONVERT_OUTPUT_REQUEST); }
            catch (RuntimeException failure) {
                pendingConversionOutput = null;
                source.delete();
                notifyAndroidConvertComplete("无法打开保存位置选择器。", "");
            }
        });
    }

    private void copyConversionOutputToDocument(File source, Uri destination) {
        nativeDownloadExecutor.execute(() -> {
            String error = "";
            String filename = source.getName();
            try (InputStream input = new java.io.FileInputStream(source);
                 OutputStream output = getContentResolver().openOutputStream(destination, "wt")) {
                if (output == null) throw new IOException("无法创建目标文件");
                byte[] buffer = new byte[64 * 1024];
                int count;
                while ((count = input.read(buffer)) != -1) output.write(buffer, 0, count);
            } catch (Exception failure) {
                error = failure.getMessage() == null ? "保存转换文件失败。" : failure.getMessage();
                try { DocumentsContract.deleteDocument(getContentResolver(), destination); } catch (Exception ignored) { }
            } finally { source.delete(); }
            String resultError = error;
            String resultFilename = filename;
            runOnUiThread(() -> {
                File parent = source.getParentFile();
                if (parent != null) {
                    File grandparent = parent.getParentFile();
                    parent.delete();
                    if (grandparent != null) grandparent.delete();
                }
                notifyAndroidConvertComplete(resultError, resultFilename);
            });
        });
    }

    private void copyNativeDownloadToDocument(File source, Uri destination) {
        nativeDownloadExecutor.execute(() -> {
            String error = "";
            String filename = source.getName();
            try (InputStream input = new java.io.FileInputStream(source);
                 OutputStream output = getContentResolver().openOutputStream(destination, "wt")) {
                if (output == null) throw new IOException("无法创建目标文件");
                byte[] buffer = new byte[64 * 1024];
                int count;
                while ((count = input.read(buffer)) != -1) output.write(buffer, 0, count);
            } catch (Exception failure) {
                error = failure.getMessage() == null ? "保存下载文件失败。" : failure.getMessage();
                try { DocumentsContract.deleteDocument(getContentResolver(), destination); }
                catch (Exception ignored) { }
            } finally {
                source.delete();
            }
            String resultError = error;
            String resultFilename = filename;
            runOnUiThread(() -> notifyNativeDownloadComplete(resultError, resultFilename, pendingNativeDownloadWarning, pendingNativeDownloadLyricsStatus));
        });
    }

    void saveNativeDownload(File source, String warning, String lyricsStatus) {
        pendingNativeDownloadWarning = warning == null ? "" : warning;
        pendingNativeDownloadLyricsStatus = lyricsStatus == null ? "" : lyricsStatus;
        pendingNativeDownload = source;
        runOnUiThread(() -> {
            String filename = source.getName();
            String extension = filename.contains(".") ? filename.substring(filename.lastIndexOf('.')).toLowerCase() : "";
            String mime = extension.equals(".m4a") || extension.equals(".mp4") ? "audio/mp4"
                    : extension.equals(".mp3") ? "audio/mpeg"
                    : extension.equals(".ogg") || extension.equals(".opus") ? "audio/ogg"
                    : extension.equals(".wav") ? "audio/wav" : "application/octet-stream";
            Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT);
            intent.addCategory(Intent.CATEGORY_OPENABLE);
            intent.setType(mime);
            intent.putExtra(Intent.EXTRA_TITLE, safeDownloadFilename(filename));
            try { startActivityForResult(intent, DOWNLOAD_DESTINATION_REQUEST); }
            catch (RuntimeException failure) {
                pendingNativeDownload = null;
                source.delete();
                notifyNativeDownloadComplete("无法打开保存位置选择器。", "", "");
            }
        });
    }

    JSONArray scanTree(Uri tree) {
        JSONArray results = new JSONArray();
        try {
            String rootId = DocumentsContract.getTreeDocumentId(tree);
            scanDocumentTree(tree, rootId, results, 0, "");
        } catch (RuntimeException ignored) {
            // Return an empty array so the page can show a useful empty-library state.
        }
        return results;
    }

    void scanFolderAsync(Uri tree) {
        folderExecutor.execute(() -> {
            JSONArray tracks = scanTree(tree);
            mergeCachedTracks(tracks);
            saveTrackCache();
            publishTrackChunks(tracks, true);
        });
    }

    void publishTrackChunks(JSONArray tracks, boolean finalChunk) {
            int chunkSize = 100;
            int total = tracks.length();
            if (total == 0) {
                runOnUiThread(() -> {
                    if (webView != null) webView.evaluateJavascript("window.onAndroidFolderPicked && window.onAndroidFolderPicked('[]',true,false)", null);
                });
            }
            for (int start = 0; start < total; start += chunkSize) {
                JSONArray batch = new JSONArray();
                int end = Math.min(start + chunkSize, total);
                for (int index = start; index < end; index++) batch.put(tracks.optJSONObject(index));
                String payload = JSONObject.quote(batch.toString());
                boolean finished = finalChunk && end == total;
                boolean capped = total >= 5000;
                String script = "window.onAndroidFolderPicked && window.onAndroidFolderPicked(" + payload + "," + finished + "," + capped + ")";
                runOnUiThread(() -> {
                    if (webView != null) webView.evaluateJavascript(script, null);
                });
            }
    }

    private File trackCacheFile() { return new File(getFilesDir(), "musicdesk-library-index.json"); }

    JSONArray readTrackCache() {
        File file = trackCacheFile();
        if (!file.isFile()) return new JSONArray();
        try (InputStream input = new java.io.FileInputStream(file); ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[8192];
            int count;
            while ((count = input.read(buffer)) != -1) output.write(buffer, 0, count);
            JSONArray records = new JSONArray(output.toString("UTF-8"));
            cachedTracks.clear();
            for (int i = 0; i < records.length(); i++) {
                JSONObject record = records.optJSONObject(i);
                if (record != null && record.optString("uri", "").length() > 0) cachedTracks.put(record.optString("uri"), record);
            }
            return records;
        } catch (Exception ignored) {
            return new JSONArray();
        }
    }

    void mergeCachedTracks(JSONArray records) {
        for (int i = 0; i < records.length(); i++) {
            JSONObject record = records.optJSONObject(i);
            if (record != null && record.optString("uri", "").length() > 0) cachedTracks.put(record.optString("uri"), record);
        }
    }

    void saveTrackCache() {
        JSONArray records = new JSONArray();
        for (JSONObject record : cachedTracks.values()) records.put(record);
        File destination = trackCacheFile();
        File temporary = new File(destination.getParentFile(), destination.getName() + ".tmp");
        try (FileOutputStream output = new FileOutputStream(temporary)) {
            output.write(records.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8));
            output.getFD().sync();
            if (!temporary.renameTo(destination)) {
                try (FileOutputStream retry = new FileOutputStream(destination)) { retry.write(records.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8)); }
                temporary.delete();
            }
        } catch (IOException ignored) { temporary.delete(); }
    }

    private void rememberFolder(Uri tree) {
        SharedPreferences preferences = getSharedPreferences(PREFS_NAME, MODE_PRIVATE);
        Set<String> saved = new HashSet<>(preferences.getStringSet(PREF_SAVED_FOLDERS, new HashSet<>()));
        saved.add(tree.toString());
        preferences.edit().putStringSet(PREF_SAVED_FOLDERS, saved).apply();
    }

    private void scanDocumentTree(Uri tree, String parentId, JSONArray results, int depth, String folderPath) {
        if (depth > 32 || results.length() >= 5000) return;
        Uri children = DocumentsContract.buildChildDocumentsUriUsingTree(tree, parentId);
        String[] columns = {DocumentsContract.Document.COLUMN_DOCUMENT_ID,
                DocumentsContract.Document.COLUMN_DISPLAY_NAME, DocumentsContract.Document.COLUMN_MIME_TYPE,
                DocumentsContract.Document.COLUMN_LAST_MODIFIED};
        try (Cursor cursor = getContentResolver().query(children, columns, null, null, null)) {
            if (cursor == null) return;
            while (cursor.moveToNext() && results.length() < 5000) {
                String id = cursor.getString(0);
                String name = cursor.getString(1);
                String mime = cursor.getString(2);
                long modified = cursor.getColumnCount() > 3 && !cursor.isNull(3) ? cursor.getLong(3) : 0L;
                if (DocumentsContract.Document.MIME_TYPE_DIR.equals(mime)) {
                    String childPath = folderPath.isEmpty() ? name : folderPath + "/" + name;
                    scanDocumentTree(tree, id, results, depth + 1, childPath);
                } else if (isAudio(name, mime)) {
                    Uri fileUri = DocumentsContract.buildDocumentUriUsingTree(tree, id);
                    JSONObject cached = cachedTracks.get(fileUri.toString());
                    if (cached != null && cached.optLong("modified", -1L) == modified
                            && name.equals(cached.optString("name"))) {
                        results.put(cached);
                        continue;
                    }
                    JSONObject track = new JSONObject();
                    try {
                        track.put("uri", fileUri.toString());
                        track.put("name", name);
                        track.put("folderPath", folderPath);
                        track.put("modified", modified);
                        track.put("title", name.replaceFirst("(?i)\\.[^.]+$", ""));
                        track.put("artist", "未知歌手");
                        track.put("album", "未知专辑");
                        MediaMetadataRetriever metadata = new MediaMetadataRetriever();
                        try {
                            metadata.setDataSource(this, fileUri);
                            String title = metadata.extractMetadata(MediaMetadataRetriever.METADATA_KEY_TITLE);
                            String artist = metadata.extractMetadata(MediaMetadataRetriever.METADATA_KEY_ARTIST);
                            String album = metadata.extractMetadata(MediaMetadataRetriever.METADATA_KEY_ALBUM);
                            if (title != null && !title.trim().isEmpty()) track.put("title", title);
                            if (artist != null && !artist.trim().isEmpty()) track.put("artist", artist);
                            if (album != null && !album.trim().isEmpty()) track.put("album", album);
                        } catch (RuntimeException ignored) {
                            // File-name metadata remains usable when a provider cannot parse tags.
                        } finally {
                            try {
                                metadata.release();
                            } catch (IOException ignored) {
                                // Releasing provider metadata must not interrupt folder scanning.
                            }
                        }
                        results.put(track);
                    } catch (org.json.JSONException ignored) {
                        // Skip malformed provider entries.
                    }
                }
            }
        } catch (RuntimeException ignored) {
            // Some document providers deny individual subdirectories; continue elsewhere.
        }
    }

    private boolean isAudio(String name, String mime) {
        if (mime != null && mime.startsWith("audio/")) return true;
        return name != null && name.matches("(?i).+\\.(mp3|m4a|flac|wav|ogg|opus|aac|wma)$");
    }

    String safeDownloadFilename(String filename) {
        String clean = filename == null ? "MusicDesk-download" : filename.replaceAll("[\\\\/:*?\"<>|]", "_").trim();
        return clean.isEmpty() ? "MusicDesk-download" : clean;
    }

    /**
     * Answers the WebView's request for a cached track. WebView itself skips to the start of a
     * requested Range in the returned stream, so the stream is the whole file, cut off after the
     * range's last byte, and the response states the range so the media player can seek.
     */
    private WebResourceResponse serveCachedAudio(WebResourceRequest request) {
        Map<String, String> headers = new HashMap<>();
        headers.put("Access-Control-Allow-Origin", "*");
        headers.put("Access-Control-Allow-Headers", "Range");
        headers.put("Access-Control-Expose-Headers", "Content-Length, Content-Range, Accept-Ranges");
        headers.put("Accept-Ranges", "bytes");
        headers.put("Cache-Control", "no-store");
        if ("OPTIONS".equalsIgnoreCase(request.getMethod())) {
            return new WebResourceResponse("text/plain", "utf-8", 204, "No Content", headers, null);
        }
        try {
            File file = LocalMediaRoutes.resolve(new File(getCacheDir(), "musicdesk-audio"), request.getUrl().getPath());
            if (file == null) {
                return new WebResourceResponse("text/plain", "utf-8", 404, "Not Found", headers, null);
            }
            long length = file.length();
            String rangeHeader = null;
            for (Map.Entry<String, String> entry : request.getRequestHeaders().entrySet()) {
                if ("range".equalsIgnoreCase(entry.getKey())) rangeHeader = entry.getValue();
            }
            String mime = LocalMediaRoutes.mimeType(file.getName());
            if (rangeHeader == null || rangeHeader.trim().isEmpty()) {
                return new WebResourceResponse(mime, null, 200, "OK", headers, new FileInputStream(file));
            }
            long[] range = LocalMediaRoutes.parseRange(rangeHeader, length);
            if (range == null) {
                headers.put("Content-Range", "bytes */" + length);
                return new WebResourceResponse("text/plain", "utf-8", 416, "Range Not Satisfiable", headers, null);
            }
            headers.put("Content-Range", "bytes " + range[0] + "-" + range[1] + "/" + length);
            return new WebResourceResponse(mime, null, 206, "Partial Content", headers,
                    new BoundedInputStream(new FileInputStream(file), range[1] + 1));
        } catch (IOException failure) {
            return new WebResourceResponse("text/plain", "utf-8", 500, "Internal Server Error", headers, null);
        }
    }

    /** Ends the stream after {@code limit} bytes from its start, i.e. at a Range's last byte. */
    private static final class BoundedInputStream extends java.io.FilterInputStream {
        private long remaining;

        BoundedInputStream(InputStream input, long limit) {
            super(input);
            remaining = limit;
        }

        @Override
        public int read() throws IOException {
            if (remaining <= 0) return -1;
            int value = super.read();
            if (value >= 0) remaining--;
            return value;
        }

        @Override
        public int read(byte[] buffer, int offset, int length) throws IOException {
            if (remaining <= 0) return -1;
            int count = super.read(buffer, offset, (int) Math.min(length, remaining));
            if (count > 0) remaining -= count;
            return count;
        }

        @Override
        public long skip(long count) throws IOException {
            long skipped = super.skip(Math.min(count, remaining));
            if (skipped > 0) remaining -= skipped;
            return skipped;
        }

        @Override
        public int available() throws IOException {
            return (int) Math.min(super.available(), remaining);
        }
    }

    String cacheKey(String contentUri) {
        return UUID.nameUUIDFromBytes(contentUri.getBytes(java.nio.charset.StandardCharsets.UTF_8)).toString();
    }

    String readArtwork(Uri source) {
        return readArtwork(source, 512);
    }

    /** Small, disk-cached thumbnail for library rows; empty string when the file has no artwork. */
    String readArtworkThumbnail(String contentUri) {
        File folder = new File(getCacheDir(), "musicdesk-art");
        if (!folder.exists() && !folder.mkdirs()) return readArtwork(Uri.parse(contentUri), 192);
        String key = cacheKey(contentUri);
        File thumb = new File(folder, key + ".jpg");
        File none = new File(folder, key + ".none");
        try {
            if (none.isFile()) return "";
            if (thumb.isFile() && thumb.length() > 0) {
                byte[] bytes = new byte[(int) thumb.length()];
                try (java.io.FileInputStream input = new java.io.FileInputStream(thumb)) {
                    int offset = 0;
                    while (offset < bytes.length) {
                        int count = input.read(bytes, offset, bytes.length - offset);
                        if (count < 0) break;
                        offset += count;
                    }
                }
                return "data:image/jpeg;base64," + android.util.Base64.encodeToString(bytes, android.util.Base64.NO_WRAP);
            }
            String data = readArtwork(Uri.parse(contentUri), 192);
            if (data.isEmpty()) {
                none.createNewFile();
                return "";
            }
            byte[] decoded = android.util.Base64.decode(data.substring(data.indexOf(',') + 1), android.util.Base64.DEFAULT);
            try (FileOutputStream output = new FileOutputStream(thumb)) { output.write(decoded); }
            return data;
        } catch (Exception ignored) {
            return "";
        }
    }

    String readArtwork(Uri source, int maxEdge) {
        MediaMetadataRetriever metadata = new MediaMetadataRetriever();
        try {
            metadata.setDataSource(this, source);
            byte[] embedded = metadata.getEmbeddedPicture();
            if (embedded == null || embedded.length > 8 * 1024 * 1024) return "";
            BitmapFactory.Options bounds = new BitmapFactory.Options();
            bounds.inJustDecodeBounds = true;
            BitmapFactory.decodeByteArray(embedded, 0, embedded.length, bounds);
            int sample = 1;
            while (Math.max(bounds.outWidth / sample, bounds.outHeight / sample) > maxEdge) sample *= 2;
            BitmapFactory.Options options = new BitmapFactory.Options();
            options.inSampleSize = sample;
            Bitmap bitmap = BitmapFactory.decodeByteArray(embedded, 0, embedded.length, options);
            if (bitmap == null) return "";
            ByteArrayOutputStream output = new ByteArrayOutputStream();
            bitmap.compress(Bitmap.CompressFormat.JPEG, 82, output);
            bitmap.recycle();
            return "data:image/jpeg;base64," + android.util.Base64.encodeToString(output.toByteArray(), android.util.Base64.NO_WRAP);
        } catch (RuntimeException ignored) {
            return "";
        } finally {
            try {
                metadata.release();
            } catch (IOException ignored) {
                // Embedded artwork is optional.
            }
        }
    }

    @Override
    protected void onPause() {
        if (webView != null) {
            webView.evaluateJavascript("window.persistAndroidPlayback && window.persistAndroidPlayback(true)", null);
        }
        super.onPause();
    }

    @Override
    protected void onDestroy() {
        folderExecutor.shutdownNow();
        audioExecutor.shutdownNow();
        artworkExecutor.shutdownNow();
        updateExecutor.shutdownNow();
        nativeDownloadExecutor.shutdownNow();
        if (downloadOutput != null) {
            try { downloadOutput.close(); } catch (IOException ignored) {}
            downloadOutput = null;
        }
        if (downloadUri != null) {
            try { DocumentsContract.deleteDocument(getContentResolver(), downloadUri); }
            catch (Exception ignored) { /* Some document providers do not support deletion. */ }
            downloadUri = null;
        }
        File audioCache = new File(getCacheDir(), "musicdesk-audio");
        File[] cachedFiles = audioCache.listFiles();
        if (cachedFiles != null) for (File file : cachedFiles) file.delete();
        audioCache.delete();
        if (fileSelectionCallback != null) {
            fileSelectionCallback.onReceiveValue(null);
            fileSelectionCallback = null;
        }
        if (webView != null) {
            webView.stopLoading();
            webView.destroy();
            webView = null;
        }
        stopService(new Intent(this, MusicPlaybackService.class));
        if (mediaReceiverRegistered) {
            try { unregisterReceiver(mediaCommandReceiver); } catch (IllegalArgumentException ignored) { }
            mediaReceiverRegistered = false;
        }
        super.onDestroy();
    }

    @Override
    @SuppressWarnings("deprecation")
    public void onBackPressed() {
        if (queueOpen && webView != null) {
            queueOpen = false;
            webView.evaluateJavascript("window.closeQueue && window.closeQueue()", null);
            return;
        }
        if (webView != null && webView.canGoBack()) {
            webView.goBack();
            return;
        }
        if (playbackActive) {
            moveTaskToBack(true);
            return;
        }
        super.onBackPressed();
    }
}

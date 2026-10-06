package com.musicdesk.android;

import android.app.Activity;
import android.content.Intent;
import android.content.SharedPreferences;
import android.media.MediaMetadataRetriever;
import android.database.Cursor;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.provider.DocumentsContract;
import android.view.ViewGroup;
import android.webkit.JavascriptInterface;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.webkit.WebResourceRequest;
import android.widget.Toast;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.ByteArrayOutputStream;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.UUID;
import java.util.HashSet;
import java.util.Set;

public final class MainActivity extends Activity {
    private static final int FILE_CHOOSER_REQUEST = 4102;
    private static final int FOLDER_CHOOSER_REQUEST = 4103;
    private static final int DOWNLOAD_DESTINATION_REQUEST = 4104;
    private static final String PREFS_NAME = "musicdesk-library";
    private static final String PREF_SAVED_FOLDERS = "saved-folder-uris";

    private WebView webView;
    private ValueCallback<Uri[]> fileSelectionCallback;
    private OutputStream downloadOutput;
    private Uri downloadUri;
    private volatile boolean queueOpen;
    private final ExecutorService folderExecutor = Executors.newSingleThreadExecutor();

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
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(true);
        settings.setAllowContentAccess(true);
        settings.setAllowFileAccessFromFileURLs(false);
        settings.setAllowUniversalAccessFromFileURLs(false);
        settings.setMediaPlaybackRequiresUserGesture(false);
        settings.setUserAgentString(settings.getUserAgentString() + " MusicDeskAndroid/0.1.0");

        webView.setWebViewClient(new WebViewClient() {
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
        webView.addJavascriptInterface(new AndroidMusicBridge(), "AndroidMusic");
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
        webView.loadUrl("file:///android_asset/index.html");
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        if (requestCode == DOWNLOAD_DESTINATION_REQUEST) {
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
            if (fileSelectionCallback != null) {
                fileSelectionCallback.onReceiveValue(
                        WebChromeClient.FileChooserParams.parseResult(resultCode, data));
                fileSelectionCallback = null;
            }
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

    private void notifyDownloadReady(String error) {
        if (webView == null) return;
        webView.evaluateJavascript("window.onAndroidDownloadReady && window.onAndroidDownloadReady(" + JSONObject.quote(error) + ")", null);
    }

    private JSONArray scanTree(Uri tree) {
        JSONArray results = new JSONArray();
        try {
            String rootId = DocumentsContract.getTreeDocumentId(tree);
            scanDocumentTree(tree, rootId, results, 0, "");
        } catch (RuntimeException ignored) {
            // Return an empty array so the page can show a useful empty-library state.
        }
        return results;
    }

    private void scanFolderAsync(Uri tree) {
        folderExecutor.execute(() -> {
            JSONArray tracks = scanTree(tree);
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
                boolean finished = end == total;
                boolean capped = total >= 5000;
                String script = "window.onAndroidFolderPicked && window.onAndroidFolderPicked(" + payload + "," + finished + "," + capped + ")";
                runOnUiThread(() -> {
                    if (webView != null) webView.evaluateJavascript(script, null);
                });
            }
        });
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
                DocumentsContract.Document.COLUMN_DISPLAY_NAME, DocumentsContract.Document.COLUMN_MIME_TYPE};
        try (Cursor cursor = getContentResolver().query(children, columns, null, null, null)) {
            if (cursor == null) return;
            while (cursor.moveToNext() && results.length() < 5000) {
                String id = cursor.getString(0);
                String name = cursor.getString(1);
                String mime = cursor.getString(2);
                if (DocumentsContract.Document.MIME_TYPE_DIR.equals(mime)) {
                    String childPath = folderPath.isEmpty() ? name : folderPath + "/" + name;
                    scanDocumentTree(tree, id, results, depth + 1, childPath);
                } else if (isAudio(name, mime)) {
                    Uri fileUri = DocumentsContract.buildDocumentUriUsingTree(tree, id);
                    JSONObject track = new JSONObject();
                    try {
                        track.put("uri", fileUri.toString());
                        track.put("name", name);
                        track.put("folderPath", folderPath);
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

    private final class AndroidMusicBridge {
        @JavascriptInterface
        public void pickFolder() {
            runOnUiThread(() -> {
                Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT_TREE);
                intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION);
                startActivityForResult(intent, FOLDER_CHOOSER_REQUEST);
            });
        }

        @JavascriptInterface
        public void restoreFolders() {
            SharedPreferences preferences = getSharedPreferences(PREFS_NAME, MODE_PRIVATE);
            Set<String> saved = new HashSet<>(preferences.getStringSet(PREF_SAVED_FOLDERS, new HashSet<>()));
            if (saved.isEmpty()) return;
            runOnUiThread(() -> {
                if (webView != null) webView.evaluateJavascript(
                        "document.getElementById('androidScopeNote').textContent='正在恢复上次的曲库…';document.getElementById('androidScopeNote').style.display='block'", null);
            });
            for (String value : saved) scanFolderAsync(Uri.parse(value));
        }

        @JavascriptInterface
        public void setQueueOpen(boolean open) {
            queueOpen = open;
        }

        @JavascriptInterface
        public void loadAudio(String contentUri, int index) {
            folderExecutor.execute(() -> {
                String localUri = null;
                String artworkData = "";
                String error = "";
                File cached = null;
                try {
                    Uri source = Uri.parse(contentUri);
                    artworkData = readArtwork(source);
                    String extension = ".audio";
                    String path = source.getLastPathSegment();
                    if (path != null && path.matches("(?i).*\\.(mp3|m4a|flac|wav|ogg|opus|aac|wma)$")) {
                        extension = path.substring(path.lastIndexOf('.'));
                    }
                    File folder = new File(getCacheDir(), "musicdesk-audio");
                    if (!folder.exists() && !folder.mkdirs()) throw new java.io.IOException("无法创建音频缓存目录");
                    cached = new File(folder, cacheKey(contentUri) + extension);
                    if (!cached.isFile() || cached.length() == 0) {
                        try (InputStream input = getContentResolver().openInputStream(source);
                             FileOutputStream output = new FileOutputStream(cached)) {
                            if (input == null) throw new java.io.IOException("无法读取所选音频");
                            byte[] buffer = new byte[64 * 1024];
                            int count;
                            while ((count = input.read(buffer)) != -1) output.write(buffer, 0, count);
                        }
                    }
                    localUri = Uri.fromFile(cached).toString();
                } catch (Exception failure) {
                    if (cached != null) cached.delete();
                    error = failure.getMessage() == null ? "读取音频失败" : failure.getMessage();
                }
                final String resultUri = localUri;
                final String resultError = error;
                String script = "window.onAndroidAudioReady && window.onAndroidAudioReady(" + index + ","
                        + JSONObject.quote(contentUri) + "," + JSONObject.quote(resultUri == null ? "" : resultUri)
                        + "," + JSONObject.quote(resultError) + "," + JSONObject.quote(artworkData) + ")";
                runOnUiThread(() -> {
                    if (webView != null) webView.evaluateJavascript(script, null);
                });
            });
        }

        @JavascriptInterface
        public void releaseAudio(String contentUri) {
            File folder = new File(getCacheDir(), "musicdesk-audio");
            File[] cachedFiles = folder.listFiles();
            if (cachedFiles == null) return;
            for (File file : cachedFiles) {
                if (file.getName().startsWith(cacheKey(contentUri))) file.delete();
            }
        }

        @JavascriptInterface
        public void createDownload(String filename, String mimeType) {
            runOnUiThread(() -> {
                if (downloadOutput != null) cancelDownload();
                Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT);
                intent.addCategory(Intent.CATEGORY_OPENABLE);
                String contentType = mimeType == null ? "" : mimeType.split(";", 2)[0].trim();
                intent.setType(contentType.isEmpty() ? "application/octet-stream" : contentType);
                intent.putExtra(Intent.EXTRA_TITLE, safeDownloadFilename(filename));
                try {
                    startActivityForResult(intent, DOWNLOAD_DESTINATION_REQUEST);
                } catch (RuntimeException error) {
                    notifyDownloadReady("无法打开保存位置选择器。");
                }
            });
        }

        @JavascriptInterface
        public synchronized String writeDownloadChunk(String base64Data) {
            if (downloadOutput == null) return "保存目标已关闭。";
            try {
                byte[] bytes = android.util.Base64.decode(base64Data, android.util.Base64.DEFAULT);
                downloadOutput.write(bytes);
                return "";
            } catch (IOException | IllegalArgumentException error) {
                return "写入下载文件失败：" + error.getMessage();
            }
        }

        @JavascriptInterface
        public synchronized String finishDownload() {
            try {
                if (downloadOutput != null) downloadOutput.close();
                downloadOutput = null;
                downloadUri = null;
                runOnUiThread(() -> Toast.makeText(MainActivity.this, "文件已保存", Toast.LENGTH_SHORT).show());
                return "";
            } catch (IOException error) {
                cancelDownload();
                runOnUiThread(() -> Toast.makeText(MainActivity.this, "保存文件失败", Toast.LENGTH_LONG).show());
                return "保存文件失败：" + error.getMessage();
            }
        }

        @JavascriptInterface
        public synchronized void cancelDownload() {
            try {
                if (downloadOutput != null) downloadOutput.close();
            } catch (IOException ignored) {
                // The canceled or failed download is already unusable.
            }
            downloadOutput = null;
            if (downloadUri != null) {
                try { DocumentsContract.deleteDocument(getContentResolver(), downloadUri); }
                catch (Exception ignored) { /* Some document providers do not support deletion. */ }
                downloadUri = null;
            }
        }
    }

    private String safeDownloadFilename(String filename) {
        String clean = filename == null ? "MusicDesk-download" : filename.replaceAll("[\\\\/:*?\"<>|]", "_").trim();
        return clean.isEmpty() ? "MusicDesk-download" : clean;
    }

    private String cacheKey(String contentUri) {
        return UUID.nameUUIDFromBytes(contentUri.getBytes(java.nio.charset.StandardCharsets.UTF_8)).toString();
    }

    private String readArtwork(Uri source) {
        MediaMetadataRetriever metadata = new MediaMetadataRetriever();
        try {
            metadata.setDataSource(this, source);
            byte[] embedded = metadata.getEmbeddedPicture();
            if (embedded == null || embedded.length > 8 * 1024 * 1024) return "";
            BitmapFactory.Options bounds = new BitmapFactory.Options();
            bounds.inJustDecodeBounds = true;
            BitmapFactory.decodeByteArray(embedded, 0, embedded.length, bounds);
            int sample = 1;
            while (Math.max(bounds.outWidth / sample, bounds.outHeight / sample) > 512) sample *= 2;
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
    protected void onDestroy() {
        folderExecutor.shutdownNow();
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
        super.onBackPressed();
    }
}

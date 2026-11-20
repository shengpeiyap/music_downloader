package com.musicdesk.android;

import android.content.SharedPreferences;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;
import okhttp3.WebSocket;
import okhttp3.WebSocketListener;
import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.util.concurrent.BlockingQueue;
import java.util.concurrent.Executors;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;

/**
 * Optional, opt-in standalone Discord Rich Presence for Android: connects straight to the
 * Discord Gateway with the user's own account token, so phone playback can show a status without
 * pairing to a desktop that has Discord open (see AGENTS.md's Discord section and
 * docs/architecture-plan.md). This never touches desktop/discord_presence.py's local Windows
 * named-pipe IPC and is a different mechanism entirely.
 *
 * Using a personal account token this way (rather than a bot token) is against Discord's Terms
 * of Service for automated/self-bot clients; the user was told this explicitly before opting in,
 * and the token is only ever sent to Discord's own gateway, never anywhere else.
 *
 * All Gateway protocol handling (identify/heartbeat/presence/reconnect) runs serialized on one
 * worker thread via {@link #queue}, so the OkHttp callback threads and the JS bridge thread never
 * touch mutable state directly; only {@link #connected} and {@link #message} are read off-thread
 * (by {@link #statusJson()}), which is why they are {@code volatile}.
 */
final class DiscordPresenceManager {
    private static final String PREFS_NAME = "musicdesk-discord-direct";
    private static final String PREF_TOKEN = "token";
    private static final String GATEWAY_URL = "wss://gateway.discord.gg/?v=10&encoding=json";
    private static final int OP_DISPATCH = 0;
    private static final int OP_HEARTBEAT = 1;
    private static final int OP_IDENTIFY = 2;
    private static final int OP_PRESENCE_UPDATE = 3;
    private static final int OP_RECONNECT = 7;
    private static final int OP_INVALID_SESSION = 9;
    private static final int OP_HELLO = 10;
    private static final int OP_HEARTBEAT_ACK = 11;

    private final MainActivity host;
    private final OkHttpClient httpClient = new OkHttpClient.Builder().retryOnConnectionFailure(true).build();
    private final ScheduledExecutorService scheduler = Executors.newSingleThreadScheduledExecutor();
    private final BlockingQueue<Runnable> queue = new LinkedBlockingQueue<>();
    private final Thread worker;

    // Only touched on the worker thread.
    private WebSocket socket;
    private ScheduledFuture<?> heartbeatTask;
    private ScheduledFuture<?> reconnectTask;
    private boolean heartbeatAckPending;
    private boolean identified;
    private long lastSequence = -1;
    private JSONObject desiredActivity;
    private boolean desiredHasActivity;
    private boolean wantsConnection;

    private volatile boolean connected;
    private volatile String message = "未连接";

    DiscordPresenceManager(MainActivity host) {
        this.host = host;
        this.worker = new Thread(this::runQueue, "MusicDesk-DiscordGateway");
        this.worker.setDaemon(true);
        this.worker.start();
    }

    private SharedPreferences prefs() {
        return host.getSharedPreferences(PREFS_NAME, host.MODE_PRIVATE);
    }

    String token() {
        return prefs().getString(PREF_TOKEN, "");
    }

    boolean hasToken() {
        return !token().isEmpty();
    }

    /** Called from the JS bridge thread. */
    String setToken(String token) {
        String trimmed = token == null ? "" : token.trim();
        if (trimmed.length() < 20) return "Discord 令牌格式不正确。";
        prefs().edit().putString(PREF_TOKEN, trimmed).apply();
        message = "正在连接…";
        enqueue(() -> { wantsConnection = true; reconnect("令牌已更新"); });
        return "";
    }

    /** Called from the JS bridge thread. */
    void clearToken() {
        prefs().edit().remove(PREF_TOKEN).apply();
        message = "已断开";
        connected = false;
        enqueue(() -> { wantsConnection = false; teardown("已断开"); });
    }

    /** Called from the JS bridge thread; a quick snapshot, never blocks on the gateway. */
    String statusJson() {
        JSONObject json = new JSONObject();
        try {
            json.put("connected", connected);
            json.put("message", message);
            json.put("hasToken", hasToken());
        } catch (JSONException ignored) { }
        return json.toString();
    }

    /** Called from the JS bridge thread with the same payload shape the PC relay uses. */
    void update(JSONObject payload) {
        if (!payload.optBoolean("enabled", true)) {
            message = "已关闭";
            connected = false;
            enqueue(() -> { wantsConnection = false; teardown("已关闭"); });
            return;
        }
        if (!hasToken()) return;
        JSONObject activity = buildActivity(payload);
        enqueue(() -> {
            desiredActivity = activity;
            desiredHasActivity = true;
            wantsConnection = true;
            if (socket == null) connectNow();
            else if (identified) sendPresenceUpdate(activity);
        });
    }

    void close() {
        enqueue(() -> { wantsConnection = false; teardown("已关闭"); });
        scheduler.shutdownNow();
        worker.interrupt();
    }

    private void enqueue(Runnable task) {
        queue.add(task);
    }

    private void runQueue() {
        while (true) {
            try {
                queue.take().run();
            } catch (InterruptedException stop) {
                return;
            } catch (Exception unexpected) {
                message = "Discord 连接出现内部错误";
            }
        }
    }

    // --- Worker-thread-only state machine below ---

    private void connectNow() {
        teardownSocket();
        identified = false;
        heartbeatAckPending = false;
        lastSequence = -1;
        String currentToken = token();
        if (currentToken.isEmpty()) {
            message = "未连接";
            return;
        }
        message = "正在连接…";
        Request request = new Request.Builder().url(GATEWAY_URL).build();
        socket = httpClient.newWebSocket(request, new GatewayListener());
    }

    private void reconnect(String reason) {
        if (reconnectTask != null) reconnectTask.cancel(false);
        teardownSocket();
        if (!wantsConnection) {
            message = reason;
            return;
        }
        message = reason + "；正在重新连接…";
        connectNow();
    }

    private void teardown(String statusMessage) {
        if (reconnectTask != null) { reconnectTask.cancel(false); reconnectTask = null; }
        teardownSocket();
        message = statusMessage;
        connected = false;
    }

    private void teardownSocket() {
        if (heartbeatTask != null) { heartbeatTask.cancel(false); heartbeatTask = null; }
        if (socket != null) {
            WebSocket closing = socket;
            socket = null;
            try { closing.close(1000, "MusicDesk 已断开"); } catch (Exception ignored) { }
        }
        identified = false;
        connected = false;
    }

    private void scheduleReconnect(String reason) {
        // The remote socket is already closed/closing; just drop our reference and stop beating,
        // without calling WebSocket.close() again on something that is going away on its own.
        if (heartbeatTask != null) { heartbeatTask.cancel(false); heartbeatTask = null; }
        socket = null;
        identified = false;
        connected = false;
        if (!wantsConnection) {
            message = reason;
            return;
        }
        message = reason + "；5 秒后重试";
        if (reconnectTask != null) reconnectTask.cancel(false);
        reconnectTask = scheduler.schedule(() -> enqueue(() -> reconnect(reason)), 5, TimeUnit.SECONDS);
    }

    private void handleHello(JSONObject data) {
        int intervalMs = data.optInt("heartbeat_interval", 41250);
        if (heartbeatTask != null) heartbeatTask.cancel(false);
        heartbeatAckPending = false;
        // Jitter the first beat as Discord's own docs recommend, then beat on a fixed interval.
        long firstDelay = Math.round(intervalMs * Math.random());
        heartbeatTask = scheduler.scheduleAtFixedRate(() -> enqueue(this::sendHeartbeat),
                firstDelay, intervalMs, TimeUnit.MILLISECONDS);
        sendIdentify();
    }

    private void sendIdentify() {
        WebSocket active = socket;
        if (active == null) return;
        try {
            JSONObject properties = new JSONObject()
                    .put("os", "android")
                    .put("browser", "MusicDesk")
                    .put("device", "MusicDesk");
            JSONObject data = new JSONObject()
                    .put("token", token())
                    .put("properties", properties)
                    .put("compress", false)
                    .put("large_threshold", 50);
            JSONObject frame = new JSONObject().put("op", OP_IDENTIFY).put("d", data);
            active.send(frame.toString());
        } catch (JSONException ignored) { }
    }

    private void sendHeartbeat() {
        WebSocket active = socket;
        if (active == null) return;
        if (heartbeatAckPending) {
            // Discord never acked the previous beat: the connection is a zombie, per Discord's docs.
            scheduleReconnect("Discord 连接无响应");
            return;
        }
        heartbeatAckPending = true;
        try {
            JSONObject frame = new JSONObject().put("op", OP_HEARTBEAT)
                    .put("d", lastSequence < 0 ? JSONObject.NULL : lastSequence);
            active.send(frame.toString());
        } catch (JSONException ignored) { }
    }

    private void sendPresenceUpdate(JSONObject activity) {
        WebSocket active = socket;
        if (active == null || !identified) return;
        try {
            JSONArray activities = new JSONArray();
            if (activity != null) activities.put(activity);
            JSONObject data = new JSONObject()
                    .put("since", JSONObject.NULL)
                    .put("activities", activities)
                    .put("status", "online")
                    .put("afk", false);
            JSONObject frame = new JSONObject().put("op", OP_PRESENCE_UPDATE).put("d", data);
            active.send(frame.toString());
        } catch (JSONException ignored) { }
    }

    private void handleDispatch(String event, JSONObject data) {
        if ("READY".equals(event)) {
            identified = true;
            connected = true;
            message = desiredHasActivity ? "已连接并正在分享播放状态" : "已连接；播放歌曲时显示状态";
            if (desiredHasActivity) sendPresenceUpdate(desiredActivity);
        }
    }

    private void handleFrame(JSONObject frame) {
        int op = frame.optInt("op", -1);
        JSONObject data = frame.optJSONObject("d");
        if (!frame.isNull("s")) lastSequence = frame.optLong("s", lastSequence);
        switch (op) {
            case OP_HELLO:
                handleHello(data == null ? new JSONObject() : data);
                break;
            case OP_HEARTBEAT_ACK:
                heartbeatAckPending = false;
                break;
            case OP_HEARTBEAT:
                sendHeartbeat();
                break;
            case OP_DISPATCH:
                handleDispatch(frame.optString("t", ""), data == null ? new JSONObject() : data);
                break;
            case OP_RECONNECT:
                scheduleReconnect("Discord 请求重新连接");
                break;
            case OP_INVALID_SESSION:
                scheduleReconnect("Discord 会话已失效");
                break;
            default:
                break;
        }
    }

    /** Builds the Rich Presence activity Discord shows, or null for "connected, nothing playing". */
    private static JSONObject buildActivity(JSONObject payload) {
        if (!payload.optBoolean("has_track", false)) return null;
        boolean shareDetails = payload.optBoolean("share_details", true);
        String title = payload.optString("title", "").trim();
        String artist = payload.optString("artist", "").trim();
        double duration = payload.optDouble("duration", 0);
        double position = payload.optDouble("position", 0);
        boolean isPlaying = payload.optBoolean("playing", false) && duration > 0;
        try {
            JSONObject activity = new JSONObject();
            // Unlike the local-IPC path Discord uses for the desktop app (where the app-name
            // banner always comes from the registered application, not our payload), a Gateway
            // presence's "name" field IS the banner text, so this is where artist/title can
            // actually replace "MusicDesk" on screen.
            String name = "MusicDesk";
            if (shareDetails) {
                if (!artist.isEmpty() && !title.isEmpty()) name = artist + " - " + title;
                else if (!title.isEmpty()) name = title;
                else if (!artist.isEmpty()) name = artist;
            }
            activity.put("name", name);
            activity.put("type", 2); // Discord ActivityType.LISTENING
            String appId = payload.optString("application_id", "");
            if (appId.matches("\\d{17,20}")) activity.put("application_id", appId);
            if (shareDetails) {
                if (!title.isEmpty()) activity.put("details", title);
                if (!artist.isEmpty()) activity.put("state", isPlaying ? artist : ("已暂停 · " + artist));
                else if (!isPlaying) activity.put("state", "已暂停");
            }
            if (isPlaying) {
                long now = System.currentTimeMillis();
                long start = now - Math.round(position * 1000);
                JSONObject timestamps = new JSONObject().put("start", start).put("end", start + Math.round(duration * 1000));
                activity.put("timestamps", timestamps);
            }
            return activity;
        } catch (JSONException impossible) {
            return null;
        }
    }

    private final class GatewayListener extends WebSocketListener {
        @Override
        public void onMessage(WebSocket webSocket, String text) {
            enqueue(() -> {
                if (webSocket != socket) return; // Stale callback from a socket we already replaced.
                try { handleFrame(new JSONObject(text)); } catch (JSONException ignored) { }
            });
        }

        @Override
        public void onClosed(WebSocket webSocket, int code, String reason) {
            enqueue(() -> {
                if (webSocket != socket) return;
                scheduleReconnect(describeCloseCode(code));
            });
        }

        @Override
        public void onFailure(WebSocket webSocket, Throwable t, Response response) {
            enqueue(() -> {
                if (webSocket != socket) return;
                String reason = t.getMessage() == null ? "Discord 连接失败" : t.getMessage();
                scheduleReconnect(reason);
            });
        }
    }

    private static String describeCloseCode(int code) {
        switch (code) {
            case 4004: return "Discord 令牌无效或已过期";
            case 4003: return "尚未向 Discord 完成认证";
            case 4009: return "Discord 会话超时";
            case 4014: return "缺少必要的网关权限";
            default: return "Discord 连接已关闭";
        }
    }
}

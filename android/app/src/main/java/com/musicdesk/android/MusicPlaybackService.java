package com.musicdesk.android;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.media.MediaMetadata;
import android.media.session.MediaSession;
import android.media.session.PlaybackState;
import android.os.Build;
import android.os.IBinder;
import android.util.Base64;

public final class MusicPlaybackService extends Service {
    public static final String ACTION_UPDATE = "com.musicdesk.android.UPDATE_PLAYBACK";
    public static final String ACTION_MEDIA_COMMAND = "com.musicdesk.android.MEDIA_COMMAND";
    public static final String ACTION_STOP = "com.musicdesk.android.STOP_PLAYBACK";
    public static final String EXTRA_COMMAND = "command";
    public static final String EXTRA_TITLE = "title";
    public static final String EXTRA_ARTIST = "artist";
    public static final String EXTRA_ALBUM = "album";
    public static final String EXTRA_PLAYING = "playing";
    public static final String EXTRA_POSITION = "position";
    public static final String EXTRA_DURATION = "duration";
    public static final String EXTRA_ARTWORK = "artwork";

    private static final String CHANNEL_ID = "musicdesk-playback";
    private static final int NOTIFICATION_ID = 7101;
    private MediaSession mediaSession;
    private String title = "MusicDesk";
    private String artist = "本地音乐播放器";
    private String album = "";
    private String artwork = "";
    private long position;
    private long duration;
    private boolean playing;

    @Override public void onCreate() {
        super.onCreate();
        createNotificationChannel();
        mediaSession = new MediaSession(this, "MusicDesk");
        mediaSession.setFlags(MediaSession.FLAG_HANDLES_MEDIA_BUTTONS | MediaSession.FLAG_HANDLES_TRANSPORT_CONTROLS);
        mediaSession.setCallback(new MediaSession.Callback() {
            @Override public void onPlay() { sendCommand("play"); }
            @Override public void onPause() { sendCommand("pause"); }
            @Override public void onSkipToNext() { sendCommand("next"); }
            @Override public void onSkipToPrevious() { sendCommand("previous"); }
        });
        mediaSession.setActive(true);
    }

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent == null) return START_NOT_STICKY;
        String action = intent.getAction();
        if (ACTION_STOP.equals(action)) {
            stopForeground(true);
            stopSelf();
            return START_NOT_STICKY;
        }
        if (ACTION_UPDATE.equals(action)) {
            title = intent.getStringExtra(EXTRA_TITLE) == null ? "未知标题" : intent.getStringExtra(EXTRA_TITLE);
            artist = intent.getStringExtra(EXTRA_ARTIST) == null ? "未知歌手" : intent.getStringExtra(EXTRA_ARTIST);
            album = intent.getStringExtra(EXTRA_ALBUM) == null ? "" : intent.getStringExtra(EXTRA_ALBUM);
            artwork = intent.getStringExtra(EXTRA_ARTWORK) == null ? "" : intent.getStringExtra(EXTRA_ARTWORK);
            playing = intent.getBooleanExtra(EXTRA_PLAYING, false);
            position = Math.max(0, (long) (intent.getDoubleExtra(EXTRA_POSITION, 0) * 1000));
            duration = Math.max(0, (long) (intent.getDoubleExtra(EXTRA_DURATION, 0) * 1000));
            updateSession();
            Notification notification = buildNotification();
            if (Build.VERSION.SDK_INT >= 29) startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK);
            else startForeground(NOTIFICATION_ID, notification);
            if (!playing && Build.VERSION.SDK_INT >= 24) stopForeground(STOP_FOREGROUND_DETACH);
        } else if (action != null && action.startsWith("com.musicdesk.android.CONTROL.")) {
            sendCommand(action.substring("com.musicdesk.android.CONTROL.".length()).toLowerCase());
        }
        return START_STICKY;
    }

    private void updateSession() {
        MediaMetadata.Builder metadata = new MediaMetadata.Builder()
                .putString(MediaMetadata.METADATA_KEY_TITLE, title)
                .putString(MediaMetadata.METADATA_KEY_ARTIST, artist)
                .putString(MediaMetadata.METADATA_KEY_ALBUM, album)
                .putLong(MediaMetadata.METADATA_KEY_DURATION, duration);
        Bitmap cover = decodeArtwork(artwork);
        if (cover != null) metadata.putBitmap(MediaMetadata.METADATA_KEY_ART, cover);
        mediaSession.setMetadata(metadata.build());
        long actions = PlaybackState.ACTION_PLAY | PlaybackState.ACTION_PAUSE
                | PlaybackState.ACTION_PLAY_PAUSE | PlaybackState.ACTION_SKIP_TO_NEXT
                | PlaybackState.ACTION_SKIP_TO_PREVIOUS;
        mediaSession.setPlaybackState(new PlaybackState.Builder().setActions(actions)
                .setState(playing ? PlaybackState.STATE_PLAYING : PlaybackState.STATE_PAUSED, position, playing ? 1f : 0f)
                .build());
    }

    private Bitmap decodeArtwork(String dataUrl) {
        int comma = dataUrl.indexOf(',');
        if (comma < 0 || !dataUrl.substring(0, comma).contains("base64")) return null;
        try {
            byte[] bytes = Base64.decode(dataUrl.substring(comma + 1), Base64.DEFAULT);
            BitmapFactory.Options bounds = new BitmapFactory.Options();
            bounds.inJustDecodeBounds = true;
            BitmapFactory.decodeByteArray(bytes, 0, bytes.length, bounds);
            int sample = 1;
            while (Math.max(bounds.outWidth / sample, bounds.outHeight / sample) > 512) sample *= 2;
            BitmapFactory.Options options = new BitmapFactory.Options();
            options.inSampleSize = sample;
            return BitmapFactory.decodeByteArray(bytes, 0, bytes.length, options);
        } catch (IllegalArgumentException ignored) { return null; }
    }

    private Notification buildNotification() {
        Intent openIntent = new Intent(this, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        PendingIntent content = PendingIntent.getActivity(this, 1, openIntent, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        Notification.Builder builder = Build.VERSION.SDK_INT >= 26
                ? new Notification.Builder(this, CHANNEL_ID) : new Notification.Builder(this);
        builder.setSmallIcon(R.drawable.ic_stat_music).setContentTitle(title).setContentText(artist)
                .setContentIntent(content).setOnlyAlertOnce(true).setOngoing(playing)
                .setCategory(Notification.CATEGORY_TRANSPORT).setVisibility(Notification.VISIBILITY_PUBLIC)
                .addAction(action("previous", "上一首", android.R.drawable.ic_media_previous))
                .addAction(action(playing ? "pause" : "play", playing ? "暂停" : "播放",
                        playing ? android.R.drawable.ic_media_pause : android.R.drawable.ic_media_play))
                .addAction(action("next", "下一首", android.R.drawable.ic_media_next));
        if (Build.VERSION.SDK_INT >= 24 && !album.isEmpty()) builder.setSubText(album);
        Bitmap cover = decodeArtwork(artwork);
        if (cover != null) builder.setLargeIcon(cover);
        if (Build.VERSION.SDK_INT >= 21) builder.setStyle(new Notification.MediaStyle()
                .setMediaSession(mediaSession.getSessionToken()).setShowActionsInCompactView(0, 1, 2));
        return builder.build();
    }

    private Notification.Action action(String command, String label, int icon) {
        Intent intent = new Intent(this, MusicPlaybackService.class)
                .setAction("com.musicdesk.android.CONTROL." + command.toUpperCase());
        PendingIntent pending = PendingIntent.getService(this, command.hashCode(), intent,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        return new Notification.Action.Builder(icon, label, pending).build();
    }

    private void sendCommand(String command) {
        Intent intent = new Intent(ACTION_MEDIA_COMMAND).setPackage(getPackageName()).putExtra(EXTRA_COMMAND, command);
        sendBroadcast(intent);
    }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT < 26) return;
        NotificationChannel channel = new NotificationChannel(CHANNEL_ID, "MusicDesk 播放控制", NotificationManager.IMPORTANCE_LOW);
        channel.setDescription("显示当前播放歌曲并提供耳机和通知栏控制");
        NotificationManager manager = getSystemService(NotificationManager.class);
        if (manager != null) manager.createNotificationChannel(channel);
    }

    @Override public IBinder onBind(Intent intent) { return null; }

    @Override public void onDestroy() {
        if (mediaSession != null) {
            mediaSession.setActive(false);
            mediaSession.release();
            mediaSession = null;
        }
        super.onDestroy();
    }
}

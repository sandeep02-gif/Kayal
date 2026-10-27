package com.shutterstrokes.kayal;

import android.Manifest;
import android.content.ComponentName;
import android.content.ContentResolver;
import android.content.Context;
import android.content.Intent;
import android.database.Cursor;
import android.media.MediaMetadataRetriever;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.OpenableColumns;
import android.util.Base64;

import androidx.activity.result.ActivityResult;
import androidx.media3.common.MediaItem;
import androidx.media3.common.MediaMetadata;
import androidx.media3.common.MimeTypes;
import androidx.media3.common.PlaybackException;
import androidx.media3.common.Player;
import androidx.media3.session.MediaController;
import androidx.media3.session.SessionCommand;
import androidx.media3.session.SessionToken;

import com.getcapacitor.JSArray;
import com.getcapacitor.JSObject;
import com.getcapacitor.PermissionState;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.ActivityCallback;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.getcapacitor.annotation.Permission;
import com.getcapacitor.annotation.PermissionCallback;
import com.google.common.util.concurrent.ListenableFuture;
import com.google.common.util.concurrent.MoreExecutors;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.io.FileOutputStream;
import java.util.ArrayList;
import java.util.List;

/**
 * Capacitor bridge to the native Media3 player (KayalPlaybackService).
 * JS -> native: load / play / pause / stop / seekTo / setVolume / setMetadata / setQueue / next / previous /
 *               setEq / pickAudio / writeCache / requestNotifications / getState
 * native -> JS events: "state" (snapshot) and "action" ({action:'nexttrack'|'previoustrack'}).
 */
@CapacitorPlugin(
        name = "KayalPlayer",
        permissions = { @Permission(alias = "notifications", strings = { Manifest.permission.POST_NOTIFICATIONS }) })
public class KayalPlayerPlugin extends Plugin {
    private final Handler main = new Handler(Looper.getMainLooper());
    private MediaController ctrl;
    private ListenableFuture<MediaController> fut;
    private final List<Runnable> pending = new ArrayList<>();
    private float volume = 1f;
    private boolean muted = false;
    private String lastError = "";

    private final Runnable ticker = new Runnable() {
        @Override public void run() {
            if (ctrl != null && ctrl.isPlaying()) { emitState(); main.postDelayed(this, 500); }
        }
    };

    private final Player.Listener listener = new Player.Listener() {
        @Override public void onIsPlayingChanged(boolean p) { emitState(); main.removeCallbacks(ticker); if (p) main.postDelayed(ticker, 500); }
        @Override public void onPlaybackStateChanged(int s) { emitState(); }
        @Override public void onPlayWhenReadyChanged(boolean w, int r) { emitState(); }
        @Override public void onMediaItemTransition(MediaItem m, int r) { emitState(); }
        @Override public void onPositionDiscontinuity(Player.PositionInfo a, Player.PositionInfo b, int r) { emitState(); }
        @Override public void onPlayerError(PlaybackException e) {
            lastError = e.getErrorCodeName() + (e.getCause() != null ? ": " + e.getCause().getMessage() : "");
            emitState();
        }
    };

    @Override
    public void load() {
        KayalPlaybackService.actionListener = a -> main.post(() -> {
            JSObject o = new JSObject();
            o.put("action", a);
            notifyListeners("action", o);
        });
        main.post(this::connect);
    }

    @Override
    protected void handleOnDestroy() {
        KayalPlaybackService.actionListener = null;
        main.removeCallbacks(ticker);
        if (ctrl != null) { ctrl.removeListener(listener); }
        if (fut != null) MediaController.releaseFuture(fut);
        ctrl = null; fut = null;
    }

    /* ---------- controller plumbing ---------- */
    private void connect() {
        if (fut != null) return;
        SessionToken token = new SessionToken(getContext(), new ComponentName(getContext(), KayalPlaybackService.class));
        fut = new MediaController.Builder(getContext(), token).buildAsync();
        fut.addListener(() -> {
            try {
                ctrl = fut.get();
                ctrl.addListener(listener);
                ctrl.setVolume(muted ? 0f : volume);
                List<Runnable> run = new ArrayList<>(pending);
                pending.clear();
                for (Runnable r : run) r.run();
                emitState();
            } catch (Exception e) {
                lastError = "controller: " + e.getMessage();
                fut = null;
            }
        }, MoreExecutors.directExecutor());
    }

    /** Runs on the main thread once the MediaController is connected (starts the service if needed). */
    private void withCtrl(Runnable r) {
        main.post(() -> {
            if (ctrl != null) { r.run(); return; }
            pending.add(r);
            connect();
        });
    }

    private JSObject snapshot() {
        JSObject o = new JSObject();
        if (ctrl == null) { o.put("state", "idle"); o.put("playing", false); o.put("playWhenReady", false); o.put("position", 0); o.put("duration", 0); return o; }
        int st = ctrl.getPlaybackState();
        o.put("state", st == Player.STATE_BUFFERING ? "buffering" : st == Player.STATE_READY ? "ready" : st == Player.STATE_ENDED ? "ended" : "idle");
        o.put("playing", ctrl.isPlaying());
        o.put("playWhenReady", ctrl.getPlayWhenReady());
        o.put("position", Math.max(0, ctrl.getCurrentPosition()) / 1000.0);
        long d = ctrl.getDuration();
        o.put("duration", d == androidx.media3.common.C.TIME_UNSET ? 0 : d / 1000.0);
        o.put("index", ctrl.getCurrentMediaItemIndex());
        o.put("count", ctrl.getMediaItemCount());
        o.put("uri", ctrl.getCurrentMediaItem() != null && ctrl.getCurrentMediaItem().localConfiguration != null
                ? ctrl.getCurrentMediaItem().localConfiguration.uri.toString() : "");
        o.put("error", lastError);
        return o;
    }

    private void emitState() { notifyListeners("state", snapshot()); }

    private MediaItem buildItem(JSONObject j) {
        MediaMetadata.Builder md = new MediaMetadata.Builder()
                .setTitle(j.optString("title", ""))
                .setArtist(j.optString("artist", ""))
                .setAlbumTitle(j.optString("album", ""))
                .setIsPlayable(true);
        String art = j.optString("artwork", "");
        if (art.startsWith("http") || art.startsWith("content:") || art.startsWith("file:")) md.setArtworkUri(Uri.parse(art));
        MediaItem.Builder b = new MediaItem.Builder().setUri(j.optString("url")).setMediaMetadata(md.build());
        if (j.optString("id", "").length() > 0) b.setMediaId(j.optString("id"));
        if (j.optBoolean("hls", false)) b.setMimeType(MimeTypes.APPLICATION_M3U8);
        return b.build();
    }

    private JSONObject callJson(PluginCall c) {
        try { return new JSONObject(c.getData().toString()); } catch (Exception e) { return new JSONObject(); }
    }

    /* ---------- JS API ---------- */
    @PluginMethod
    public void load(PluginCall call) {
        final JSONObject j = callJson(call);
        if (j.optString("url", "").isEmpty()) { call.reject("url required"); return; }
        withCtrl(() -> {
            lastError = "";
            ctrl.setMediaItem(buildItem(j), (long) (j.optDouble("startAt", 0) * 1000));
            ctrl.prepare();
            ctrl.setPlayWhenReady(j.optBoolean("autoplay", true));
            call.resolve(snapshot());
        });
    }

    @PluginMethod
    public void setQueue(PluginCall call) {
        final JSONObject j = callJson(call);
        withCtrl(() -> {
            try {
                JSONArray arr = j.getJSONArray("items");
                List<MediaItem> items = new ArrayList<>();
                for (int i = 0; i < arr.length(); i++) items.add(buildItem(arr.getJSONObject(i)));
                lastError = "";
                ctrl.setMediaItems(items, Math.max(0, j.optInt("index", 0)), (long) (j.optDouble("startAt", 0) * 1000));
                ctrl.prepare();
                ctrl.setPlayWhenReady(j.optBoolean("autoplay", true));
                call.resolve(snapshot());
            } catch (Exception e) { call.reject("bad queue: " + e.getMessage()); }
        });
    }

    @PluginMethod public void play(PluginCall call) { withCtrl(() -> { if (ctrl.getPlaybackState() == Player.STATE_ENDED) ctrl.seekTo(0); ctrl.play(); call.resolve(snapshot()); }); }
    @PluginMethod public void pause(PluginCall call) { withCtrl(() -> { ctrl.pause(); call.resolve(snapshot()); }); }
    @PluginMethod public void stop(PluginCall call) { withCtrl(() -> { ctrl.stop(); ctrl.clearMediaItems(); call.resolve(snapshot()); }); }
    @PluginMethod public void next(PluginCall call) { withCtrl(() -> { if (ctrl.hasNextMediaItem()) ctrl.seekToNextMediaItem(); call.resolve(snapshot()); }); }
    @PluginMethod public void previous(PluginCall call) { withCtrl(() -> { if (ctrl.hasPreviousMediaItem()) ctrl.seekToPreviousMediaItem(); call.resolve(snapshot()); }); }
    @PluginMethod public void getState(PluginCall call) { withCtrl(() -> call.resolve(snapshot())); }

    @PluginMethod
    public void seekTo(PluginCall call) {
        final double pos = call.getDouble("position", 0.0);
        withCtrl(() -> { ctrl.seekTo((long) (pos * 1000)); emitState(); call.resolve(); });
    }

    @PluginMethod
    public void setVolume(PluginCall call) {
        volume = (float) Math.max(0, Math.min(1, call.getDouble("volume", 1.0)));
        muted = call.getBoolean("muted", false);
        withCtrl(() -> { ctrl.setVolume(muted ? 0f : volume); call.resolve(); });
    }

    /** Update title/artist/artwork of the current item without interrupting playback. */
    @PluginMethod
    public void setMetadata(PluginCall call) {
        final JSONObject j = callJson(call);
        withCtrl(() -> {
            if (ctrl.getMediaItemCount() == 0) { call.resolve(); return; }
            MediaItem cur = ctrl.getCurrentMediaItem();
            MediaMetadata.Builder md = (cur != null ? cur.mediaMetadata : MediaMetadata.EMPTY).buildUpon()
                    .setTitle(j.optString("title", "")).setArtist(j.optString("artist", ""))
                    .setAlbumTitle(j.optString("album", ""));
            String art = j.optString("artwork", "");
            if (art.startsWith("http") || art.startsWith("content:") || art.startsWith("file:")) md.setArtworkUri(Uri.parse(art));
            if (cur != null) ctrl.replaceMediaItem(ctrl.getCurrentMediaItemIndex(), cur.buildUpon().setMediaMetadata(md.build()).build());
            call.resolve();
        });
    }

    /** Native equaliser: {on, gains:[10 dB], pre}. Resolves {supported}. */
    @PluginMethod
    public void setEq(PluginCall call) {
        final JSONObject j = callJson(call);
        withCtrl(() -> {
            Bundle b = new Bundle();
            b.putBoolean("on", j.optBoolean("on", false));
            float[] g = new float[10];
            JSONArray a = j.optJSONArray("gains");
            for (int i = 0; i < 10; i++) g[i] = a != null ? (float) a.optDouble(i, 0) : 0f;
            b.putFloatArray("gains", g);
            b.putFloat("pre", (float) j.optDouble("pre", 0));
            ListenableFuture<androidx.media3.session.SessionResult> f = ctrl.sendCustomCommand(new SessionCommand(KayalPlaybackService.CMD_EQ, Bundle.EMPTY), b);
            f.addListener(() -> {
                JSObject o = new JSObject();
                try { o.put("supported", f.get().extras.getBoolean("supported", false)); } catch (Exception e) { o.put("supported", false); }
                call.resolve(o);
            }, MoreExecutors.directExecutor());
        });
    }

    /* ---------- notification permission (Android 13+) ---------- */
    @PluginMethod
    public void requestNotifications(PluginCall call) {
        if (Build.VERSION.SDK_INT < 33 || getPermissionState("notifications") == PermissionState.GRANTED) {
            JSObject o = new JSObject(); o.put("granted", true); call.resolve(o); return;
        }
        requestPermissionForAlias("notifications", call, "notifCb");
    }

    @PermissionCallback
    private void notifCb(PluginCall call) {
        JSObject o = new JSObject();
        o.put("granted", getPermissionState("notifications") == PermissionState.GRANTED);
        call.resolve(o);
    }

    /* ---------- local music: system file picker (SAF, no storage permission needed) ---------- */
    @PluginMethod
    public void pickAudio(PluginCall call) {
        Intent it = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        it.addCategory(Intent.CATEGORY_OPENABLE);
        it.setType("audio/*");
        it.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true);
        it.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION);
        startActivityForResult(call, it, "pickResult");
    }

    @ActivityCallback
    private void pickResult(PluginCall call, ActivityResult res) {
        JSObject out = new JSObject();
        JSArray files = new JSArray();
        out.put("files", files);
        if (call == null) return;
        if (res.getResultCode() != android.app.Activity.RESULT_OK || res.getData() == null) { call.resolve(out); return; }
        Intent d = res.getData();
        List<Uri> uris = new ArrayList<>();
        if (d.getClipData() != null) for (int i = 0; i < d.getClipData().getItemCount(); i++) uris.add(d.getClipData().getItemAt(i).getUri());
        else if (d.getData() != null) uris.add(d.getData());
        Context ctx = getContext();
        for (Uri u : uris) {
            try { ctx.getContentResolver().takePersistableUriPermission(u, Intent.FLAG_GRANT_READ_URI_PERMISSION); } catch (Exception ignored) { }
            JSObject f = new JSObject();
            f.put("uri", u.toString());
            String name = displayName(ctx.getContentResolver(), u);
            String title = null, artist = null, album = null; double dur = 0;
            MediaMetadataRetriever r = new MediaMetadataRetriever();
            try {
                r.setDataSource(ctx, u);
                title = r.extractMetadata(MediaMetadataRetriever.METADATA_KEY_TITLE);
                artist = r.extractMetadata(MediaMetadataRetriever.METADATA_KEY_ARTIST);
                album = r.extractMetadata(MediaMetadataRetriever.METADATA_KEY_ALBUM);
                String ds = r.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION);
                if (ds != null) dur = Long.parseLong(ds) / 1000.0;
            } catch (Exception ignored) { } finally { try { r.release(); } catch (Exception ignored) { } }
            if (title == null || title.trim().isEmpty()) title = name != null ? name.replaceAll("\\.[A-Za-z0-9]{2,5}$", "") : "Unknown";
            f.put("title", title); f.put("artist", artist == null ? "" : artist); f.put("album", album == null ? "" : album);
            f.put("duration", dur); f.put("name", name == null ? "" : name);
            files.put(f);
        }
        call.resolve(out);
    }

    private String displayName(ContentResolver cr, Uri u) {
        try (Cursor c = cr.query(u, new String[]{OpenableColumns.DISPLAY_NAME}, null, null, null)) {
            if (c != null && c.moveToFirst()) return c.getString(0);
        } catch (Exception ignored) { }
        return u.getLastPathSegment();
    }

    /* ---------- blob: sources (offline-saved songs live in IndexedDB) -> cache file the native player can open ---------- */
    @PluginMethod
    public void writeCache(PluginCall call) {
        try {
            String name = call.getString("name", "track").replaceAll("[^A-Za-z0-9._-]", "_");
            File dir = new File(getContext().getCacheDir(), "native-audio");
            if (!dir.exists()) dir.mkdirs();
            File f = new File(dir, name);
            boolean append = call.getBoolean("append", false);
            try (FileOutputStream os = new FileOutputStream(f, append)) { os.write(Base64.decode(call.getString("data", ""), Base64.DEFAULT)); }
            JSObject o = new JSObject();
            o.put("uri", Uri.fromFile(f).toString());
            call.resolve(o);
        } catch (Exception e) { call.reject("cache write failed: " + e.getMessage()); }
    }

    @PluginMethod
    public void clearCache(PluginCall call) {
        File dir = new File(getContext().getCacheDir(), "native-audio");
        File[] fs = dir.listFiles();
        if (fs != null) for (File f : fs) f.delete();
        call.resolve();
    }
}

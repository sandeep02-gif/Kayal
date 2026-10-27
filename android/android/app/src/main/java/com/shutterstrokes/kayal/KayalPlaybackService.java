package com.shutterstrokes.kayal;

import android.app.PendingIntent;
import android.content.Intent;
import android.media.audiofx.Equalizer;
import android.os.Bundle;

import androidx.annotation.Nullable;
import androidx.media3.common.AudioAttributes;
import androidx.media3.common.C;
import androidx.media3.common.ForwardingPlayer;
import androidx.media3.common.Player;
import androidx.media3.datasource.DataSource;
import androidx.media3.datasource.DefaultDataSource;
import androidx.media3.datasource.DefaultHttpDataSource;
import androidx.media3.exoplayer.ExoPlayer;
import androidx.media3.exoplayer.source.DefaultMediaSourceFactory;
import androidx.media3.session.MediaSession;
import androidx.media3.session.MediaSessionService;
import androidx.media3.session.SessionCommand;
import androidx.media3.session.SessionResult;

import com.google.common.util.concurrent.Futures;
import com.google.common.util.concurrent.ListenableFuture;

/**
 * Kayal's native audio engine: an ExoPlayer wrapped in a Media3 MediaSessionService.
 * Media3 provides the foreground service, the media notification (play/pause/next/previous/seek),
 * the lock-screen / Bluetooth / Android Auto controls and audio focus. The WebView UI talks to it
 * through KayalPlayerPlugin (a MediaController).
 *
 * Kayal's queue lives in JavaScript (tracks are resolved lazily), so when the native playlist has
 * no next/previous item the notification's skip buttons are forwarded to JS as "nexttrack" /
 * "previoustrack" actions instead.
 */
public class KayalPlaybackService extends MediaSessionService {
    public static final String CMD_EQ = "kayal.eq";

    public interface ActionListener { void onAction(String action); }
    /** Set by KayalPlayerPlugin; skip requests are delivered here (same process). */
    public static volatile ActionListener actionListener;

    private ExoPlayer exo;
    private MediaSession session;
    private Equalizer eq;
    private int eqSession = C.AUDIO_SESSION_ID_UNSET;
    private boolean eqOn = false;
    private float[] eqGains = new float[10];
    private float eqPre = 0f;
    private static final float[] KAYAL_HZ = {31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000};

    private static void fire(String a) {
        ActionListener l = actionListener;
        if (l != null) l.onAction(a);
    }

    @Override
    public void onCreate() {
        super.onCreate();
        DefaultHttpDataSource.Factory http = new DefaultHttpDataSource.Factory()
                .setAllowCrossProtocolRedirects(true)
                .setUserAgent("Kayal/2.2 (Android; Media3)")
                .setConnectTimeoutMs(15000)
                .setReadTimeoutMs(20000);
        DataSource.Factory ds = new DefaultDataSource.Factory(this, http);
        exo = new ExoPlayer.Builder(this)
                .setMediaSourceFactory(new DefaultMediaSourceFactory(ds))
                .setAudioAttributes(new AudioAttributes.Builder()
                        .setUsage(C.USAGE_MEDIA).setContentType(C.AUDIO_CONTENT_TYPE_MUSIC).build(), true)
                .setHandleAudioBecomingNoisy(true)
                .setWakeMode(C.WAKE_MODE_NETWORK)
                .setSeekBackIncrementMs(10000)
                .setSeekForwardIncrementMs(10000)
                .build();
        exo.addListener(new Player.Listener() {
            @Override public void onAudioSessionIdChanged(int id) { attachEq(id); }
        });
        attachEq(exo.getAudioSessionId());

        Player facade = new ForwardingPlayer(exo) {
            @Override public Commands getAvailableCommands() {
                return super.getAvailableCommands().buildUpon()
                        .addAll(COMMAND_SEEK_TO_NEXT, COMMAND_SEEK_TO_PREVIOUS,
                                COMMAND_SEEK_TO_NEXT_MEDIA_ITEM, COMMAND_SEEK_TO_PREVIOUS_MEDIA_ITEM).build();
            }
            @Override public boolean isCommandAvailable(int c) {
                if (c == COMMAND_SEEK_TO_NEXT || c == COMMAND_SEEK_TO_PREVIOUS
                        || c == COMMAND_SEEK_TO_NEXT_MEDIA_ITEM || c == COMMAND_SEEK_TO_PREVIOUS_MEDIA_ITEM) return true;
                return super.isCommandAvailable(c);
            }
            private void next() {
                if (exo.hasNextMediaItem()) exo.seekToNextMediaItem(); else fire("nexttrack");
            }
            private void prev() {
                if (exo.hasPreviousMediaItem()) {
                    if (exo.getCurrentPosition() > 3000) exo.seekTo(0); else exo.seekToPreviousMediaItem();
                } else fire("previoustrack");
            }
            @Override public void seekToNext() { next(); }
            @Override public void seekToNextMediaItem() { next(); }
            @Override public void seekToPrevious() { prev(); }
            @Override public void seekToPreviousMediaItem() { prev(); }
        };

        Intent open = new Intent(this, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_NEW_TASK);
        PendingIntent pi = PendingIntent.getActivity(this, 0, open, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        session = new MediaSession.Builder(this, facade)
                .setSessionActivity(pi)
                .setCallback(new MediaSession.Callback() {
                    @Override public MediaSession.ConnectionResult onConnect(MediaSession s, MediaSession.ControllerInfo c) {
                        MediaSession.ConnectionResult def = MediaSession.Callback.super.onConnect(s, c);
                        return MediaSession.ConnectionResult.accept(
                                def.availableSessionCommands.buildUpon().add(new SessionCommand(CMD_EQ, Bundle.EMPTY)).build(),
                                def.availablePlayerCommands);
                    }
                    @Override public ListenableFuture<SessionResult> onCustomCommand(MediaSession s, MediaSession.ControllerInfo c,
                                                                                    SessionCommand cmd, Bundle args) {
                        if (CMD_EQ.equals(cmd.customAction)) {
                            eqOn = args.getBoolean("on", false);
                            float[] g = args.getFloatArray("gains");
                            if (g != null && g.length == 10) eqGains = g;
                            eqPre = args.getFloat("pre", 0f);
                            applyEq();
                            Bundle out = new Bundle();
                            out.putBoolean("supported", eq != null);
                            return Futures.immediateFuture(new SessionResult(SessionResult.RESULT_SUCCESS, out));
                        }
                        return MediaSession.Callback.super.onCustomCommand(s, c, cmd, args);
                    }
                }).build();
    }

    /* ---- native equaliser (android.media.audiofx.Equalizer on the ExoPlayer audio session) ---- */
    private void attachEq(int id) {
        if (id == C.AUDIO_SESSION_ID_UNSET || id == eqSession) return;
        try {
            if (eq != null) { eq.release(); eq = null; }
            eq = new Equalizer(0, id);
            eqSession = id;
            applyEq();
        } catch (Throwable t) { eq = null; }
    }

    /** Maps Kayal's 10 bands (+preamp) onto the device equaliser's bands by log-frequency interpolation. */
    private void applyEq() {
        if (eq == null) return;
        try {
            eq.setEnabled(eqOn);
            if (!eqOn) return;
            short[] range = eq.getBandLevelRange();
            for (short b = 0; b < eq.getNumberOfBands(); b++) {
                double hz = eq.getCenterFreq(b) / 1000.0;
                double x = Math.log(Math.max(hz, 1)), db;
                if (hz <= KAYAL_HZ[0]) db = eqGains[0];
                else if (hz >= KAYAL_HZ[9]) db = eqGains[9];
                else {
                    int i = 0;
                    while (i < 8 && hz > KAYAL_HZ[i + 1]) i++;
                    double x0 = Math.log(KAYAL_HZ[i]), x1 = Math.log(KAYAL_HZ[i + 1]);
                    double f = (x - x0) / (x1 - x0);
                    db = eqGains[i] * (1 - f) + eqGains[i + 1] * f;
                }
                int mb = (int) Math.round((db + eqPre) * 100);
                eq.setBandLevel(b, (short) Math.max(range[0], Math.min(range[1], mb)));
            }
        } catch (Throwable ignored) { }
    }

    @Nullable @Override
    public MediaSession onGetSession(MediaSession.ControllerInfo controllerInfo) { return session; }

    @Override
    public void onTaskRemoved(@Nullable Intent rootIntent) {
        // The queue and next-track logic live in the WebView, which dies with the task, so stop cleanly.
        if (exo != null) exo.pause();
        stopSelf();
    }

    @Override
    public void onDestroy() {
        if (eq != null) { try { eq.release(); } catch (Throwable ignored) { } eq = null; }
        if (session != null) { session.getPlayer().release(); session.release(); session = null; }
        super.onDestroy();
    }
}

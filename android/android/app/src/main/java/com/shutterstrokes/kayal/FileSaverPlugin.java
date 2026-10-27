package com.shutterstrokes.kayal;

import android.Manifest;
import android.content.ContentResolver;
import android.content.ContentValues;
import android.content.Intent;
import android.media.MediaScannerConnection;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.provider.MediaStore;
import android.util.Base64;
import android.widget.Toast;
import androidx.core.content.FileProvider;
import com.getcapacitor.JSArray;
import com.getcapacitor.JSObject;
import com.getcapacitor.PermissionState;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.getcapacitor.annotation.Permission;
import com.getcapacitor.annotation.PermissionCallback;
import java.io.File;
import java.io.FileOutputStream;
import java.io.OutputStream;
import java.util.ArrayList;
import org.json.JSONObject;

/**
 * Saves files coming from the web app (blob/data URL "downloads") into the phone's shared storage:
 * images -> Pictures/<App>, videos -> Movies/<App>, everything else -> Download/<App>.
 * Uses MediaStore on Android 10+ (no permission needed) and the legacy public folders on Android 7-9.
 * Also shares files through the Android share sheet (navigator.share polyfill).
 */
@CapacitorPlugin(name = "FileSaver", permissions = { @Permission(alias = "storage", strings = { Manifest.permission.WRITE_EXTERNAL_STORAGE }) })
public class FileSaverPlugin extends Plugin {

    private String folder() {
        String f = getConfig().getString("folder", null);
        if (f == null || f.isEmpty()) f = getContext().getApplicationInfo().loadLabel(getContext().getPackageManager()).toString();
        return f.replaceAll("[\\\\/:*?\"<>|]", "_");
    }

    private static String safeName(String n) {
        if (n == null || n.trim().isEmpty()) n = "file";
        return n.replaceAll("[\\\\/:*?\"<>|\\p{Cntrl}]", "_");
    }

    @PluginMethod
    public void save(PluginCall call) {
        if (Build.VERSION.SDK_INT < 29 && getPermissionState("storage") != PermissionState.GRANTED) {
            requestPermissionForAlias("storage", call, "storagePermCallback");
            return;
        }
        doSave(call);
    }

    @PermissionCallback
    private void storagePermCallback(PluginCall call) {
        if (getPermissionState("storage") == PermissionState.GRANTED) doSave(call);
        else call.reject("Storage permission was denied");
    }

    private void doSave(PluginCall call) {
        String name = safeName(call.getString("name", "file"));
        String mime = call.getString("mime", "application/octet-stream");
        String data = call.getString("data");
        if (data == null) { call.reject("No data"); return; }
        try {
            byte[] bytes = Base64.decode(data, Base64.DEFAULT);
            boolean image = mime.startsWith("image/"), video = mime.startsWith("video/");
            String dir = image ? Environment.DIRECTORY_PICTURES : video ? Environment.DIRECTORY_MOVIES : Environment.DIRECTORY_DOWNLOADS;
            String rel = dir + "/" + folder();
            String uriStr;
            if (Build.VERSION.SDK_INT >= 29) {
                ContentResolver cr = getContext().getContentResolver();
                ContentValues v = new ContentValues();
                v.put(MediaStore.MediaColumns.DISPLAY_NAME, name);
                v.put(MediaStore.MediaColumns.MIME_TYPE, mime);
                v.put(MediaStore.MediaColumns.RELATIVE_PATH, rel);
                v.put(MediaStore.MediaColumns.IS_PENDING, 1);
                Uri col = image ? MediaStore.Images.Media.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY)
                        : video ? MediaStore.Video.Media.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY)
                        : MediaStore.Downloads.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY);
                Uri uri = cr.insert(col, v);
                if (uri == null) throw new Exception("MediaStore insert failed");
                try (OutputStream os = cr.openOutputStream(uri)) { if (os == null) throw new Exception("Cannot open output"); os.write(bytes); }
                v.clear();
                v.put(MediaStore.MediaColumns.IS_PENDING, 0);
                cr.update(uri, v, null, null);
                uriStr = uri.toString();
            } else {
                File d = new File(Environment.getExternalStoragePublicDirectory(dir), folder());
                if (!d.exists() && !d.mkdirs()) throw new Exception("Cannot create " + d);
                File f = new File(d, name);
                String base = name, ext = "";
                int dot = name.lastIndexOf('.');
                if (dot > 0) { base = name.substring(0, dot); ext = name.substring(dot); }
                for (int i = 1; f.exists(); i++) f = new File(d, base + " (" + i + ")" + ext);
                try (FileOutputStream os = new FileOutputStream(f)) { os.write(bytes); }
                MediaScannerConnection.scanFile(getContext(), new String[] { f.getAbsolutePath() }, new String[] { mime }, null);
                uriStr = Uri.fromFile(f).toString();
                name = f.getName();
            }
            final String msg = "Saved to " + rel + "/" + name;
            getActivity().runOnUiThread(() -> Toast.makeText(getContext(), msg, Toast.LENGTH_LONG).show());
            JSObject ret = new JSObject();
            ret.put("uri", uriStr);
            ret.put("location", rel + "/" + name);
            ret.put("bytes", bytes.length);
            call.resolve(ret);
        } catch (Exception e) {
            call.reject("Could not save file: " + e.getMessage(), e);
        }
    }

    /** files: [{name, mime, data(base64)}], title, text, url */
    @PluginMethod
    public void openUrl(PluginCall call) {
        String url = call.getString("url", "");
        if (url == null || !(url.startsWith("https://") || url.startsWith("http://") || url.startsWith("spotify:"))) {
            call.reject("bad url");
            return;
        }
        try {
            Intent i = new Intent(Intent.ACTION_VIEW, Uri.parse(url));
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            getContext().startActivity(i);
            call.resolve();
        } catch (Exception e) {
            call.reject("Could not open link: " + e.getMessage());
        }
    }

    @PluginMethod
    public void share(PluginCall call) {
        try {
            JSArray files = call.getArray("files", new JSArray());
            ArrayList<Uri> uris = new ArrayList<>();
            String mimeAll = null;
            File dir = new File(getContext().getCacheDir(), "share");
            if (!dir.exists()) dir.mkdirs();
            for (int i = 0; i < files.length(); i++) {
                JSONObject o = files.getJSONObject(i);
                String name = safeName(o.optString("name", "file"));
                String mime = o.optString("mime", "application/octet-stream");
                File f = new File(dir, name);
                try (FileOutputStream os = new FileOutputStream(f)) { os.write(Base64.decode(o.getString("data"), Base64.DEFAULT)); }
                uris.add(FileProvider.getUriForFile(getContext(), getContext().getPackageName() + ".fileprovider", f));
                String top = mime.split("/")[0] + "/*";
                mimeAll = mimeAll == null ? mime : (mimeAll.equals(mime) ? mime : (mimeAll.startsWith(mime.split("/")[0]) ? top : "*/*"));
            }
            String text = call.getString("text", ""), url = call.getString("url", ""), title = call.getString("title", "");
            String body = (text + (url.isEmpty() ? "" : (text.isEmpty() ? "" : "\n") + url)).trim();
            Intent it;
            if (uris.size() > 1) { it = new Intent(Intent.ACTION_SEND_MULTIPLE); it.putParcelableArrayListExtra(Intent.EXTRA_STREAM, uris); }
            else { it = new Intent(Intent.ACTION_SEND); if (uris.size() == 1) it.putExtra(Intent.EXTRA_STREAM, uris.get(0)); }
            it.setType(mimeAll != null ? mimeAll : "text/plain");
            if (!body.isEmpty()) it.putExtra(Intent.EXTRA_TEXT, body);
            if (!title.isEmpty()) it.putExtra(Intent.EXTRA_SUBJECT, title);
            it.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
            Intent chooser = Intent.createChooser(it, title.isEmpty() ? "Share" : title);
            chooser.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            getActivity().startActivity(chooser);
            call.resolve();
        } catch (Exception e) {
            call.reject("Share failed: " + e.getMessage(), e);
        }
    }
}

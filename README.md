# Kayal

Kayal is a personal music player by Sandeep (HQ Media), built as a single-file web app (`web/index.html`) that is wrapped as an Android app (`com.shutterstrokes.kayal`) with [Capacitor](https://capacitorjs.com/). Current version: **2.2.0** (versionCode 4).

This is a **private, personal-use project**. It is not published, sold or monetised.

## Layout

| Path | What it is |
|---|---|
| `web/` | The web app: `index.html`, icons, `manifest.webmanifest`, `sw.js`, `hls.light.min.js` (+ `LICENSE-hls.js.txt`), `test/` (Python end-to-end suites + results), `screenshots/` |
| `android/` | The Capacitor project: `package.json`, `capacitor.config.json`, `native.json`, `sync_android.py`, `www/native-bridge.js` (hand-written native bridge), and `android/` (the Gradle project with `MainActivity.java`, `FileSaverPlugin.java`, manifest, resources) |

Not in the repo (generated or secret): `node_modules/`, `build/`, `.gradle/`, `android/www/*` except `native-bridge.js`, `android/android/app/src/main/assets/public/`, generated Capacitor config files, `capacitor-cordova-android-plugins/`, `*.apk`, `*.aab`, `*.jks`, `*.keystore`, `keystore.properties`, `local.properties`, `.env*`.

## Original build paths (not yet adapted to this layout)

`sync_android.py` and `native.json` were imported **unchanged** and still use the original machine paths:

- web source: `/workspace/music-player` (= `web/` here)
- Capacitor project: `/workspace/android-build/kayal` (= `android/` here)
- signing key: `/workspace/android-keys/kayal-release.jks`

(`native.json` is a stale icon/version helper file and still says 2.1.0; the real version is in `android/android/app/build.gradle`.)
To build from a clone, either recreate those paths (e.g. symlink them to the clone) or edit the two path constants at the top of `sync_android.py`.

## Build

Requirements: Node 22, JDK 21, Android SDK (API 35-ish; see `android/android/variables.gradle`).

```bash
cd android
npm install                      # Capacitor + plugins
python3 sync_android.py          # copies web/index.html into www/ and re-applies the native-only patches
npx cap sync android             # copies www/ into the Gradle project, regenerates plugin config
cd android
./gradlew assembleRelease        # or assembleDebug
```

The APK is written to `android/android/app/build/outputs/apk/`.

### Signing

Release signing reads `android/android/keystore.properties`, which is **never committed**. Create it locally:

```properties
storeFile=/absolute/path/to/your-release.jks
storePassword=...
keyAlias=...
keyPassword=...
```

Keep the keystore and passwords outside the repo. Without them, use `assembleDebug`. Always install updates signed with the same key, or Android will refuse to update in place.

## Tests

`web/test/kayal_e2e*.py` are browser end-to-end suites (results in `web/test/results*.json`).

## Legal / sources note

Kayal only plays audio from sources that permit it: your own local files, free/open catalogues (Audius, Internet Archive, Wikimedia, Jamendo with your own key), live radio streams, and official 30-second previews. Commercial catalogue songs are opened in their official apps (YouTube Music, JioSaavn, Spotify) rather than being ripped or streamed around those services' access controls. No secret API keys are embedded; no paid backend or cloud AI is used.

## Third-party licences

- **hls.js** (`web/hls.light.min.js`) - Apache License 2.0, (c) 2017 Dailymotion. Licence text: `web/LICENSE-hls.js.txt` (kept alongside the file).
- Capacitor and its plugins (MIT / Apache-2.0) are installed via npm.
- No code from BitChord (GPL-3.0) is included in this repository. If any is added later, the combined work becomes GPL-3.0 and its notices must be kept.

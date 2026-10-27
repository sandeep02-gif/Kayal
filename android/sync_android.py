#!/usr/bin/env python3
"""Sync the Kayal web app (<repo>/web) into the Capacitor www/ folder (<repo>/android/www),
re-applying the native-only patches (bridge script, https-radio on Android, no PWA/SW/install UI).
All paths are relative to this script, so it works from any checkout."""
import shutil,sys,os
HERE=os.path.dirname(os.path.abspath(__file__))
SRC=os.path.join(HERE,'..','web');DST=os.path.join(HERE,'www')
os.makedirs(DST,exist_ok=True)
s=open(os.path.join(SRC,'index.html'),encoding='utf-8').read()
def rep(old,new,cnt=1):
    global s
    n=s.count(old);assert n==cnt,f'expected {cnt} got {n}: {old[:80]!r}'
    s=s.replace(old,new)
rep('<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">','<meta name="viewport" content="width=device-width,initial-scale=1,">')
rep('<meta name="theme-color" content="#0f1115">','<meta name="theme-color" content="#0f1115">\n<script>window.__NATIVE_APP="kayal";window.__NATIVE_BAR="#0f1115"</script><script src="native-bridge.js"></script>')
rep(' <button id="installBtn" class="btn" hidden>Install</button>\n',' \n')
rep("const okArt=u=>typeof u==='string'&&/^https:\\/\\//.test(u)||(typeof u==='string'&&u.startsWith('http:')&&location.protocol==='http:');",
    "const NATIVE=(window.Capacitor&&Capacitor.isNativePlatform&&Capacitor.isNativePlatform());const okArt=u=>typeof u==='string'&&/^https:\\/\\//.test(u)||(typeof u==='string'&&u.startsWith('http:')&&(location.protocol==='http:'||NATIVE));")
rep("const https=location.protocol==='https:';const seen=new Set();","const https=location.protocol==='https:'&&!NATIVE;const seen=new Set();")
# ---- native playback (Media3 via KayalPlayer plugin): Kayal's JS player drives an <audio>-compatible shim ----
rep("const audioPl=$('#audio');","const audioPl=window.__nativeAudio?window.__nativeAudio($('#audio')):$('#audio');")
# Web Audio EQ cannot process native audio: use the native equaliser (Android audiofx) instead
rep("let useEq=!!S.eq.on&&!this.noEq.has(key(t));","let useEq=!NATIVE&&!!S.eq.on&&!this.noEq.has(key(t));")
rep("this.eqActive=useEq;","this.eqActive=NATIVE?(!!S.eq.on&&window.__nativeEqOK!==false):useEq;if(NATIVE)EQ.apply();")
rep("else audio.src=u;","else{if(NATIVE)audio.hlsHint=hls;audio.src=u}")
rep("apply(){if(!this.nodes)return;","apply(){if(window.__nativeEqApply)window.__nativeEqApply(S.eq);if(!this.nodes)return;")
rep("async function reapplyEq(){","async function reapplyEq(){if(NATIVE){player.eqActive=!!S.eq.on&&window.__nativeEqOK!==false;EQ.apply();return}")
# don't pre-load the saved queue into the native player at startup (it would show a paused notification); first Play loads it
rep("if(!audio.getAttribute('src')&&player.cur()===t){audio.preload='metadata';audio.src=u}","if(!NATIVE&&!audio.getAttribute('src')&&player.cur()===t){audio.preload='metadata';audio.src=u}")
rep("radio:'Radio',jamendo:'Jamendo'};","radio:'Radio',jamendo:'Jamendo',local:'This device'};")
rep("const kayal=window.kayal={get S(){return S},","const kayal=window.kayal={get S(){return S},save,renderLibrary,")
a=s.index("let deferredInstall=null;window.addEventListener('beforeinstallprompt'");b=s.index("const net=()=>")
s=s[:a]+"""let deferredInstall=null;
if($('#installBtn'))$('#installBtn').onclick=async()=>{if(!deferredInstall)return;deferredInstall.prompt();await deferredInstall.userChoice.catch(()=>{});deferredInstall=null;$('#installBtn').hidden=true};

"""+s[b:]
open(os.path.join(DST,'index.html'),'w',encoding='utf-8').write(s)
for f in ['hls.light.min.js','manifest.webmanifest','icon.svg','icon-192.png','icon-512.png','icon-maskable-512.png']:
    shutil.copy(os.path.join(SRC,f),os.path.join(DST,f))
print('synced',len(s),'bytes; www files:',sorted(os.listdir(DST)))

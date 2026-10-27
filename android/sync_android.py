#!/usr/bin/env python3
"""Sync the Kayal web app (/workspace/music-player) into the Capacitor www/ folder,
re-applying the native-only patches (bridge script, https-radio on Android, no PWA/SW/install UI)."""
import shutil,sys,os
SRC='/workspace/music-player';DST='/workspace/android-build/kayal/www'
s=open(SRC+'/index.html',encoding='utf-8').read()
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
a=s.index("let deferredInstall=null;window.addEventListener('beforeinstallprompt'");b=s.index("const net=()=>")
s=s[:a]+"""let deferredInstall=null;
if($('#installBtn'))$('#installBtn').onclick=async()=>{if(!deferredInstall)return;deferredInstall.prompt();await deferredInstall.userChoice.catch(()=>{});deferredInstall=null;$('#installBtn').hidden=true};

"""+s[b:]
open(DST+'/index.html','w',encoding='utf-8').write(s)
for f in ['hls.light.min.js','manifest.webmanifest','icon.svg','icon-192.png','icon-512.png','icon-maskable-512.png']:
    shutil.copy(f'{SRC}/{f}',f'{DST}/{f}')
print('synced',len(s),'bytes; www files:',sorted(os.listdir(DST)))

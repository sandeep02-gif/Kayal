/* Android (Capacitor) bridge: downloads -> phone storage, Web Share polyfill, back button,
   status bar, and (Kayal) Media Session -> native lock-screen/notification controls. */
(function(){
'use strict';
var C=window.Capacitor;if(!C||!C.isNativePlatform||!C.isNativePlatform())return;
var APP=(window.__NATIVE_APP||'app');
function plug(n){return (C.Plugins&&C.Plugins[n])||(C.registerPlugin?C.registerPlugin(n):null)}
window.__native={app:APP,log:[]};
function log(m){try{window.__native.log.push(String(m));if(window.__native.log.length>50)window.__native.log.shift()}catch(e){}}
var tEl=null,tT=0;
function toast(m){try{if(!tEl){tEl=document.createElement('div');tEl.setAttribute('role','status');tEl.style.cssText='position:fixed;left:50%;bottom:96px;transform:translateX(-50%);background:#e8edf5;color:#111;padding:10px 16px;border-radius:10px;z-index:2147483647;font:600 14px system-ui,sans-serif;max-width:86vw;text-align:center;box-shadow:0 6px 20px #0006;transition:opacity .2s;pointer-events:none';document.body.appendChild(tEl)}tEl.textContent=m;tEl.style.opacity='1';clearTimeout(tT);tT=setTimeout(function(){tEl.style.opacity='0'},2000)}catch(e){}}
window.__native.toast=toast;
function b64(blob){return new Promise(function(res,rej){var r=new FileReader();r.onload=function(){var s=String(r.result);res(s.slice(s.indexOf(',')+1))};r.onerror=function(){rej(r.error)};r.readAsDataURL(blob)})}
var MIME={png:'image/png',jpg:'image/jpeg',jpeg:'image/jpeg',webp:'image/webp',gif:'image/gif',webm:'video/webm',mp4:'video/mp4',zip:'application/zip',json:'application/json',txt:'text/plain',csv:'text/csv',svg:'image/svg+xml',pdf:'application/pdf'};
function guess(n){var e=(String(n).split('.').pop()||'').toLowerCase();return MIME[e]||'application/octet-stream'}
async function saveBlob(blob,name){var mime=(blob.type&&blob.type!=='application/octet-stream')?blob.type.split(';')[0]:guess(name);
  var r=await plug('FileSaver').save({name:name,mime:mime,data:await b64(blob)});log('saved '+r.location);window.__native.lastSaved=r;
  try{window.dispatchEvent(new CustomEvent('native-saved',{detail:r}))}catch(e){}return r}
window.__native.saveBlob=saveBlob;
async function saveHref(href,name){try{var blob=await (await fetch(href)).blob();return await saveBlob(blob,name)}catch(e){log('save failed '+e.message);toast('Could not save: '+e.message);throw e}}
/* 1. downloads: <a download href="blob:|data:"> */
var oclick=HTMLAnchorElement.prototype.click;
HTMLAnchorElement.prototype.click=function(){var h=this.href||'';if(this.hasAttribute('download')&&/^(blob:|data:)/.test(h)){saveHref(h,this.getAttribute('download')||'download').catch(function(){});return}return oclick.call(this)};
document.addEventListener('click',function(e){var a=e.target&&e.target.closest&&e.target.closest('a[download]');if(!a)return;var h=a.href||'';if(/^(blob:|data:)/.test(h)){e.preventDefault();e.stopPropagation();saveHref(h,a.getAttribute('download')||'download').catch(function(){})}},true);
/* 2. Web Share API polyfill -> Android share sheet */
navigator.canShare=function(d){return !!d};
navigator.share=async function(d){d=d||{};var files=[];if(d.files)for(var i=0;i<d.files.length;i++){var f=d.files[i];files.push({name:f.name||('file-'+i),mime:f.type||guess(f.name||''),data:await b64(f)})}
  await plug('FileSaver').share({files:files,title:d.title||'',text:d.text||'',url:d.url||''})};
/* 3. Status bar (Android < 15; on 15+ the system bars are drawn edge-to-edge over the page padding) */
try{var SB=plug('StatusBar');var col=window.__NATIVE_BAR||'#0f1115';SB&&SB.setBackgroundColor&&SB.setBackgroundColor({color:col}).catch(function(){});SB&&SB.setStyle&&SB.setStyle({style:'DARK'}).catch(function(){})}catch(e){}
/* 4. Back button: close in-app layers first, never exit on the first press */
var lastBack=0;
function vis(el){return !!el&&!el.hidden&&getComputedStyle(el).display!=='none'&&getComputedStyle(el).visibility!=='hidden'}
function kayalBack(){var sh=document.getElementById('sheet'),np=document.getElementById('np'),det=document.getElementById('v-detail');
  if(sh&&sh.classList.contains('on')||np&&np.classList.contains('on')||det&&det.classList.contains('on')){if(history.state&&history.state.k){history.back()}else{if(sh&&sh.classList.contains('on')){document.getElementById('sheetBg').click()}else if(np&&np.classList.contains('on')){document.getElementById('npClose').click()}else{document.getElementById('detBack').click()}}return true}
  var home=document.querySelector('nav.bnav [data-tab="home"]');if(home&&!home.classList.contains('on')){home.click();return true}return false}
function collageBack(){var open=document.querySelectorAll('.sheet-wrap.show');if(open.length){document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));return true}
  var ov=document.getElementById('calOverlay');if(ov&&!ov.hidden){var b=document.getElementById('calBoardBtn');if(b){b.click();return true}}
  var ae=document.activeElement;if(ae&&/^(INPUT|TEXTAREA)$/.test(ae.tagName)){ae.blur();return true}
  var first=document.querySelector('#mobilebar button[data-tab]');var act=document.querySelector('#mobilebar button.active');if(first&&act&&act!==first&&vis(first)){first.click();return true}return false}
try{var App=plug('App');App&&App.addListener('backButton',function(ev){var handled=APP==='kayal'?kayalBack():APP==='collage'?collageBack():false;log('back handled='+handled);
  if(handled)return;if(ev&&ev.canGoBack){history.back();return}
  var now=Date.now();if(now-lastBack<2000){if(APP==='kayal'&&App.minimizeApp){App.minimizeApp()}else{App.exitApp()}}else{lastBack=now;toast(APP==='kayal'?'Press back again to leave (music keeps playing)':'Press back again to exit')}})}catch(e){log('back listener failed '+e.message)}
/* 5. Kayal: native audio engine (Media3 ExoPlayer + MediaSessionService, via the KayalPlayer plugin).
   Kayal's JS player talks to an HTMLAudioElement-compatible shim (window.__nativeAudio, wired in by sync_android.py),
   so queue / shuffle / repeat / sleep timer logic is unchanged while the audio itself plays in a foreground service
   (background playback, media notification, lock-screen controls). If the plugin is missing it falls back to the
   old behaviour (WebView <audio> + @capgo/capacitor-media-session). */
var KP=null;try{KP=(APP==='kayal')?plug('KayalPlayer'):null}catch(e){KP=null}
if(APP==='kayal'&&KP){
  window.__native.player=KP;var curMeta=null,handlers={},notifAsked=false;
  function artOK(m){var a=((m&&m.artwork)||[]).filter(function(x){return x&&/^https?:/.test(x.src)&&!/^https?:\/\/(localhost|127\.)/.test(x.src)})[0];return a?a.src:''}
  function MM(o){o=o||{};this.title=o.title||'';this.artist=o.artist||'';this.album=o.album||'';this.artwork=o.artwork||[]}
  window.MediaMetadata=MM;
  var shim={get metadata(){return curMeta},set metadata(m){curMeta=m;if(!m)return;
      try{KP.setMetadata({title:m.title||'',artist:m.artist||'',album:m.album||'',artwork:artOK(m)}).catch(function(e){log('meta '+e.message)})}catch(e){}},
    playbackState:'none',setActionHandler:function(a,h){if(h)handlers[a]=h;else delete handlers[a]},setPositionState:function(){}};
  try{Object.defineProperty(navigator,'mediaSession',{value:shim,configurable:true})}catch(e){log('mediaSession shim failed '+e.message)}
  /* notification / lock-screen / headset skip buttons -> Kayal's own next/prev logic */
  KP.addListener('action',function(e){var h=handlers[e&&e.action];log('action '+(e&&e.action));if(h)try{h({action:e.action})}catch(x){}});
  function bytesB64(blob){return b64(blob)}
  async function resolveUri(u){
    if(!/^blob:/.test(u))return u;
    var blob=await (await fetch(u)).blob(),ext=((blob.type||'audio/mpeg').split('/')[1]||'mp3').split(';')[0].replace(/[^a-z0-9]/gi,'')||'mp3';
    var name='t'+Date.now()+'.'+ext,CH=3*1024*1024,uri='';await KP.clearCache().catch(function(){});
    for(var o=0,i=0;o<blob.size;o+=CH,i++){var r=await KP.writeCache({name:name,data:await bytesB64(blob.slice(o,o+CH)),append:i>0});uri=r.uri}
    return uri}
  class NativeAudio extends EventTarget{
    constructor(){super();this._src='';this._t=0;this._d=NaN;this._paused=true;this._vol=1;this._muted=false;this.error=null;this.preload='auto';this.playbackRate=1;this.readyState=0;this.ended=false;
      this._tok=0;this._lock=0;this._ready=Promise.resolve();this._pl=false;this._err='';this.hlsHint=false;this.nativeState=null}
    _e(n){try{this.dispatchEvent(new Event(n))}catch(e){}}
    get src(){return this._src}
    set src(v){v=String(v||'');if(!v){this.removeAttribute('src');return}
      var self=this,tok=++this._tok,hls=!!this.hlsHint||/\.m3u8(\?|$)/i.test(v);this.hlsHint=false;
      this._src=v;this.error=null;this.ended=false;this._t=0;this._d=NaN;this._paused=true;this._pl=false;this._err='';this.readyState=0;this._e('emptied');this._e('loadstart');
      var m=curMeta||{};
      this._ready=resolveUri(v).then(function(uri){if(tok!==self._tok)return;
        return KP.load({url:uri,hls:hls,autoplay:false,title:m.title||'',artist:m.artist||'',album:m.album||'',artwork:artOK(m)})});
      this._ready.catch(function(e){log('load failed '+(e&&e.message))})}
    getAttribute(n){return n==='src'&&this._src?this._src:null}
    setAttribute(n,v){if(n==='src')this.src=v}
    removeAttribute(n){if(n!=='src')return;this._tok++;this._src='';this._t=0;this._d=NaN;this._paused=true;this._pl=false;this.ended=false;this._ready=Promise.resolve();try{KP.stop().catch(function(){})}catch(e){}}
    load(){}
    canPlayType(){return 'maybe'}
    get paused(){return this._paused}
    get currentTime(){return this._t}
    set currentTime(v){v=+v;if(!isFinite(v)||v<0)v=0;this._t=v;var tok=this._tok;this._e('seeking');this._ready.then(function(){return KP.seekTo({position:v})}).catch(function(){});this._e('timeupdate')}
    get duration(){return this._d}
    get volume(){return this._vol}
    set volume(v){this._vol=Math.max(0,Math.min(1,+v||0));this._pushVol()}
    get muted(){return this._muted}
    set muted(v){this._muted=!!v;this._pushVol()}
    _pushVol(){try{KP.setVolume({volume:this._vol,muted:this._muted}).catch(function(){})}catch(e){}}
    play(){var self=this;if(!this._src)return Promise.reject(new DOMException('No source','NotSupportedError'));
      var tok=this._tok;this._paused=false;this._lock=Date.now();this._e('play');
      if(!notifAsked){notifAsked=true;KP.requestNotifications().catch(function(){})}
      return this._ready.then(function(){if(tok!==self._tok)throw new DOMException('Superseded','AbortError');return KP.play()}).then(function(){},function(e){
        if(e&&e.name==='AbortError')throw e;self._paused=true;var er=new Error((e&&e.message)||'native load failed');er.name='NotSupportedError';throw er})}
    pause(){if(!this._src)return;this._paused=true;this._lock=Date.now();this._e('pause');this._ready.then(function(){return KP.pause()}).catch(function(){})}
    /* native -> element state */
    _apply(s){if(!this._src)return;this.nativeState=s;var prevT=this._t;this._t=s.position||0;
      if(s.state!=='idle')this.readyState=s.state==='ready'?4:2;
      var d=s.duration>0?s.duration:(s.state==='ready'?Infinity:NaN);
      if(!(d===this._d||(isNaN(d)&&isNaN(this._d)))){var first=isNaN(this._d);this._d=d;if(!isNaN(d)){if(first)this._e('loadedmetadata');this._e('durationchange');this._e('canplay')}}
      var wantPlay=!!s.playWhenReady&&s.state!=='ended',recent=Date.now()-this._lock<800;
      if(!recent&&s.state!=='idle'){if(wantPlay&&this._paused){this._paused=false;this._e('play')}else if(!wantPlay&&!this._paused&&s.state!=='ended'){this._paused=true;this._e('pause')}}
      if(s.playing&&!this._pl){this._pl=true;this._e('playing')}else if(!s.playing&&this._pl){this._pl=false;if(s.state==='buffering')this._e('waiting')}
      if(s.state==='ended'&&!this.ended){this.ended=true;this._paused=true;this._pl=false;this._e('pause');this._e('ended')}
      else if(s.state!=='ended')this.ended=false;
      if(s.error&&s.error!==this._err){this._err=s.error;this.error={code:4,message:s.error};this._e('error')}
      if(s.playing||this._t!==prevT)this._e('timeupdate')}
  }
  var NA=null;
  window.__nativeAudio=function(realEl){if(!NA){NA=new NativeAudio();KP.addListener('state',function(s){if(NA)NA._apply(s)});KP.getState().catch(function(){})}return NA};
  /* native equaliser (Android audiofx on the player's audio session). The WebAudio EQ cannot touch native audio. */
  window.__nativeEqOK=true;
  window.__nativeEqApply=function(eq){try{KP.setEq({on:!!eq.on,gains:eq.g,pre:eq.pre||0}).then(function(r){window.__nativeEqOK=!!(r&&r.supported)}).catch(function(){window.__nativeEqOK=false})}catch(e){}};
  /* local music: system file picker -> "On this device" playlist */
  function pickLocal(){KP.pickAudio().then(function(r){var files=(r&&r.files)||[];if(!files.length)return;var k=window.kayal;if(!k){toast('Kayal is still loading');return}
      var pl=k.S.playlists.find(function(p){return p.name==='On this device'})||k.createPlaylist('On this device');
      var have={};pl.tracks.forEach(function(t){have[t.id]=1});var first=-1,added=0;
      files.forEach(function(f){var id='l:'+f.uri;if(have[id]){if(first<0)first=pl.tracks.findIndex(function(t){return t.id===id});return}
        pl.tracks.push({src:'local',id:id,title:f.title,artist:f.artist||'Unknown artist',art:'',alt:[],dur:f.duration||0,url:f.uri,aid:'',live:false,lic:'',dl:0,hls:0,pg:'',uid:'',gn:'',ts:Date.now(),cr:''});
        if(first<0)first=pl.tracks.length-1;added++});
      k.save();k.renderLibrary();toast(added?('Added '+added+' file'+(added===1?'':'s')+' to “On this device”'):'Already in “On this device”');
      k.player.playList(pl.tracks,Math.max(0,first))}).catch(function(e){log('pick failed '+(e&&e.message));toast('Could not open files')})}
  window.__native.pickLocal=pickLocal;
  function addLocalBtn(){var np=document.getElementById('newPl');if(!np||document.getElementById('addLocal'))return;
    var w=document.createElement('div');w.style.cssText='display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end';np.parentNode.insertBefore(w,np);
    var b=document.createElement('button');b.className='btn';b.id='addLocal';b.textContent='Add local music';b.onclick=pickLocal;w.appendChild(b);w.appendChild(np)}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',addLocalBtn);else addLocalBtn();
  log('native player ready')
}else if(APP==='kayal'){var MS=function(){return plug('MediaSession')};var meta=null,state='none',lastPos=0,lastP=-1;
  function MM(o){o=o||{};this.title=o.title||'';this.artist=o.artist||'';this.album=o.album||'';this.artwork=o.artwork||[]}
  window.MediaMetadata=MM;
  var shim={get metadata(){return meta},set metadata(m){meta=m;if(!m)return;var art=(m.artwork||[]).filter(function(a){return a&&/^https?:/.test(a.src)});
      try{MS().setMetadata({title:m.title||'',artist:m.artist||'',album:m.album||'',artwork:art}).catch(function(e){log('meta '+e.message)})}catch(e){}},
    get playbackState(){return state},set playbackState(s){if(s===state)return;state=s;try{MS().setPlaybackState({playbackState:s}).catch(function(e){log('state '+e.message)})}catch(e){}},
    setActionHandler:function(a,h){if(!h)return;try{MS().setActionHandler({action:a},function(d){try{h(Object.assign({action:a},d||{}))}catch(e){}}).catch(function(){})}catch(e){}},
    setPositionState:function(p){if(!p||!isFinite(p.duration))return;var now=Date.now();if(now-lastPos<2000&&Math.abs((p.position||0)-lastP-(now-lastPos)/1000)<2)return;lastPos=now;lastP=p.position||0;
      try{MS().setPositionState({duration:p.duration,position:p.position||0,playbackRate:p.playbackRate||1}).catch(function(){})}catch(e){}}};
  try{Object.defineProperty(navigator,'mediaSession',{value:shim,configurable:true})}catch(e){log('mediaSession shim failed '+e.message)}}
/* 6. hide web-only 'install as PWA' UI inside the app */
try{var st=document.createElement('style');st.textContent='#installHelpBtn,#installBtn2,#installBtn,#installHelp{display:none!important}';(document.head||document.documentElement).appendChild(st)}catch(e){}
/* 7. open external links (JioSaavn / Spotify / YouTube Music) in their app or the browser */
window.__native.openUrl=function(u){try{return plug('FileSaver').openUrl({url:u}).catch(function(){window.open(u,'_blank')})}catch(e){window.open(u,'_blank')}};
log('bridge ready '+APP);
})();

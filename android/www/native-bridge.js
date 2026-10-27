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
/* 5. Kayal: Media Session API -> native media session + foreground playback service */
if(APP==='kayal'){var MS=function(){return plug('MediaSession')};var meta=null,state='none',lastPos=0,lastP=-1;
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

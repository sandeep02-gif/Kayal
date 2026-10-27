#!/usr/bin/env python3
"""Host-side test of Kayal's native-player wiring (android/www = output of sync_android.py).
A fake `KayalPlayer` Capacitor plugin (backed by a Chromium <audio>) stands in for the Media3 service, so this checks the
JS side only: routing of Kayal's player to the plugin, events back, notification skip actions, EQ routing, local files,
blob sources and startup behaviour. It does NOT test ExoPlayer, the foreground service, notification or lock screen.
Usage: python3 android/sync_android.py && python3 android/test/native_shim_test.py"""
import asyncio,os,sys,wave,struct,math,threading,http.server,socketserver,functools,tempfile,json
from playwright.async_api import async_playwright
HERE=os.path.dirname(os.path.abspath(__file__));WWW=os.path.join(HERE,'..','www')
TMP=tempfile.mkdtemp()
def tone(path,secs,f=440):
    w=wave.open(path,'wb');w.setnchannels(1);w.setsampwidth(2);w.setframerate(8000)
    w.writeframes(b''.join(struct.pack('<h',int(8000*math.sin(2*math.pi*f*i/8000))) for i in range(int(8000*secs))));w.close()
tone(TMP+'/a.wav',3,440);tone(TMP+'/b.wav',3,660);tone(TMP+'/c.wav',20,880)
class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*a):pass
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin','*');super().end_headers()
class RS(socketserver.ThreadingTCPServer):
    allow_reuse_address=True;daemon_threads=True
def serve(d,port):
    h=functools.partial(Q,directory=d);s=RS(('127.0.0.1',port),h)
    threading.Thread(target=s.serve_forever,daemon=True).start();return s
serve(os.path.abspath(WWW),18092);serve(TMP,18093)
INIT=r"""
(function(){
 const L={};const calls=[];window.__calls=calls;
 const a=new Audio();a.preload='auto';let pwr=false,err='',hasItem=false;
 const snap=()=>({state:!hasItem?'idle':a.ended?'ended':(a.readyState>=3?'ready':'buffering'),playing:hasItem&&!a.paused&&!a.ended&&a.readyState>=3,playWhenReady:pwr,position:a.currentTime||0,duration:isFinite(a.duration)?a.duration:0,index:0,count:hasItem?1:0,uri:a.src,error:err});
 const emit=(n,d)=>(L[n]||[]).forEach(f=>f(d));const push=()=>emit('state',snap());
 ['playing','pause','play','ended','waiting','canplay','loadedmetadata','seeked','timeupdate'].forEach(e=>a.addEventListener(e,push));
 a.addEventListener('error',()=>{err='media error';push()});
 window.__fireAction=x=>emit('action',{action:x});window.__nativePause=()=>{pwr=false;a.pause();push()};window.__nativePlay=()=>{pwr=true;a.play();push()};
 const KP={addListener(n,f){(L[n]=L[n]||[]).push(f);return Promise.resolve({remove(){}})},
  load(o){calls.push(['load',o]);err='';hasItem=true;a.src=o.url;pwr=!!o.autoplay;if(pwr)a.play().catch(()=>{});push();return Promise.resolve(snap())},
  play(){calls.push(['play']);pwr=true;a.play().catch(()=>{});push();return Promise.resolve(snap())},
  pause(){calls.push(['pause']);pwr=false;a.pause();push();return Promise.resolve(snap())},
  stop(){calls.push(['stop']);pwr=false;hasItem=false;a.pause();a.removeAttribute('src');return Promise.resolve(snap())},
  seekTo(o){calls.push(['seekTo',o]);a.currentTime=o.position;return Promise.resolve()},
  setVolume(o){calls.push(['setVolume',o]);return Promise.resolve()},
  setMetadata(o){calls.push(['setMetadata',o]);return Promise.resolve()},
  setEq(o){calls.push(['setEq',o]);return Promise.resolve({supported:true})},
  requestNotifications(){calls.push(['requestNotifications']);return Promise.resolve({granted:true})},
  getState(){return Promise.resolve(snap())},clearCache(){calls.push(['clearCache']);return Promise.resolve()},
  writeCache(o){calls.push(['writeCache',{name:o.name,len:o.data.length,append:o.append}]);return Promise.resolve({uri:'http://127.0.0.1:18093/a.wav'})},
  pickAudio(){calls.push(['pickAudio']);return Promise.resolve({files:[{uri:'http://127.0.0.1:18093/a.wav',title:'Local A',artist:'Me',duration:3},{uri:'http://127.0.0.1:18093/b.wav',title:'Local B',artist:'',duration:3}]})}};
 const stub=new Proxy({},{get:(t,k)=>k==='addListener'?()=>Promise.resolve({remove(){}}):()=>Promise.resolve({})});
 window.Capacitor={isNativePlatform:()=>true,getPlatform:()=>'android',Plugins:{},registerPlugin:n=>n==='KayalPlayer'?KP:stub};
})();"""
R=[]
def check(n,ok,d=''):
    R.append(bool(ok));print(('PASS ' if ok else 'FAIL ')+n+((' – '+str(d)[:300]) if d!='' else ''),flush=True)
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(executable_path='/usr/bin/google-chrome',args=['--no-sandbox','--autoplay-policy=no-user-gesture-required'])
        ctx=await b.new_context(viewport={'width':412,'height':900},is_mobile=True,has_touch=True)
        await ctx.add_init_script(INIT)
        pg=await ctx.new_page();errs=[]
        pg.on('pageerror',lambda e:errs.append(str(e)[:200]))
        pg.on('console',lambda m:errs.append(m.text[:200]) if m.type=='error' and 'Failed to load resource' not in m.text else None)
        await pg.goto('http://127.0.0.1:18092/index.html');await pg.wait_for_function('window.kayal&&kayal.ready');await pg.wait_for_timeout(500)
        ev=lambda js,a=None:pg.evaluate(js,a)
        calls=lambda n=None:ev("n=>__calls.filter(c=>!n||c[0]===n)",n)
        check('bridge ready + native player detected',await ev("__native&&__native.log.includes('native player ready')"))
        check('Kayal player drives the native shim (not a DOM <audio>)',await ev("kayal.audio.constructor.name==='NativeAudio'&&kayal.audioPl===kayal.audio"))
        check('web WebAudio equaliser is not created on native',await ev("!kayal.EQ.ctx"))
        # --- play a track
        T=lambda i,u,t,dur=3:{'src':'local','id':i,'title':t,'artist':'Test','art':'','dur':dur,'url':u}
        await ev("T=>kayal.player.playList(T,0)",[T('1','http://127.0.0.1:18093/a.wav','Song A'),T('2','http://127.0.0.1:18093/b.wav','Song B'),T('3','http://127.0.0.1:18093/c.wav','Song C',20)])
        await pg.wait_for_function("kayal.audio.currentTime>0.4",timeout=8000)
        c=await calls('load');check('load() called with the resolved URL, autoplay off then play()',len(c)==1 and c[0][1]['url'].endswith('a.wav') and c[0][1]['autoplay']==False and len(await calls('play'))>=1,c[:1])
        check('notification permission requested on first play',len(await calls('requestNotifications'))==1)
        m=await calls('setMetadata');check('Media metadata forwarded to native',any(x[1]['title']=='Song A' for x in m),m[:2])
        check('UI shows playing (pause icon) and duration known',await ev("document.querySelector('#play use').getAttribute('href')==='#i-pause'&&isFinite(kayal.audio.duration)&&Math.abs(kayal.audio.duration-3)<.3"))
        check('local source is labelled for the UI',await ev("kayal.S.queue[0].src==='local'"))
        # --- seek
        await ev("kayal.audio.currentTime=2");await pg.wait_for_timeout(300)
        check('seek forwarded to native',any(abs(x[1]['position']-2)<.01 for x in await calls('seekTo')))
        # --- ended -> auto next
        await pg.wait_for_function("kayal.S.qi===1",timeout=8000)
        check('track end -> JS advances queue and loads next track natively',(await calls('load'))[-1][1]['url'].endswith('b.wav'))
        # --- notification skip buttons
        await pg.wait_for_function("kayal.audio.currentTime>0.3",timeout=6000)
        await ev("__fireAction('nexttrack')");await pg.wait_for_function("kayal.S.qi===2",timeout=6000)
        check('notification Next -> Kayal next()',(await calls('load'))[-1][1]['url'].endswith('c.wav'))
        await pg.wait_for_function("kayal.audio.currentTime>0.3",timeout=6000)
        await ev("__fireAction('previoustrack')");await pg.wait_for_timeout(300)
        check('notification Previous (<3s into track) -> previous track',await ev("kayal.S.qi===1"))
        await pg.wait_for_function("kayal.audio.currentTime>0.2",timeout=6000)
        # --- pause/play from the notification / lock screen (native state wins)
        await pg.wait_for_timeout(900)
        await ev("__nativePause()");await pg.wait_for_timeout(400)
        check('pause from notification -> UI shows paused',await ev("kayal.audio.paused&&document.querySelector('#play use').getAttribute('href')==='#i-play'"))
        await ev("__nativePlay()");await pg.wait_for_timeout(500)
        check('play from notification -> UI shows playing',await ev("!kayal.audio.paused&&document.querySelector('#play use').getAttribute('href')==='#i-pause'"))
        # --- in-app pause button reaches native
        n0=len(await calls('pause'));await pg.evaluate("document.querySelector('#play').click()");await pg.wait_for_timeout(400)
        check('in-app pause button -> native pause()',len(await calls('pause'))>n0 and await ev("kayal.audio.paused"))
        await pg.evaluate("document.querySelector('#play').click()");await pg.wait_for_timeout(500)
        # --- volume
        await ev("kayal.audio.volume=.5");check('volume forwarded',any(x[1]['volume']==.5 for x in await calls('setVolume')))
        # --- EQ
        await ev("kayal.S.eq.on=true;kayal.S.eq.g=[6,5,4,2,0,0,0,0,0,0];kayal.EQ.apply()");await pg.wait_for_timeout(200)
        e=await calls('setEq');check('equaliser settings go to the native equaliser',e and e[-1][1]['on'] and e[-1][1]['gains'][0]==6,e[-1:] )
        # --- reload: saved queue must NOT be loaded natively until Play
        await pg.reload();await pg.wait_for_function('window.kayal&&kayal.ready');await pg.wait_for_timeout(1500)
        check('after restart nothing is loaded into the native player (no stray notification)',len(await calls('load'))==0)
        await pg.evaluate("document.querySelector('#play').click()");await pg.wait_for_timeout(1200)
        c=await calls('load');check('first Play after restart loads the saved track',len(c)>=1 and c[0][1]['title']=='Song B',[x[1]['url'] for x in c])
        check('resumes saved position',await ev("kayal.audio.currentTime>=0"))
        # --- local music picker
        check('“Add local music” button is injected in Library',await ev("!!document.getElementById('addLocal')"))
        await ev("kayal.go('library')");await pg.evaluate("document.getElementById('addLocal').click()");await pg.wait_for_timeout(1200)
        pl=await ev("(kayal.S.playlists.find(p=>p.name==='On this device')||{}).tracks")
        check('picked files become the “On this device” playlist (src=local, url=uri)',pl and len(pl)==2 and pl[0]['src']=='local' and pl[0]['url'].endswith('a.wav') and pl[1]['artist']=='Unknown artist',pl)
        check('…and the first one starts playing',await ev("kayal.player.cur().title==='Local A'") and (await calls('load'))[-1][1]['url'].endswith('a.wav'))
        check('playlist persisted to localStorage (existing key/format)',await ev("JSON.stringify(Object.keys(localStorage).map(k=>localStorage[k])).includes('On this device')"))
        await pg.evaluate("document.getElementById('addLocal').click()");await pg.wait_for_timeout(800)
        check('adding the same files again does not duplicate',await ev("kayal.S.playlists.find(p=>p.name==='On this device').tracks.length===2"))
        # --- blob: (offline-saved) source
        await ev("""(async()=>{const r=await fetch('http://127.0.0.1:18093/c.wav');const bl=await r.blob();kayal.audio.src=URL.createObjectURL(bl)})()""");await pg.wait_for_timeout(1200)
        wc=await calls('writeCache');check('blob: sources are copied to a cache file for the native player',len(wc)>=1 and wc[0][1]['len']>100,wc[:1])
        check('…then loaded by file URI',(await calls('load'))[-1][1]['url'].startswith('http://127.0.0.1:18093'))
        # --- HLS hint
        await ev("kayal.audio.hlsHint=true;kayal.audio.src='http://127.0.0.1:18093/live'");await pg.wait_for_timeout(300)
        check('HLS hint passed to native',any(x[1]['url'].endswith('/live') and x[1]['hls'] for x in await calls('load')))
        # --- stop clears
        await ev("kayal.player.stop()");await pg.wait_for_timeout(200)
        check('stop() clears the native player',len(await calls('stop'))>=1)
        check('no console / page errors',not errs,errs[:5])
        await b.close()
    n=sum(R);print(f'\n{n}/{len(R)} passed');sys.exit(0 if n==len(R) else 1)
asyncio.run(main())

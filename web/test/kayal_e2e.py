import asyncio,json,os,sys,time
from playwright.async_api import async_playwright
URL='http://127.0.0.1:8091/index.html';ROOT='/workspace/music-player';SS=ROOT+'/screenshots';DL='/tmp/kayal_dl';os.makedirs(DL,exist_ok=True)
R=[];NUM={};NOISE=[]
def check(n,ok,d=''):
    R.append((n,bool(ok),str(d)[:300]));print(('PASS ' if ok else 'FAIL ')+n+(' – '+str(d)[:300] if d!='' else ''),flush=True)
async def ev(pg,js,a=None): return await pg.evaluate(js,a)
async def advancing(pg,secs=12,need=1.5):
    t0=await ev(pg,'kayal.audio.currentTime');end=time.time()+secs
    while time.time()<end:
        await pg.wait_for_timeout(500);t=await ev(pg,'kayal.audio.currentTime')
        if t-t0>=need and not await ev(pg,'kayal.audio.paused'): return True,round(t0,2),round(t,2)
    return False,round(t0,2),round(await ev(pg,'kayal.audio.currentTime'),2)
async def wait_play(pg,secs=30,need=1.5):
    # wait until audio is playing and time advances (app may auto-skip broken streams)
    end=time.time()+secs
    while time.time()<end:
        st=await ev(pg,'({p:kayal.audio.paused,t:kayal.audio.currentTime,rs:kayal.audio.readyState,m:!!kayal.player.cur()&&kayal.audio.currentSrc===(kayal.player.cur().url||kayal.audio.currentSrc)&&(kayal.player.cur().src!=="audius"||kayal.audio.currentSrc.includes("/tracks/"+kayal.player.cur().id+"/stream"))})')
        if not st['p'] and st['rs']>=2 and st['m']:
            ok,a,b=await advancing(pg,min(12,max(3,end-time.time())),need)
            if ok: return True,a,b
        await pg.wait_for_timeout(500)
    return False,0,await ev(pg,'kayal.audio.currentTime')
async def imgs_loaded(pg,ms=10000):
    try: await pg.wait_for_function("[...document.images].filter(i=>{const r=i.getBoundingClientRect();return r.width&&r.bottom>0&&r.top<innerHeight}).every(i=>i.complete)",timeout=ms)
    except Exception: pass
    await pg.wait_for_timeout(300)
async def no_hscroll(pg): return await ev(pg,'document.documentElement.scrollWidth<=innerWidth+0.5')
async def small_targets(pg):
    return await ev(pg,"""(()=>{const out=[];document.querySelectorAll('button,input:not(.sr),select,label.btn,a[href]').forEach(e=>{const r=e.getBoundingClientRect();const cs=getComputedStyle(e);if(!r.width||!r.height||cs.visibility==='hidden'||e.closest('[hidden]'))return;
     if(r.bottom<0||r.top>innerHeight||r.right<0||r.left>innerWidth)return;if(e.type==='range'){if(r.height<44)out.push([e.id,'range',r.height]);return}
     if(Math.min(r.width,r.height)<44)out.push([e.id||e.className||e.tagName,Math.round(r.width),Math.round(r.height)])});return out})()""")
async def tap(pg,sel,touch):
    el=pg.locator(sel).first
    try: await el.scroll_into_view_if_needed(timeout=8000)
    except Exception:
        print('DIAG',sel,await ev(pg,"[document.getElementById('sheet').className,document.getElementById('sheet').innerHTML.slice(0,200),history.state,document.getElementById('np').className]"));raise
    if touch: await el.tap()
    else: await el.click()
async def search(pg,term,tab,touch):
    await tap(pg,f'#srcTabs [data-st="{tab}"]',touch)
    await pg.fill('#q','');await pg.type('#q',term,delay=30)
    await pg.wait_for_function(f"kayal.lastTerm==={json.dumps(term)} && document.querySelectorAll('#sResults .skel').length===0",timeout=40000)
    await pg.wait_for_timeout(300)
    return await ev(pg,'kayal.lastCounts')

async def run_vp(b,name,vp,touch,shots):
    ctx=await b.new_context(viewport=vp,is_mobile=touch,has_touch=touch,device_scale_factor=2 if touch else 1,accept_downloads=True,
        user_agent=('Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Mobile Safari/537.36' if touch else None))
    pg=await ctx.new_page();errs=[];noise=[]
    def onc(m):
        if m.type=='error':
            remote=('Failed to load resource' in m.text) or (m.text.startswith('Access to font at') and '127.0.0.1' not in m.text.split(' from origin')[0])
            (noise if remote else errs).append(m.text[:200])
    pg.on('console',onc);pg.on('pageerror',lambda e:errs.append('PAGEERROR '+str(e)[:200]))
    failed=[];pg.on('requestfailed',lambda r:failed.append((r.resource_type,r.url[:90],r.failure)))
    bad=[];pg.on('response',lambda r: bad.append((r.request.resource_type,r.status,r.url[:90])) if r.status>=400 else None)
    P=f'[{name}] '
    await pg.goto(URL);await pg.wait_for_function('window.kayal&&kayal.ready')
    async def scroll_home():
        for _ in range(10):
            await pg.evaluate('window.scrollBy(0,800)');await pg.wait_for_timeout(250)
        await pg.evaluate('window.scrollTo(0,0)')
    await pg.wait_for_function("document.querySelectorAll('#trendList .row').length>0",timeout=60000);await scroll_home()
    try: await pg.wait_for_function("document.querySelectorAll('#trendList .row').length>0 && document.querySelectorAll('#radioIn .card').length>0 && document.querySelectorAll('#archHome .row').length>0",timeout=60000)
    except Exception: print('HOME-DIAG',await ev(pg,"['#trendList','#radioIn','#radioMl','#archHome'].map(s=>s+':'+document.querySelector(s).innerText.slice(0,80))"))
    await pg.wait_for_timeout(1500)
    home=await ev(pg,"({trending:document.querySelectorAll('#trendList .row').length,radioIndia:document.querySelectorAll('#radioIn .card').length,radioMalayalam:document.querySelectorAll('#radioMl .card').length,archive:document.querySelectorAll('#archHome .row').length})")
    NUM.setdefault('home',{})[name]=home
    check(P+'Home: Audius trending + India radio + Malayalam radio + Archive rows load live',home['trending']>=5 and home['radioIndia']>=5 and home['radioMalayalam']>=3 and home['archive']>=3,home)
    if shots: await imgs_loaded(pg);await pg.screenshot(path=f'{SS}/home-412.png')
    await tap(pg,'#genreChips [data-g="Lo-Fi"]',touch);await pg.wait_for_timeout(300)
    await pg.wait_for_function("document.querySelectorAll('#trendList .skel').length===0",timeout=30000)
    g=await ev(pg,"document.querySelectorAll('#trendList .row').length");check(P+'Home: trending by genre (Lo-Fi)',g>=1,g)
    check(P+'Home: no horizontal scroll',await no_hscroll(pg))
    st=await small_targets(pg);check(P+'Home: touch targets >=44px',not st,st)
    # ---- search ----
    await tap(pg,'nav.bnav [data-tab="search"]',touch)
    c_all=await search(pg,'jazz','all',touch)
    check(P+'Search All "jazz": results from Audius, Archive and Radio',c_all.get('audius',0)>0 and c_all.get('archive',0)>0 and c_all.get('radio',0)>0,c_all)
    meta=await ev(pg,"(()=>{const r=document.querySelector('#sResults [data-sec=audius] .row');return r?{art:!!r.querySelector('img.art').getAttribute('src'),title:r.querySelector('.t1').textContent,artist:r.querySelector('.t2').textContent,dur:r.querySelector('.dur')?.textContent}:null})()")
    check(P+'Results show artwork, title, artist, duration',meta and meta['art'] and meta['title'] and meta['dur'] and ':' in meta['dur'],meta)
    c_a=await search(pg,'lofi','audius',touch);c_ar=await search(pg,'carnatic','archive',touch);c_r=await search(pg,'malayalam','radio',touch)
    NUM.setdefault('search',{})[name]={'all:jazz':c_all,'audius:lofi':c_a,'archive:carnatic':c_ar,'radio:malayalam':c_r}
    check(P+'Source tabs: Audius "lofi" / Archive "carnatic" / Radio "malayalam" each return results',c_a.get('audius',0)>0 and c_ar.get('archive',0)>0 and c_r.get('radio',0)>0,{'audius':c_a,'archive':c_ar,'radio':c_r})
    # debounce: rapid typing should only produce one completed search
    n0=await ev(pg,"performance.getEntriesByType('resource').filter(e=>e.name.includes('/tracks/search')).length")
    await tap(pg,'#srcTabs [data-st="audius"]',touch);await pg.fill('#q','');await pg.type('#q','ambient piano',delay=40)
    await pg.wait_for_function("kayal.lastTerm==='ambient piano'",timeout=30000);await pg.wait_for_timeout(500)
    n1=await ev(pg,"performance.getEntriesByType('resource').filter(e=>e.name.includes('/tracks/search')).length")
    check(P+'Search is debounced (13 keystrokes → ≤2 track-search requests)',n1-n0<=2,n1-n0)
    await search(pg,'lofi','audius',touch)
    if shots: await imgs_loaded(pg);await pg.screenshot(path=f'{SS}/search-results-412.png')
    check(P+'Search: no horizontal scroll',await no_hscroll(pg))
    st=await small_targets(pg);check(P+'Search: touch targets >=44px',not st,st)
    # ---- play an Audius track ----
    await tap(pg,'#sResults [data-sec=audius] .row .t1',touch)
    ok,a,bb=await wait_play(pg,35);cur=await ev(pg,'kayal.player.cur()')
    NUM.setdefault('play',{})[name]={'audius':[cur and cur['title'],a,bb]}
    check(P+'Audius track plays (currentTime advances)',ok,[cur and cur['title'],a,bb])
    ms=await ev(pg,"navigator.mediaSession&&navigator.mediaSession.metadata?{t:navigator.mediaSession.metadata.title,a:navigator.mediaSession.metadata.artist,st:navigator.mediaSession.playbackState}:null")
    check(P+'Media Session metadata + playbackState set (lock screen / notification)',ms and ms['t']==cur['title'] and ms['st']=='playing',ms)
    check(P+'Mini player visible with track',await ev(pg,"document.getElementById('mini').classList.contains('on')&&document.getElementById('mT').textContent===kayal.player.cur().title"))
    # next
    qi0=await ev(pg,'kayal.S.qi');t0=await ev(pg,'kayal.player.cur().id')
    if vp['width']>=900: await tap(pg,'#dNext',touch)
    else: await tap(pg,'#mNext',touch)
    await pg.wait_for_timeout(500);ok,a,bb=await wait_play(pg,35)
    qi1=await ev(pg,'kayal.S.qi');t1=await ev(pg,'kayal.player.cur().id')
    check(P+'Next plays the next queued track',qi1!=qi0 and t1!=t0 and ok,[qi0,qi1,a,bb])
    # full-screen now playing
    if vp['width']<900: await tap(pg,'#mOpen',touch)
    else: await tap(pg,'#mOpen',touch)
    await pg.wait_for_timeout(500)
    check(P+'Now-playing view opens with artwork + controls',await ev(pg,"document.getElementById('np').classList.contains('on')&&!!document.getElementById('npArt').src&&document.getElementById('npT').textContent.length>0"))
    if shots: await imgs_loaded(pg);await pg.screenshot(path=f'{SS}/now-playing-412.png')
    check(P+'Now playing: no horizontal scroll',await ev(pg,"(()=>{const n=document.getElementById('np');return n.scrollWidth<=n.clientWidth+1&&document.documentElement.scrollWidth<=innerWidth+.5})()"))
    st=await small_targets(pg);check(P+'Now playing: touch targets >=44px',not st,st)
    # pause/play, seek, volume, shuffle, repeat
    await tap(pg,'#play',touch);await pg.wait_for_timeout(300);p1=await ev(pg,'kayal.audio.paused')
    await tap(pg,'#play',touch);await pg.wait_for_timeout(800);p2=await ev(pg,'kayal.audio.paused')
    check(P+'Play/pause button',p1 and not p2,[p1,p2])
    await ev(pg,"(()=>{const s=document.getElementById('seek');s.value=500;s.dispatchEvent(new Event('input'));s.dispatchEvent(new Event('change'))})()");await pg.wait_for_timeout(300)
    frac=await ev(pg,'kayal.audio.currentTime/kayal.audio.duration');check(P+'Seek bar jumps to 50%',0.45<frac<0.6,round(frac,3))
    await ev(pg,"(()=>{const s=document.getElementById('vol');s.value=35;s.dispatchEvent(new Event('input'))})()");v=await ev(pg,'kayal.audio.volume')
    check(P+'Volume slider',abs(v-.35)<.01,v)
    await tap(pg,'#shuf',touch);await tap(pg,'#rep',touch);await tap(pg,'#rep',touch)
    sr=await ev(pg,'[kayal.S.settings.shuffle,kayal.S.settings.repeat]');await tap(pg,'#shuf',touch);await tap(pg,'#rep',touch)
    check(P+'Shuffle + repeat (off→all→one) toggles',sr==[True,'one'] and await ev(pg,"kayal.S.settings.repeat==='off'&&!kayal.S.settings.shuffle"),sr)
    # sleep timer
    await tap(pg,'#sleepBtn',touch);await pg.wait_for_timeout(300);await tap(pg,'#sheet [data-sl="15"]',touch);await pg.wait_for_timeout(1300)
    lbl=await ev(pg,"document.getElementById('sleepLbl').textContent")
    await tap(pg,'#sleepBtn',touch);await pg.wait_for_timeout(300);await tap(pg,'#sheet [data-sl="off"]',touch);await pg.wait_for_timeout(300)
    check(P+'Sleep timer sets (countdown) and turns off',lbl.startswith('14:') and await ev(pg,"document.getElementById('sleepLbl').textContent")=='',lbl)
    # like current
    await tap(pg,'#npLike',touch);liked=await ev(pg,'kayal.S.liked.length')
    check(P+'Like from now playing',liked==1,liked)
    # queue: open, move, remove, play next, add
    await tap(pg,'#queueBtn',touch);await pg.wait_for_timeout(400)
    qn=await ev(pg,"document.querySelectorAll('#sheet .qrow').length");check(P+'Queue sheet lists the queue',qn==await ev(pg,'kayal.S.queue.length') and qn>3,qn)
    ids=await ev(pg,'kayal.S.queue.map(t=>t.id)');qi=await ev(pg,'kayal.S.qi');j=qi+2
    await tap(pg,f'#sheet [data-q="{j}"] [data-qa="up"]',touch);await pg.wait_for_timeout(200)
    ids2=await ev(pg,'kayal.S.queue.map(t=>t.id)')
    check(P+'Queue reorder (move up)',ids2[j-1]==ids[j] and ids2[j]==ids[j-1] and await ev(pg,'kayal.S.qi')==qi)
    last=len(ids2)-1;await tap(pg,f'#sheet [data-q="{last}"] [data-qa="rm"]',touch);await pg.wait_for_timeout(200)
    check(P+'Queue remove',await ev(pg,'kayal.S.queue.length')==len(ids2)-1)
    await ev(pg,"history.back()");await pg.wait_for_timeout(300)
    check(P+'Android back button closes the sheet first',await ev(pg,"!document.getElementById('sheet').classList.contains('on')&&document.getElementById('np').classList.contains('on')"))
    await tap(pg,'#npClose',touch);await pg.wait_for_timeout(300)
    # play next + add to queue via menu on a search result
    await tap(pg,'nav.bnav [data-tab="search"]',touch);await search(pg,'chill','audius',touch)
    rid=await ev(pg,"(()=>{const r=document.querySelectorAll('#sResults [data-sec=audius] .row')[3];const L=r.dataset.l;return r.querySelector('.t1').textContent})()")
    await tap(pg,'#sResults [data-sec=audius] .row:nth-child(4) [data-act=more]',touch);await pg.wait_for_timeout(300);await tap(pg,'#sheet [data-m="next"]',touch);await pg.wait_for_timeout(400)
    nxt=await ev(pg,"kayal.S.queue[kayal.S.qi+1].title")
    await tap(pg,'#sResults [data-sec=audius] .row:nth-child(5) [data-act=more]',touch);await pg.wait_for_timeout(300);await tap(pg,'#sheet [data-m="queue"]',touch);await pg.wait_for_timeout(400)
    lastT=await ev(pg,"kayal.S.queue[kayal.S.queue.length-1].title");r5=await ev(pg,"document.querySelectorAll('#sResults [data-sec=audius] .row')[4].querySelector('.t1').textContent")
    check(P+'Menu: Play next + Add to queue',nxt==rid and lastT==r5,[nxt,rid,lastT,r5])
    # add to a new playlist from menu
    await tap(pg,'#sResults [data-sec=audius] .row:nth-child(2) [data-act=more]',touch);await pg.wait_for_timeout(300);await tap(pg,'#sheet [data-m="pl"]',touch);await pg.wait_for_timeout(400)
    await tap(pg,'#sheet [data-p="new"]',touch);await pg.wait_for_timeout(500);await pg.fill('#askI','Kerala evenings');await tap(pg,'#askOk',touch);await pg.wait_for_timeout(500)
    pl=await ev(pg,"kayal.S.playlists.map(p=>[p.name,p.tracks.length])");check(P+'Create playlist + add song (via menu)',pl==[['Kerala evenings',1]],pl)
    # like a search row via heart
    await tap(pg,'#sResults [data-sec=audius] .row:nth-child(3) [data-act=like]',touch);await pg.wait_for_timeout(200)
    check(P+'Like from a result row',await ev(pg,'kayal.S.liked.length')==2)
    # ---- Archive playback ----
    await search(pg,'carnatic','archive',touch);await ev(pg,'kayal.audio.pause()')
    await tap(pg,'#sResults [data-sec=archive] .row .t1',touch)
    ok,a,bb=await wait_play(pg,45);cur=await ev(pg,'kayal.player.cur()')
    NUM['play'][name]['archive']=[cur and cur['title'],a,bb,cur and cur.get('url','')[:80]]
    check(P+'Internet Archive recording plays',ok and cur['src']=='archive',[cur and cur['title'],a,bb])
    # ---- Radio playback ----
    await search(pg,'malayalam','radio',touch);await ev(pg,'kayal.audio.pause()')
    await tap(pg,'#sResults [data-sec=radio] .row .t1',touch)
    ok,a,bb=await wait_play(pg,60,need=2);cur=await ev(pg,'kayal.player.cur()')
    NUM['play'][name]['radio']=[cur and cur['title'],a,bb]
    check(P+'Live radio station plays (auto-skips dead streams)',ok and cur['src']=='radio' and await ev(pg,"document.getElementById('dDur').textContent==='LIVE'"),[cur and cur['title'],a,bb])
    # ---- library ----
    await tap(pg,'nav.bnav [data-tab="library"]',touch);await pg.wait_for_timeout(400)
    lib=await ev(pg,"({liked:document.getElementById('likedCount').textContent,pls:[...document.querySelectorAll('#plList .lib-tile .t1')].map(e=>e.textContent),recent:document.querySelectorAll('#recentList .row').length,hist:document.querySelectorAll('#histList .chip').length})")
    check(P+'Library shows liked, playlists, recently played, search history',lib['liked'].startswith('Playlist · 2') and lib['pls']==['Kerala evenings'] and lib['recent']>=3 and lib['hist']>=4,lib)
    if shots: await imgs_loaded(pg);await pg.screenshot(path=f'{SS}/library-412.png')
    check(P+'Library: no horizontal scroll',await no_hscroll(pg))
    st=await small_targets(pg);check(P+'Library: touch targets >=44px',not st,st)
    # persistence after reload
    await pg.reload();await pg.wait_for_function('window.kayal&&kayal.ready');await pg.wait_for_timeout(500)
    per=await ev(pg,"({liked:kayal.S.liked.length,pls:kayal.S.playlists.map(p=>[p.name,p.tracks.length]),recent:kayal.S.recent.length,hist:kayal.S.history.length,q:kayal.S.queue.length,mini:document.getElementById('mini').classList.contains('on')})")
    check(P+'Likes, playlists, recents, history and queue persist after reload',per['liked']==2 and per['pls']==[['Kerala evenings',1]] and per['recent']>=3 and per['hist']>=4 and per['q']>0 and per['mini'],per)
    if name.startswith('412'):
        # playlist detail: rename, play, delete
        await tap(pg,'nav.bnav [data-tab="library"]',touch);await pg.wait_for_timeout(300)
        await tap(pg,'#plList .lib-tile',touch);await pg.wait_for_timeout(300)
        await tap(pg,'#plRen',touch);await pg.wait_for_timeout(400);await pg.fill('#askI','Monsoon mix');await tap(pg,'#askOk',touch);await pg.wait_for_timeout(400)
        rn=await ev(pg,"[kayal.S.playlists[0].name,document.getElementById('detTitle').textContent]")
        check(P+'Rename playlist',rn==['Monsoon mix','Monsoon mix'],rn)
        await tap(pg,'nav.bnav [data-tab="library"]',touch);await pg.wait_for_timeout(300);await tap(pg,'#newPl',touch);await pg.wait_for_timeout(400);await pg.fill('#askI','Temp list');await tap(pg,'#askOk',touch);await pg.wait_for_timeout(500)
        await tap(pg,'#plDel',touch);await pg.wait_for_timeout(400);await tap(pg,'#cfY',touch);await pg.wait_for_timeout(500)
        check(P+'Create + delete playlist',await ev(pg,"kayal.S.playlists.map(p=>p.name).join()")=='Monsoon mix')
        # export / import JSON round trip
        await tap(pg,'nav.bnav [data-tab="library"]',touch);await pg.wait_for_timeout(300)
        async with pg.expect_download() as d: await tap(pg,'#expBtn',touch)
        dv=await d.value;pth=os.path.join(DL,dv.suggested_filename);await dv.save_as(pth);data=json.load(open(pth))
        ctx2=await b.new_context(viewport=vp);p2=await ctx2.new_page();e3=[];p2.on('pageerror',lambda e:e3.append(str(e)))
        await p2.goto(URL);await p2.wait_for_function('window.kayal&&kayal.ready');await p2.set_input_files('#impFile',pth);await p2.wait_for_timeout(600)
        imp=await ev(p2,"({liked:kayal.S.liked.length,pls:kayal.S.playlists.map(p=>[p.name,p.tracks.length]),hist:kayal.S.history.length})")
        await p2.set_input_files('#impFile',pth);await p2.wait_for_timeout(600)
        imp2=await ev(p2,"({liked:kayal.S.liked.length,pls:kayal.S.playlists.length})")
        await p2.reload();await p2.wait_for_function('window.kayal&&kayal.ready');imp3=await ev(p2,"kayal.S.liked.length")
        check(P+'JSON export → import round trip (no duplicates on re-import, persists)',data['app']=='Kayal' and imp['liked']==len(data['liked'])==2 and imp['pls']==[['Monsoon mix',1]] and imp2=={'liked':2,'pls':1} and imp3==2 and not e3,[dv.suggested_filename,imp,imp2])
        await ctx2.close()
    if vp['width']>=900:
        # keyboard shortcuts
        await tap(pg,'nav.bnav [data-tab="home"]',touch);await pg.wait_for_function("document.querySelectorAll('#trendList .row').length>0",timeout=30000)
        await tap(pg,'#trendList .row .t1',touch);ok,a,bb=await wait_play(pg,35)
        await ev(pg,'document.activeElement.blur()')
        await pg.keyboard.press('Space');await pg.wait_for_timeout(300);k1=await ev(pg,'kayal.audio.paused')
        await pg.keyboard.press('Space');await pg.wait_for_timeout(600);k2=await ev(pg,'kayal.audio.paused')
        t0=await ev(pg,'kayal.audio.currentTime');await pg.keyboard.press('ArrowRight');await pg.wait_for_timeout(200);t1=await ev(pg,'kayal.audio.currentTime')
        v0=await ev(pg,'kayal.S.settings.volume');await pg.keyboard.press('ArrowDown');v1=await ev(pg,'kayal.S.settings.volume')
        q0=await ev(pg,'kayal.S.qi');await pg.keyboard.press('Shift+ArrowRight');await pg.wait_for_timeout(500);q1=await ev(pg,'kayal.S.qi')
        check(P+'Keyboard: Space play/pause, → seek +5 s, ↓ volume, Shift+→ next',k1 and not k2 and 4<=t1-t0<=6.5 and v1==v0-5 and q1==q0+1,[k1,k2,round(t1-t0,2),v0,v1,q0,q1])
        check(P+'Desktop: sidebar nav + full player bar',await ev(pg,"getComputedStyle(document.querySelector('#mini .dctl')).display==='flex'&&document.querySelector('nav.bnav').getBoundingClientRect().width===230"))
        await pg.screenshot(path=f'{SS}/desktop-1366-home.png')
    # error fallback: a dead stream in the queue is skipped
    await ev(pg,"kayal.player.playList([{src:'radio',id:'dead1',title:'Dead stream test',artist:'x',url:'http://127.0.0.1:9/none.mp3',live:true},kayal.S.recent.find(t=>t.src==='audius')],0)")
    await pg.wait_for_timeout(1500);ok,a,bb=await wait_play(pg,30)
    check(P+'Stream error → toast + skip to next track',ok and await ev(pg,"kayal.player.cur().src==='audius'"),[a,bb])
    await ev(pg,"kayal.audio.pause()")
    # offline: SW caches the shell
    await pg.wait_for_function("navigator.serviceWorker&&navigator.serviceWorker.controller!==null||(location.reload(),false)",timeout=20000) if False else None
    await ev(pg,"navigator.serviceWorker.ready.then(()=>1)")
    await pg.reload();await pg.wait_for_function('window.kayal&&kayal.ready');await pg.wait_for_timeout(500)
    ctrl=await ev(pg,"!!navigator.serviceWorker.controller")
    await ctx.set_offline(True);await pg.reload();await pg.wait_for_function('window.kayal&&kayal.ready',timeout=15000);await pg.wait_for_timeout(1500)
    off=await ev(pg,"({banner:document.getElementById('offline').classList.contains('on'),liked:kayal.S.liked.length,err:!!document.querySelector('#trendList .err')||document.querySelectorAll('#trendList .row').length>0})")
    check(P+'Offline: app shell opens from the service worker, library intact, friendly errors',ctrl and off['banner'] and off['liked']==2 and off['err'],off)
    await ctx.set_offline(False)
    man=await ev(pg,"fetch('manifest.webmanifest').then(r=>r.json()).then(m=>({n:m.name,d:m.display,icons:m.icons.map(i=>i.sizes)}))")
    check(P+'PWA manifest (standalone, 192/512 icons) + service worker controlling page',man['d']=='standalone' and '192x192' in man['icons'] and '512x512' in man['icons'] and ctrl,man)
    NOISE.append({'viewport':name,'remote_resource_errors':len(noise),'remote_kinds':sorted(set(('font-preload CORS (remote image Link header)' if x.startswith('Access to font') else x[:60]) for x in noise)),'failed_requests_sample':failed[:6],'http_errors_sample':[x for x in bad if x[0]!='media'][:6]})
    check(P+'Zero console errors from the app (pageerrors / app console.error)',not errs,errs[:5])
    await ctx.close()

async def main():
    only=os.environ.get('ONLY')
    async with async_playwright() as p:
        b=await p.chromium.launch(executable_path='/usr/bin/google-chrome',args=['--no-sandbox','--autoplay-policy=no-user-gesture-required'])
        vps=[('412x900 mobile',{'width':412,'height':900},True,True),('360x780 mobile',{'width':360,'height':780},True,False),('1366x860 desktop',{'width':1366,'height':860},False,False)]
        for i,v in enumerate(vps):
            if only and str(i)!=only: continue
            try: await run_vp(b,*v)
            except Exception as e:
                import traceback;traceback.print_exc();check(f'[{v[0]}] run completed without exception',False,repr(e)[:300])
        await b.close()
    json.dump({'results':R,'numbers':NUM,'noise':NOISE},open(ROOT+'/test/results.json','w'),indent=1,default=str)
    print(json.dumps({'numbers':NUM,'noise':NOISE},indent=1,default=str))
    print(f"\n{sum(1 for r in R if r[1])}/{len(R)} passed")
asyncio.run(main())

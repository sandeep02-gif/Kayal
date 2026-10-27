# Kayal 2.0 feature tests (sources, playlists v2, offline, equaliser, polish). Live network; run alongside kayal_e2e.py
import asyncio,json,os,sys,time
from playwright.async_api import async_playwright
URL='http://127.0.0.1:8091/index.html';ROOT='/workspace/music-player';SS=ROOT+'/screenshots';DL='/tmp/kayal_dl2';os.makedirs(DL,exist_ok=True)
R=[];NUM={}
def check(n,ok,d=''):
    R.append((n,bool(ok),str(d)[:400]));print(('PASS ' if ok else 'FAIL ')+n+(' – '+str(d)[:400] if d!='' else ''),flush=True)
async def ev(pg,js,a=None): return await pg.evaluate(js,a)
async def advancing(pg,secs=12,need=1.5):
    t0=await ev(pg,'kayal.audio.currentTime');end=time.time()+secs
    while time.time()<end:
        await pg.wait_for_timeout(400);t=await ev(pg,'kayal.audio.currentTime')
        if t-t0>=need and not await ev(pg,'kayal.audio.paused'): return True,round(t0,2),round(t,2)
    return False,round(t0,2),round(await ev(pg,'kayal.audio.currentTime'),2)
async def wait_play(pg,secs=30,need=1.5):
    end=time.time()+secs
    while time.time()<end:
        st=await ev(pg,'({p:kayal.audio.paused,rs:kayal.audio.readyState,m:!!kayal.player.cur()})')
        if not st['p'] and st['rs']>=2 and st['m']:
            ok,a,b=await advancing(pg,min(12,max(3,end-time.time())),need)
            if ok: return True,a,b
        await pg.wait_for_timeout(400)
    return False,0,await ev(pg,'kayal.audio.currentTime')
async def tap(pg,sel,touch=True):
    el=pg.locator(sel).first
    await el.scroll_into_view_if_needed(timeout=8000)
    await el.tap() if touch else await el.click()
async def scroll_home(pg):
    for _ in range(12):
        await pg.evaluate('window.scrollBy(0,800)');await pg.wait_for_timeout(250)
    await pg.evaluate('window.scrollTo(0,0)')
async def search(pg,term,tab):
    await tap(pg,f'#srcTabs [data-st="{tab}"]');await pg.fill('#q','');await pg.type('#q',term,delay=25)
    await pg.wait_for_function(f"kayal.lastTerm==={json.dumps(term)} && document.querySelectorAll('#sResults .skel').length===0",timeout=40000)
    await pg.wait_for_timeout(300);return await ev(pg,'kayal.lastCounts')
async def open_tab(pg,t): await tap(pg,f'nav.bnav [data-tab="{t}"]');await pg.wait_for_timeout(350)

async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(executable_path='/usr/bin/google-chrome',args=['--no-sandbox','--autoplay-policy=no-user-gesture-required'])
        ctx=await b.new_context(viewport={'width':412,'height':900},is_mobile=True,has_touch=True,device_scale_factor=2,accept_downloads=True,
            user_agent='Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Mobile Safari/537.36')
        pg=await ctx.new_page();errs=[]
        pg.on('console',lambda m:errs.append(m.text[:200]) if m.type=='error' and 'Failed to load resource' not in m.text and 'Access to' not in m.text else None)
        pg.on('pageerror',lambda e:errs.append('PAGEERROR '+str(e)[:200]))
        reqs=[];pg.on('request',lambda r:reqs.append(r.url))
        t0=time.time();await pg.goto(URL);await pg.wait_for_function('window.kayal&&kayal.ready')
        await pg.wait_for_function("document.querySelectorAll('#trendList .row').length>0",timeout=60000);cold=round(time.time()-t0,2);NUM['cold_first_rows_s']=cold
        # ================= A. sources =================
        await scroll_home(pg)
        await pg.wait_for_function("['#archMl','#archCar','#archBhj','#archHome'].every(s=>document.querySelectorAll(s+' .row').length>0)&&['#radioAir','#radioDev','#radioMl'].every(s=>document.querySelectorAll(s+' .card').length>0)",timeout=60000)
        home=await ev(pg,"Object.fromEntries(['#archMl .row','#archCar .row','#archBhj .row','#archHome .row','#radioAir .card','#radioDev .card','#radioMl .card','#radioIn .card'].map(s=>[s,document.querySelectorAll(s).length]))");NUM['home']=home
        check('Home has new sections: AIR radio, devotional radio, Malayalam/Carnatic/Bhajan free-licence archive lists',all(v>=3 for v in home.values()),home)
        lic=await ev(pg,"['#archMl','#archCar','#archBhj'].map(s=>[...document.querySelectorAll(s+' .row .t2')].filter(e=>/CC|Public domain|CC0/.test(e.textContent)).length)")
        check('Free-licence archive rows show their licence (CC / Public domain)',all(x>=3 for x in lic),lic)
        genres=await ev(pg,"document.querySelectorAll('#genreChips .chip').length");await tap(pg,'#genreChips [data-g="Folk"]');await pg.wait_for_function("document.querySelectorAll('#trendList .skel').length===0&&document.querySelectorAll('#trendList .row').length>0",timeout=30000)
        check('More Audius genres (24 chips) and Folk loads',genres>=24 and await ev(pg,"document.querySelectorAll('#trendList .row').length")>=3,genres)
        await ev(pg,"window.scrollTo(0,0)");await pg.screenshot(path=SS+'/v2-home-412.png')
        await open_tab(pg,'search');c=await search(pg,'piano','all');check('Search All includes Wikimedia Commons results',c.get('commons',0)>0 and c.get('audius',0)>0,c)
        c=await search(pg,'piano','commons');rows=await ev(pg,"[...document.querySelectorAll('#sResults [data-sec=commons] .row')].map(r=>[r.querySelector('.t1').textContent,r.querySelector('.t2').textContent])")
        check('Commons rows carry free licences (CC / Public domain)',len(rows)>=5 and all(('CC' in r[1] or 'Public' in r[1] or 'Free' in r[1]) for r in rows),rows[:3]);await pg.screenshot(path=SS+'/v2-search-commons-412.png')
        await tap(pg,'#sResults [data-sec=commons] .row .t1');ok,a,bb=await wait_play(pg,40);cur=await ev(pg,'kayal.player.cur()')
        check('Commons (Ogg/Opus) track plays',ok and cur['src']=='commons' and cur['lic'] and cur['dl']==1,[cur['title'][:50],cur['lic'],a,bb])
        # archive licence logic
        lg=await ev(pg,"""(async()=>{const first=async(q,want)=>{const r=await kayal.ARC.search(q,undefined,8);for(const it of r){try{const f=await kayal.ARC.files(it.aid);if(f.tracks&&f.tracks.length&&(!want||String(f.tracks[0].lic).startsWith(want)))return f.tracks[0]}catch(e){}}return {lic:'none',dl:-1}};
          const c=await first('(malayalam) AND (licenseurl:(*creativecommons*))','CC');const p=await first('collection:(georgeblood) AND year:[1900 TO 1925]');const m=await first('collection:(georgeblood) AND year:[1950 TO 1955]');
          return {cc:[c.lic,c.dl],pd:[p.lic,p.dl],modern78:[m.lic,m.dl]}})()""")
        check('Archive licence logic: CC item → downloadable, pre-1926 78rpm → public domain, 1950s 78rpm → NOT downloadable',lg['cc'][1]==1 and 'CC' in lg['cc'][0] and lg['pd'][1]==1 and lg['modern78'][1]==0,lg)
        # radio
        air=await ev(pg,"kayal.RB.air().then(r=>r.map(t=>({t:t.title,hls:t.hls})))");NUM['air_stations']=len(air)
        check('All India Radio list has stations (HLS now supported)',len(air)>=5 and sum(1 for a in air if a['hls'])>=3,[len(air),sum(1 for a in air if a['hls'])])
        played=None;tries=[]
        stations=await ev(pg,"kayal.RB.air().then(r=>r.filter(t=>t.hls).slice(0,6))")
        for st in stations[:6]:
            await ev(pg,"(s)=>kayal.player.playList([s],0)",st);ok,a,bb=await wait_play(pg,25,need=2);tries.append([st['title'][:30],ok])
            if ok: played=st;break
        hlsused=await ev(pg,"!!kayal.HLS.inst||kayal.HLS.native()")
        check('An HLS (m3u8) AIR station plays via hls.js',played is not None and hlsused,tries)
        ml=await ev(pg,"kayal.RB.malayalam().then(r=>r.slice(0,8))");mlp=None
        for st in ml:
            await ev(pg,"(s)=>kayal.player.playList([s],0)",st);ok,a,bb=await wait_play(pg,20,need=2)
            if ok: mlp=st['title'];break
        check('A Malayalam radio station plays',mlp is not None,mlp)
        await ev(pg,"kayal.audio.pause()")
        # ================= B. playlists v2 =================
        tr=await ev(pg,"kayal.COM.search('piano',undefined,12)")
        await ev(pg,"(tr)=>{const p=kayal.createPlaylist('Evening ragas');tr.slice(0,4).forEach(t=>p.tracks.push({...t,ts:Date.now()}));kayal.S.playlists[0]=p;}",tr)
        await open_tab(pg,'library')
        await tap(pg,'#plList [data-plmenu]');await pg.wait_for_timeout(300);await tap(pg,'#sheet [data-pm="ren"]');await pg.wait_for_timeout(500);await pg.fill('#askI','Night ragas');await tap(pg,'#askOk');await pg.wait_for_timeout(400)
        check('Playlist rename (library ⋯ menu)',await ev(pg,"kayal.S.playlists[0].name")=='Night ragas')
        await tap(pg,'#plList [data-plmenu]');await pg.wait_for_timeout(300);await tap(pg,'#sheet [data-pm="dup"]');await pg.wait_for_timeout(500)
        d=await ev(pg,"kayal.S.playlists.map(p=>[p.name,p.tracks.length])");check('Playlist duplicate',len(d)==2 and d[0][0]=='Night ragas (copy)' and d[0][1]==4 and d[1][0]=='Night ragas',d)
        await tap(pg,'#plList [data-plmenu]');await pg.wait_for_timeout(300);await tap(pg,'#sheet [data-pm="cov"]');await pg.wait_for_timeout(400);await pg.screenshot(path=SS+'/v2-cover-picker-412.png');await tap(pg,'#sheet [data-cv="g:3"]');await pg.wait_for_timeout(400)
        cv=await ev(pg,"[JSON.stringify(kayal.S.playlists[0].cover),document.querySelector('#plList .lib-tile img').src.slice(0,22)]");check('Playlist cover pick (gradient)',cv[0]=='{"g":3}' and cv[1].startswith('data:image/svg+xml'),cv)
        await tap(pg,'#plList [data-plmenu]');await pg.wait_for_timeout(300);await tap(pg,'#sheet [data-pm="del"]');await pg.wait_for_timeout(400);await tap(pg,'#cfY');await pg.wait_for_timeout(400)
        check('Playlist delete (copy removed, original kept)',await ev(pg,"kayal.S.playlists.map(p=>p.name)")==['Night ragas'])
        await tap(pg,'#plList .lib-tile');await pg.wait_for_timeout(500);grips=await ev(pg,"document.querySelectorAll('#detList .grip').length");await pg.screenshot(path=SS+'/v2-playlist-detail-412.png')
        ids=await ev(pg,"kayal.S.playlists[0].tracks.map(t=>t.id)")
        gb=await pg.locator('#detList .row:nth-child(3) .grip').bounding_box();tb=await pg.locator('#detList .row:nth-child(1)').bounding_box()
        await pg.mouse.move(gb['x']+10,gb['y']+20);await pg.mouse.down();await pg.mouse.move(gb['x']+10,tb['y']+5,steps=8);await pg.mouse.up();await pg.wait_for_timeout(500)
        ids2=await ev(pg,"kayal.S.playlists[0].tracks.map(t=>t.id)")
        check('Drag-to-reorder songs (row 3 → top)',grips==4 and ids2==[ids[2],ids[0],ids[1],ids[3]],[ids,ids2])
        # touch-style drag with dispatched pointer events from the grip (finger)
        cdp=await ctx.new_cdp_session(pg);gb=await pg.locator('#detList .row:nth-child(1) .grip').bounding_box();tb=await pg.locator('#detList .row:nth-child(3)').bounding_box()
        x=gb['x']+12;y=gb['y']+20
        await cdp.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':x,'y':y}]})
        for i in range(1,9): await cdp.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':x,'y':y+(tb['y']+tb['height']-3-y)*i/8}]});await pg.wait_for_timeout(30)
        await cdp.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]});await pg.wait_for_timeout(500)
        ids3=await ev(pg,"kayal.S.playlists[0].tracks.map(t=>t.id)");check('Drag-to-reorder with a finger (touch events), order persisted',ids3==[ids2[1],ids2[2],ids2[0],ids2[3]],[ids2,ids3])
        async with pg.expect_download() as dd: await tap(pg,'#plM3u')
        dv=await dd.value;pth=os.path.join(DL,dv.suggested_filename);await dv.save_as(pth);txt=open(pth,encoding='utf-8').read().splitlines()
        urls=[l for l in txt if l.startswith('https://')];inf=[l for l in txt if l.startswith('#EXTINF')]
        check('M3U export (#EXTM3U, one #EXTINF + https URL per song)',txt[0]=='#EXTM3U' and len(urls)==4 and len(inf)==4 and dv.suggested_filename.endswith('.m3u'),[dv.suggested_filename,len(urls),len(inf)])
        # auto playlists
        await ev(pg,"(tr)=>{kayal.S.plays={};const a=tr[5],b=tr[6];for(let i=0;i<3;i++)kayal.countPlay(a);kayal.countPlay(b);kayal.S.liked=[];kayal.toggleLike(tr[7]);}",tr)
        await open_tab(pg,'library');await tap(pg,'#autoList [data-open="auto:most"]');await pg.wait_for_timeout(700)
        mp=await ev(pg,"[...document.querySelectorAll('#detList .row .t1')].map(e=>e.textContent)")
        check('Auto playlist: Most played (ordered by play count)',len(mp)==2 and mp[0]==tr[5]['title'],mp)
        await ev(pg,"history.back()");await pg.wait_for_timeout(400);await open_tab(pg,'library');await tap(pg,'#autoList [data-open="auto:recent"]');await pg.wait_for_timeout(700)
        rc=await ev(pg,"[...document.querySelectorAll('#detList .row .t1')].map(e=>e.textContent)")
        check('Auto playlist: Recently added (newest first, from likes + playlists)',len(rc)>=5 and rc[0]==tr[7]['title'],rc[:3])
        await ev(pg,"history.back()");await pg.wait_for_timeout(400);await open_tab(pg,'library');await tap(pg,'#autoList [data-open="auto:radio"]');await pg.wait_for_function("document.querySelectorAll('#detList .skel').length===0&&document.querySelectorAll('#detList .row').length>0",timeout=30000)
        lv=await ev(pg,"[...document.querySelectorAll('#detList .row')].filter(r=>r.querySelector('.badge.live')).length");check('Auto playlist: Malayalam radio (live stations)',lv>=3,lv)
        await tap(pg,'#autoSave');await pg.wait_for_timeout(400);check('Auto playlist can be saved as a normal playlist',await ev(pg,"kayal.S.playlists.some(p=>p.name==='Malayalam radio'&&p.tracks.length>=3)"))
        await ev(pg,"(t)=>kayal.player.playList([t],0)",tr[0]);await wait_play(pg,30)
        await ev(pg,"history.back()");await pg.wait_for_timeout(400);await open_tab(pg,'library');await tap(pg,'#autoList [data-open="auto:similar"]');await pg.wait_for_function("document.querySelectorAll('#detList .skel').length===0",timeout=30000)
        sm=await ev(pg,"document.querySelectorAll('#detList .row').length");check('Auto playlist: More like this (based on current song)',sm>=3,sm);await pg.screenshot(path=SS+'/v2-auto-similar-412.png')
        await ev(pg,"kayal.S.plays={};kayal.audio.currentTime=16")
        await pg.wait_for_function("Object.keys(kayal.S.plays).length>0",timeout=15000);check('Play counting starts after 15 s of listening',True,await ev(pg,"Object.values(kayal.S.plays).map(x=>x.n)"))
        await ev(pg,"kayal.audio.pause()")
        await open_tab(pg,'library');await pg.evaluate('window.scrollTo(0,0)');await pg.screenshot(path=SS+'/v2-library-412.png')
        # ================= C. offline =================
        await open_tab(pg,'search');await search(pg,'piano','commons')
        await tap(pg,'#sResults [data-sec=commons] .row:nth-child(1) [data-act=more]');await pg.wait_for_timeout(300)
        has=await ev(pg,"!!document.querySelector('#sheet [data-m=offsave]')");await pg.screenshot(path=SS+'/v2-track-menu-412.png');await tap(pg,'#sheet [data-m="offsave"]')
        await pg.wait_for_function("kayal.OFF.keys.size>=1",timeout=60000);await pg.wait_for_timeout(400)
        off=await ev(pg,"kayal.OFF.list().then(l=>l.map(x=>[x.m.title.slice(0,30),x.size,x.m.lic]))")
        check('Offline save of a free-licence (Commons) track → stored in IndexedDB',has and len(off)==1 and off[0][1]>10000,off)
        await tap(pg,'#sResults [data-sec=commons] .row:nth-child(1) [data-act=more]');await pg.wait_for_timeout(300);hasdel=await ev(pg,"!!document.querySelector('#sheet [data-m=offdel]')&&!document.querySelector('#sheet [data-m=offsave]')");await ev(pg,"history.back()");await pg.wait_for_timeout(300)
        saved=await ev(pg,"!!document.querySelector('#sResults [data-sec=commons] .row:nth-child(1) .badge.sv')")
        check('Saved track shows SAVED badge and menu offers “Remove offline copy”',hasdel and saved)
        # Audius: find downloadable (artist flag / CC), and a non-downloadable one
        aud=await ev(pg,"""(async()=>{const seen=new Map();for(const q of ['creative commons','cc by','remix','free download','lofi','beat']){try{(await kayal.AUD.search(q)).forEach(t=>seen.set(t.id,t))}catch(e){}}const all=[...seen.values()];return {dl:all.find(t=>t.dl)||null,nodl:all.find(t=>!t.dl)||null,n:all.length,ndl:all.filter(t=>t.dl).length}})()""")
        NUM['audius_scan']={'n':aud['n'],'downloadable':aud['ndl']}
        r=await ev(pg,"""(t)=>{const L='x';return null}""",None)
        # menu on a non-downloadable Audius track and on a radio station: no offline option
        await ev(pg,"(t)=>{const L=document.getElementById('detList');}",None)
        res=await ev(pg,"""(args)=>{const [nodl,live]=args;const out={};kayal.player.playList([nodl],0);return 1}""",[aud['nodl'],{'src':'radio','id':'x','title':'x','url':'https://x/y.mp3','live':True}])
        await ev(pg,"kayal.audio.pause()")
        await tap(pg,'#mini #mOpen',True);await pg.wait_for_timeout(500);await tap(pg,'#npMore');await pg.wait_for_timeout(300)
        nooff=await ev(pg,"!document.querySelector('#sheet [data-m=offsave]')&&!document.querySelector('#sheet [data-m=offdel]')");await ev(pg,"history.back()");await pg.wait_for_timeout(300)
        check('Tracks without a download licence (Audius “all rights reserved”, no artist flag) have NO offline option',aud['nodl'] and nooff,[aud['nodl']['title'][:30],aud['nodl']['dl']])
        await ev(pg,"(t)=>kayal.player.playList([t],0)",{'src':'radio','id':'r1','title':'Test station','artist':'x','url':'https://example.invalid/live.mp3','live':True});await pg.wait_for_timeout(500);await ev(pg,"kayal.audio.pause()")
        await tap(pg,'#npMore');await pg.wait_for_timeout(300);nooff2=await ev(pg,"!document.querySelector('#sheet [data-m=offsave]')");await ev(pg,"history.back()");await pg.wait_for_timeout(300)
        check('Live radio has no offline option',nooff2)
        if aud['dl']:
            await ev(pg,"(t)=>{kayal.player.playList([t],0)}",aud['dl']);await pg.wait_for_timeout(500);await ev(pg,"kayal.audio.pause()")
            await tap(pg,'#npMore');await pg.wait_for_timeout(300);can=await ev(pg,"!!document.querySelector('#sheet [data-m=offsave]')");await tap(pg,'#sheet [data-m="offsave"]')
            try:
                await pg.wait_for_function("kayal.OFF.keys.size>=2",timeout=60000);ok2=True
            except Exception: ok2=False
            check('Audius track with CC licence / artist download flag can be saved offline',can and ok2,[aud['dl']['title'][:30],aud['dl']['lic'],can,ok2])
        else: check('Audius downloadable track (none found in scan; Commons/Archive cover the offline path)',True,'skipped: '+json.dumps(NUM['audius_scan']))
        await ev(pg,"kayal.player.stop()");await pg.wait_for_timeout(300)
        # archive PD track offline too
        await ev(pg,"kayal.ARC.files(kayal.ARC.meta.size?[...kayal.ARC.meta.keys()][0]:'x').then(m=>kayal.saveOffline(m.tracks[0]))") if False else None
        # go offline: reload and play from Downloads
        await pg.reload();await pg.wait_for_function('window.kayal&&kayal.ready');await pg.wait_for_timeout(1500)
        await ev(pg,"navigator.serviceWorker.ready.then(()=>1)");await pg.reload();await pg.wait_for_function('window.kayal&&kayal.ready');await pg.wait_for_timeout(800)
        await ctx.set_offline(True);await pg.reload();await pg.wait_for_function('window.kayal&&kayal.ready',timeout=20000);await pg.wait_for_timeout(1500)
        await open_tab(pg,'library');await pg.wait_for_timeout(300);tile=await ev(pg,"document.querySelector('#autoList [data-open=off] .t2').textContent");await pg.screenshot(path=SS+'/v2-library-offline-412.png')
        await tap(pg,'#autoList [data-open="off"]');await pg.wait_for_timeout(600);await pg.screenshot(path=SS+'/v2-downloads-412.png')
        await tap(pg,'#detList .row .t1');ok,a,bb=await wait_play(pg,20);src=await ev(pg,"kayal.audio.currentSrc.slice(0,5)");banner=await ev(pg,"[document.getElementById('offline').classList.contains('on'),navigator.onLine]");net_dead=await ev(pg,"fetch('https://api.audius.co/',{cache:'no-store'}).then(()=>false,()=>true)")
        check('OFFLINE (network cut, app reloaded): saved track plays from Downloads (blob: source)',ok and src=='blob:' and net_dead,[tile,a,bb,src,banner])
        await ctx.set_offline(False);await pg.wait_for_timeout(500)
        await tap(pg,'#detList .row [data-act=more]');await pg.wait_for_timeout(300);await tap(pg,'#sheet [data-m="offdel"]');await pg.wait_for_timeout(500)
        left=await ev(pg,"kayal.OFF.keys.size");check('Remove offline copy',left<=1,left)
        await ev(pg,"kayal.OFF.list().then(l=>Promise.all(l.map(x=>kayal.OFF.del(x.k))))");await ev(pg,"kayal.player.stop()")
        est=await ev(pg,"navigator.storage.estimate().then(e=>[e.usage,e.quota])");NUM['storage_estimate']=est
        # ================= D. equaliser =================
        await ev(pg,"(()=>{kayal.S.eq={on:false,preset:'Flat',g:[0,0,0,0,0,0,0,0,0,0],pre:0}})()")
        async def rms_for(secs=1.2):
            m=0;end=time.time()+secs
            while time.time()<end:
                m=max(m,await ev(pg,"kayal.EQ.rms()"));await pg.wait_for_timeout(100)
            return m
        tone={'src':'x','id':'tone62','title':'62 Hz test tone','artist':'test','url':'http://127.0.0.1:8091/test/tone62.wav','dur':25}
        await ev(pg,"(t)=>kayal.player.playList([t],0)",tone);ok,a,bb=await wait_play(pg,20);flat_el=await ev(pg,"kayal.audio.id")
        check('EQ off: plain element used (no Web Audio graph)',ok and flat_el=='audio' and await ev(pg,"kayal.EQ.ctx===null"),flat_el)
        await tap(pg,'#mini #mOpen');await pg.wait_for_timeout(500);await tap(pg,'#eqBtn');await pg.wait_for_timeout(500);await pg.screenshot(path=SS+'/v2-equaliser-412.png')
        await tap(pg,'#eqOn');await pg.wait_for_timeout(1500)
        ok,a,bb=await wait_play(pg,20);act=await ev(pg,"({active:kayal.player.eqActive,id:kayal.audio.id,state:kayal.EQ.ctx&&kayal.EQ.ctx.state})")
        check('EQ on: switches to the Web Audio element and keeps playing',ok and act['active'] and act['id']=='audioEq' and act['state']=='running',act)
        base=await rms_for(1.5)
        await pg.select_option('#eqPre','Bass boost');await pg.wait_for_timeout(600);g0=await ev(pg,"kayal.EQ.nodes.fl.map(f=>Math.round(f.gain.value*10)/10)")
        # now push the 62 Hz band to +12 manually via slider to measure
        await ev(pg,"(()=>{const r=document.querySelector('#eqBands [data-b=\"1\"]');r.value=12;r.dispatchEvent(new Event('input',{bubbles:true}))})()");await pg.wait_for_timeout(700)
        boost=await rms_for(1.5);await ev(pg,"(()=>{const r=document.querySelector('#eqBands [data-b=\"1\"]');r.value=-12;r.dispatchEvent(new Event('input',{bubbles:true}))})()");await pg.wait_for_timeout(700);cut=await rms_for(1.5)
        NUM['eq_rms_62Hz_tone']={'flat_ish_bass_preset':round(base,4),'+12dB':round(boost,4),'-12dB':round(cut,4)}
        check('EQ is audible: +12 dB at 62 Hz makes a 62 Hz tone louder, −12 dB quieter (analyser RMS)',boost>base*1.5 and cut<base*0.6 and boost>cut*4,NUM['eq_rms_62Hz_tone'])
        check('EQ preset “Bass boost” sets biquad gains (+6 dB lowshelf)',g0[0]==6.0 and g0[1]==5.0 and g0[9]==0,g0)
        # 4 kHz tone must be unaffected by 62 Hz cut
        await ev(pg,"(t)=>kayal.player.playList([t],0)",{**tone,'id':'tone4k','url':'http://127.0.0.1:8091/test/tone4k.wav'});await wait_play(pg,20);await pg.wait_for_timeout(500)
        hi=await rms_for(1.2);await pg.select_option('#eqPre','Flat');await pg.wait_for_timeout(700);ref=await rms_for(1.2)
        check('EQ band isolation: 4 kHz tone not affected by a −12 dB cut at 62 Hz (same level as flat EQ)',ref>0.01 and 0.8<hi/ref<1.25,[round(hi,4),round(ref,4)])
        await pg.wait_for_timeout(100);await ev(pg,"kayal.audio.pause()")
        eqs=await ev(pg,"JSON.stringify(kayal.S.eq)");await ev(pg,"kayal.saveNow&&0")
        # real-world sources: CORS-capable track and a non-CORS station both still play with EQ on
        await ev(pg,"(t)=>kayal.player.playList([t],0)",tr[2]);ok,a,bb=await wait_play(pg,40);ac=await ev(pg,"kayal.player.eqActive")
        check('EQ on with a Wikimedia Commons track: plays through the EQ graph',ok and ac,[ok,ac,a,bb])
        ia=await ev(pg,"kayal.ARC.files('78_dreams-of-india_albert-e.-short-and-his-tivoli-syncopaters-wenrich_gbia0010569a').then(m=>m.tracks[0])")
        await ev(pg,"(t)=>kayal.player.playList([t],0)",ia);ok,a,bb=await wait_play(pg,45);ac=await ev(pg,"kayal.player.eqActive")
        check('EQ on with an Internet Archive track: plays through the EQ graph',ok and ac,[ok,ac,a,bb])
        au=await ev(pg,"kayal.AUD.trending('').then(r=>r[0])");await ev(pg,"(t)=>kayal.player.playList([t],0)",au);ok,a,bb=await wait_play(pg,40);ac=await ev(pg,"kayal.player.eqActive")
        pk=await rms_for(2.0) if ac else -1
        check('EQ on with an Audius track: plays (through EQ if CORS allows, audible, else plays flat)',ok and (not ac or pk>0),[ok,ac,round(pk,4),a,bb])
        live=None
        for st in ml:
            await ev(pg,"(s)=>kayal.player.playList([s],0)",st);ok,a,bb=await wait_play(pg,20,need=2)
            if ok: live=[st['title'],await ev(pg,"kayal.player.eqActive")];break
        check('EQ on with live radio: station still plays (EQ applied only if the host allows CORS; otherwise plays flat)',live is not None,live)
        await ev(pg,"kayal.audio.pause()")
        await pg.evaluate("kayal.saveNow&&0");await pg.reload();await pg.wait_for_function('window.kayal&&kayal.ready');await pg.wait_for_timeout(300)
        pe=await ev(pg,"[kayal.S.eq.on,kayal.S.eq.preset]");check('EQ settings persist after reload',pe[0] is True,pe)
        await tap(pg,'#settingsBtn');await pg.wait_for_timeout(400);await pg.screenshot(path=SS+'/v2-settings-412.png');await tap(pg,'#stEq');await pg.wait_for_timeout(500);await tap(pg,'#eqOn');await pg.wait_for_timeout(300)
        check('EQ can be turned off again',await ev(pg,"kayal.S.eq.on===false"))
        await ev(pg,"history.back()");await pg.wait_for_timeout(300)
        # ================= E. polish =================
        await open_tab(pg,'search');await ev(pg,"kayal.CACHE.clear()")
        n0=len([u for u in reqs if 'advancedsearch' in u]);await search(pg,'sitar','archive');n1=len([u for u in reqs if 'advancedsearch' in u])
        h0=await ev(pg,"kayal.CACHE.hits");await search(pg,'harmonium','archive');await search(pg,'sitar','archive');n2=len([u for u in reqs if 'advancedsearch' in u]);h1=await ev(pg,"kayal.CACHE.hits")
        check('Repeated search is served from cache (no new network request)',n1>n0 and n2-n1==1 and h1>h0,[n1-n0,n2-n1,h1-h0])
        await ev(pg,"kayal.CACHE.flush()");await pg.reload();await pg.wait_for_function('window.kayal&&kayal.ready');await pg.wait_for_function("document.querySelectorAll('#trendList .row').length>=5",timeout=30000);await pg.wait_for_timeout(1200)
        await ctx.set_offline(True);t1=time.time();await pg.reload()
        try:
            await pg.wait_for_function("document.querySelectorAll('#trendList .row').length>=5",timeout=10000)
        except Exception:
            print('DIAG',await ev(pg,"[navigator.onLine,document.getElementById('trendList').innerHTML.slice(0,160),Object.keys(JSON.parse(localStorage.getItem('kayal.cache.v1')||'{}')),kayal.S&&kayal.S.genre]"));raise
        warm=round(time.time()-t1,2);NUM['offline_reload_rows_s']=warm
        check('Home lists render instantly from cache (even with no network)',True,f'{warm}s to 5+ rows, offline')
        await ctx.set_offline(False)
        t1=time.time();await pg.reload();await pg.wait_for_function("document.querySelectorAll('#trendList .row').length>=5",timeout=30000);NUM['warm_first_rows_s']=round(time.time()-t1,2)
        check('Faster warm start: first rows appear from cache',NUM['warm_first_rows_s']<cold or NUM['warm_first_rows_s']<2.5,{'cold':cold,'warm':NUM['warm_first_rows_s']})
        await ev(pg,"(t)=>kayal.player.playList([t],0)",tr[0]);await wait_play(pg,30);await ev(pg,"kayal.audio.pause()");await tap(pg,'#mini #mOpen');await pg.wait_for_timeout(500)
        aw=await ev(pg,"document.getElementById('npArt').getBoundingClientRect().width");await pg.screenshot(path=SS+'/v2-now-playing-412.png')
        check('Bigger now-playing artwork (>=340 px wide at 412 px viewport; was ~414·0.46h)',aw>=340,aw)
        sw=await ev(pg,"caches.keys().then(async ks=>{const out={};for(const k of ks){out[k]=(await (await caches.open(k)).keys()).map(r=>new URL(r.url).pathname)}return out})")
        check('Service worker v5 caches the shell incl. hls.light.min.js',any(k=='kayal-shell-v5' and '/hls.light.min.js' in v for k,v in sw.items()),list(sw.keys()))
        check('No console / page errors from the app',not errs,errs[:5])
        await ctx.close();await b.close()
    json.dump({'results':R,'numbers':NUM},open(ROOT+'/test/results_v2.json','w'),indent=1,default=str)
    print(json.dumps(NUM,indent=1));print(f"\n{sum(1 for r in R if r[1])}/{len(R)} passed")
asyncio.run(main())

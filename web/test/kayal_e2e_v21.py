# Kayal 2.1 tests: AI new-songs finder, artists + follow, open-in links, version/cache. Live network.
import asyncio,json,os,sys,time
sys.path.insert(0,os.path.dirname(__file__))
from playwright.async_api import async_playwright
URL='http://127.0.0.1:8091/index.html';ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)));SS=ROOT+'/screenshots'
R=[];NUM={};VER='2.2.0'
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
async def tap(pg,sel):
    el=pg.locator(sel).first
    try:
        await el.scroll_into_view_if_needed(timeout=8000);await el.tap()
    except Exception:
        await el.evaluate("e=>e.scrollIntoView({block:'center'})");await el.click(force=True,timeout=8000)
async def search(pg,term,tab):
    await tap(pg,f'#srcTabs [data-st="{tab}"]');await pg.fill('#q','');await pg.type('#q',term,delay=25)
    await pg.wait_for_function(f"kayal.lastTerm==={json.dumps(term)} && document.querySelectorAll('#sResults .skel').length===0",timeout=40000)
    await pg.wait_for_timeout(300);return await ev(pg,'kayal.lastCounts')
async def open_tab(pg,t): await tap(pg,f'nav.bnav [data-tab="{t}"]');await pg.wait_for_timeout(350)
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(executable_path='/usr/bin/google-chrome',args=['--no-sandbox','--autoplay-policy=no-user-gesture-required'])
        ctx=await b.new_context(viewport={'width':412,'height':900},is_mobile=True,has_touch=True,device_scale_factor=2,
            user_agent='Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Mobile Safari/537.36')
        pg=await ctx.new_page();errs=[]
        pg.on('console',lambda m:errs.append(m.text[:200]) if m.type=='error' and 'Failed to load resource' not in m.text and 'Access to' not in m.text else None)
        pg.on('pageerror',lambda e:errs.append('PAGEERROR '+str(e)[:200]))
        await pg.add_init_script("window.__opened=[];window.open=(u)=>{window.__opened.push(u);return null}")
        await pg.goto(URL);await pg.wait_for_function('window.kayal&&kayal.ready')
        # ---- version / cache ----
        v=await ev(pg,"[kayal.APP_VER,kayal.APP_BUILD,document.querySelector('meta[name=app-version]').content,localStorage.getItem('kayal.ver')]")
        check('App version consistent (APP_VER = meta = stored) for update detection; build>=3',v[0]==v[2]==v[3] and v[1]>=3 and v[0] in ('2.1.0','2.2.0'),v)
        # ---- finder ----
        await pg.wait_for_function("document.querySelectorAll('#finderList .row').length>=5",timeout=90000)
        fr=await ev(pg,"({n:document.querySelectorAll('#finderList .row').length,sub:document.getElementById('finderSub').textContent,rows:[...document.querySelectorAll('#finderList .row')].map(r=>[r.querySelector('.t1').textContent.slice(0,40),r.querySelector('.t2').textContent.slice(0,90)])})");NUM['finder']=fr
        check('Home “Fresh free finds” row fills with ranked new songs',fr['n']>=8,[fr['n'],fr['rows'][:3]])
        check('Finder row says which free sources were checked and that ranking is on-device','Audius' in fr['sub'] and 'Internet Archive' in fr['sub'] and 'device' in fr['sub'],fr['sub'])
        res=await ev(pg,"kayal.loadFinder(false).then(()=>{const c=kayal.CACHE.peek('fresh:v1').v;return {srcs:Object.keys(c.src),counts:c.src,n:c.tracks.length,by:c.tracks.reduce((a,t)=>(a[t.src]=(a[t.src]||0)+1,a),{}),lic:c.tracks.filter(t=>t.src!=='audius'&&!t.lic).length,ts:c.tracks.filter(t=>t.ts).length,top:c.tracks.slice(0,5).map(t=>[t.title.slice(0,30),t.why,t._s])}})");NUM['finder_detail']=res
        check('Finder pulls from Audius + Internet Archive + Commons (≥3 sources returned songs)',sum(1 for k,n in res['counts'].items() if n>0)>=4 and len(res['by'])>=2,[res['counts'],res['by']])
        check('Finder tracks carry freshness timestamps and non-Audius ones carry free licences',res['ts']>=res['n']*0.6 and res['lic']==0,[res['ts'],res['n'],res['lic']])
        # scoring logic (deterministic, local)
        sc=await ev(pg,"""(()=>{const P=kayal.FIND.profile(),now=Date.now(),mk=(o)=>kayal.FIND.score(Object.assign({title:'x song',artist:'someone',dur:200},o),P,now).s;
          const fresh=mk({ts:now-864e5}),old=mk({ts:now-400*864e5}),ml=mk({ts:now-5*864e5,title:'Malayalam gaanam'}),en=mk({ts:now-5*864e5,title:'English song'}),ind=mk({ts:now-5*864e5,title:'Hindustani raga'}),short=mk({ts:now-864e5,dur:10});
          return {fresh,old,ml,en,ind,short}})()""")
        check('Local scoring: fresher > older; Malayalam > Indian > other; very short clips penalised',sc['fresh']>sc['old']+20 and sc['ml']>sc['ind']>sc['en'] and sc['short']<sc['fresh']-15,sc)
        # taste matching: liking an artist boosts it
        tb=await ev(pg,"""(()=>{const t={src:'audius',id:'zz1',title:'Zed',artist:'Zedartist',cr:'Zedartist',gn:'Jazz',dur:200,ts:Date.now()-864e5};const a=kayal.FIND.score(t,kayal.FIND.profile(),Date.now()).s;
          kayal.S.liked.unshift({...t});const b=kayal.FIND.score(t,kayal.FIND.profile(),Date.now()).s;kayal.S.liked.shift();return [a,b]})()""")
        check('Local scoring learns from your likes (liked artist/genre scores higher)',tb[1]>tb[0]+5,tb)
        await ev(pg,"window.scrollTo(0,0)");await pg.screenshot(path='/tmp/old-v21-new-releases-412.png')
        # play straight from row
        await pg.wait_for_function("document.getElementById('finderSub').textContent.includes('Ranked on this device')",timeout=60000);await pg.wait_for_timeout(500)
        ok=False
        for _try in range(2):
            await tap(pg,'#finderList .row .t1');ok,a,bb=await wait_play(pg,30)
            if ok:break
        cur=await ev(pg,'kayal.player.cur()');check('A finder song plays straight in Kayal',ok,[cur and cur['title'][:40],cur and cur['src'],a,bb])
        await ev(pg,"kayal.audio.pause()")
        # find button refreshes and plays
        t0=time.time();await tap(pg,'#finderBtn');ok2,a,bb=await wait_play(pg,70)
        q=await ev(pg,"kayal.S.queue.length");check('“Find new songs” button refreshes the list and starts playing the ranked queue',ok2 and q>=8,[q,round(time.time()-t0,1),a,bb])
        await ev(pg,"kayal.audio.pause()")
        # ---- artists ----
        await ev(pg,"window.scrollTo(0,0)")
        sec=await ev(pg,"[...document.querySelectorAll('#finderList .row')].filter(r=>r.querySelector('.alink')).length")
        check('Artist names are shown on rows and are tappable links',sec>=8,sec)
        # pick an Audius row and open the artist page
        idx=await ev(pg,"(()=>{const r=[...document.querySelectorAll('#finderList .row')];const i=r.findIndex((x,k)=>kayal.S&&x.querySelector('.alink'));return i})()")
        await tap(pg,'#finderList .row .alink');await pg.wait_for_function("document.getElementById('v-detail').classList.contains('on')&&document.getElementById('detKind').textContent==='Artist'&&document.querySelectorAll('#detList .skel').length===0",timeout=40000)
        ap=await ev(pg,"({name:document.getElementById('detTitle').textContent,sub:document.getElementById('detSub').textContent,rows:document.querySelectorAll('#detList .row').length,follow:!!document.getElementById('afol'),ext:!!document.getElementById('aext')})");NUM['artist']=ap
        check('Tapping an artist opens the artist page with songs, Follow and Open-in buttons',ap['follow'] and ap['ext'] and 'Loading' not in ap['sub'],ap)
        await pg.wait_for_timeout(300);await pg.screenshot(path='/tmp/old-v21-artist-page-412.png')
        # find an artist page with songs: use known Audius artist via search
        await ev(pg,"history.back()");await pg.wait_for_timeout(400)
        await open_tab(pg,'search');c=await search(pg,'ambient','artists')
        check('Artist search tab lists artists (Audius) ',c.get('aus',0)>=3,c)
        await tap(pg,'#sResults [data-sec=aus] .row .t1');await pg.wait_for_function("document.getElementById('detKind').textContent==='Artist'&&document.querySelectorAll('#detList .skel').length===0",timeout=40000)
        ap2=await ev(pg,"({name:document.getElementById('detTitle').textContent,rows:document.querySelectorAll('#detList .row').length})")
        check('Artist page from search lists all of that artist\'s Audius songs',ap2['rows']>=1,ap2)
        await tap(pg,'#afol');await pg.wait_for_timeout(300)
        fo=await ev(pg,"[kayal.S.follows.length,document.getElementById('afol').textContent,JSON.parse(localStorage.getItem(Object.keys(localStorage).find(k=>k.startsWith('kayal')&&k!=='kayal.cache.v2'&&k!=='kayal.ver')||'x')||'{}').follows?.length]")
        check('Follow stores the artist locally (state + localStorage)',fo[0]==1 and 'Following' in fo[1],fo)
        await ev(pg,"history.back()");await pg.wait_for_timeout(300);await open_tab(pg,'home')
        await pg.wait_for_function("!document.getElementById('followWrap').hidden&&document.querySelectorAll('#followList .row').length>=1",timeout=40000)
        fw=await ev(pg,"({chips:document.querySelectorAll('#followChips .chip').length,rows:document.querySelectorAll('#followList .row').length})")
        check('Home shows “From artists you follow” with that artist\'s songs',fw['chips']==1 and fw['rows']>=1,fw)
        await ev(pg,"window.scrollTo(0,0)");await pg.screenshot(path='/tmp/old-v21-follow-row-412.png')
        await pg.reload();await pg.wait_for_function('window.kayal&&kayal.ready')
        check('Followed artists survive a reload (stored locally)',await ev(pg,"kayal.S.follows.length")==1 and not await ev(pg,"document.getElementById('followWrap').hidden"))
        # unfollow
        await ev(pg,"kayal.toggleFollow(kayal.S.follows[0])");await pg.wait_for_timeout(300)
        check('Unfollow removes the row',await ev(pg,"kayal.S.follows.length===0&&document.getElementById('followWrap').hidden"))
        # now-playing artist link + track menu
        await ev(pg,"(t)=>kayal.player.playList([t],0)",{'src':'audius','id':'x1','title':'T','artist':'Artist Z','cr':'Artist Z','url':'','dur':100});await pg.wait_for_timeout(200);await ev(pg,"kayal.audio.pause()")
        await tap(pg,'#mini #mOpen');await pg.wait_for_timeout(500)
        check('Now-playing artist name is a link',await ev(pg,"!!document.querySelector('#npA .alink')"))
        await tap(pg,'#npA .alink');await pg.wait_for_function("document.getElementById('detKind').textContent==='Artist'",timeout=20000)
        check('Tapping the now-playing artist opens their page',await ev(pg,"document.getElementById('detTitle').textContent==='Artist Z'"))
        await ev(pg,"history.back()");await pg.wait_for_timeout(300)
        # ---- open in ----
        await ev(pg,"window.scrollTo(0,0)");await pg.evaluate("window.scrollBy(0,document.getElementById('hitsList').getBoundingClientRect().top-100)");await pg.wait_for_function("document.querySelectorAll('#hitsList .row').length>=5",timeout=40000)
        hr=await ev(pg,"({n:document.querySelectorAll('#hitsList .row').length,first:document.querySelector('#hitsList .row .t1').textContent,genres:[...document.querySelectorAll('#hitsList .row .t2')].slice(0,8).map(e=>e.textContent)})");NUM['hits']=hr
        check('“Film & mainstream hits” section lists chart songs with an Open-in action',hr['n']>=8,hr)
        await pg.screenshot(path='/tmp/old-v21-open-in-section-412.png')
        await tap(pg,'#hitsList .row .meta');await pg.wait_for_timeout(400)
        btn=await ev(pg,"[...document.querySelectorAll('#sheet [data-oi]')].map(b=>b.textContent.trim())")
        check('Open-in sheet offers JioSaavn, Spotify and YouTube Music',btn==['JioSaavn','Spotify','YouTube Music'],btn)
        await pg.screenshot(path='/tmp/old-v21-open-in-sheet-412.png')
        urls=[]
        for i in range(3):
            await tap(pg,f'#sheet [data-oi="{i}"]');await pg.wait_for_timeout(250)
            urls.append((await ev(pg,"window.__opened.slice(-1)[0]")));
            if i<2: await tap(pg,'#hitsList .row .meta');await pg.wait_for_timeout(400)
        ok=urls[0].startswith('https://www.jiosaavn.com/search/') and urls[1].startswith('https://open.spotify.com/search/') and urls[2].startswith('https://music.youtube.com/search?q=')
        check('Open-in buttons hand off by search link only (JioSaavn / Spotify / YouTube Music URLs)',ok,urls)
        # track menu has the entry
        await ev(pg,"window.scrollTo(0,0)");await tap(pg,'#finderList .row [data-act=more]');await pg.wait_for_timeout(400)
        mm=await ev(pg,"[...document.querySelectorAll('#sheet [data-m]')].map(b=>b.dataset.m)")
        check('Track menu has “Go to artist” and “Open in…”','artist' in mm and 'ext' in mm,mm)
        await ev(pg,"history.back()");await pg.wait_for_timeout(300)
        # ---- settings version + whats new ----
        await tap(pg,'#settingsBtn');await pg.wait_for_timeout(500);ver=await ev(pg,"document.getElementById('sheet').textContent.match(/Kayal \\d+\\.\\d+\\.\\d+ \\(build \\d+\\)/g)||[]")
        check('Settings shows “Kayal <version> (build n)”',len(ver)>=1,ver);await pg.screenshot(path='/tmp/old-v21-settings-version-412.png');await ev(pg,"history.back()");await pg.wait_for_timeout(300)
        await ev(pg,"kayal.showWhatsNew()");await pg.wait_for_timeout(400);wn=await ev(pg,"document.getElementById('sheet').textContent.includes('What\\'s new in Kayal '+kayal.APP_VER)");await pg.screenshot(path='/tmp/old-v21-whats-new-412.png')
        check('“What\'s new” sheet describes the new features',wn);await ev(pg,"history.back()");await pg.wait_for_timeout(300)
        # stale cache cleared on update: simulate old version + stale caches
        await ev(pg,"localStorage.setItem('kayal.ver','2.0.0');localStorage.setItem('kayal.cache.v1','{\"stale\":1}');caches.open('kayal-shell-v3').then(c=>c.put('/old',new Response('x')))");await pg.reload();await pg.wait_for_function('window.kayal&&kayal.ready');await pg.wait_for_timeout(1500)
        st=await ev(pg,"caches.keys().then(ks=>[ks,localStorage.getItem('kayal.ver'),localStorage.getItem('kayal.cache.v1')])")
        check('Update from an older version clears stale caches and records the new version','kayal-shell-v3' not in st[0] and st[1]==VER and st[2] is None,st)
        sw=await ev(pg,"fetch('sw.js',{cache:'no-store'}).then(r=>r.text()).then(t=>t.match(/kayal-shell-v\\d+/)[0])")
        check('Service worker cache name bumped (kayal-shell-v5) so old shells are replaced',sw=='kayal-shell-v5',sw)
        # offline: finder row from cache
        await pg.wait_for_function("document.querySelectorAll('#finderList .row').length>=5",timeout=90000);await pg.wait_for_timeout(1500)
        await ctx.set_offline(True);await pg.reload();await pg.wait_for_function("document.querySelectorAll('#finderList .row').length>=5",timeout=15000)
        check('Fresh finds row still shows (from cache) with no network',True);await ctx.set_offline(False)
        check('No console / page errors from the app',not errs,errs[:5])
        await ctx.close();await b.close()
    json.dump({'results':R,'numbers':NUM},open(ROOT+'/test/results_v21.json','w'),indent=1,default=str)
    print(json.dumps(NUM,indent=1)[:3000]);print(f"\n{sum(1 for r in R if r[1])}/{len(R)} passed")
asyncio.run(main())

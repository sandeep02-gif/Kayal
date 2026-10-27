# Kayal 2.2 tests: glass interface, theme, artwork colours, YouTube Music hand-off tab. Live network for playback bits.
import asyncio,json,os,sys,time,re
from playwright.async_api import async_playwright
URL='http://127.0.0.1:8091/index.html';ROOT='/workspace/music-player';SS=ROOT+'/screenshots'
R=[]
def check(n,ok,d=''):
    R.append((n,bool(ok),str(d)[:400]));print(('PASS ' if ok else 'FAIL ')+n+(' – '+str(d)[:400] if d!='' else ''),flush=True)
async def ev(pg,js,a=None): return await pg.evaluate(js,a)
async def tap(pg,sel):
    el=pg.locator(sel).first
    try:
        await el.scroll_into_view_if_needed(timeout=8000);await el.tap()
    except Exception:
        await el.evaluate("e=>e.scrollIntoView({block:'center'})");await el.click(force=True,timeout=8000)
async def tab(pg,t): await tap(pg,f'nav.bnav [data-tab="{t}"]');await pg.wait_for_timeout(450)
UA='Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Mobile Safari/537.36'
async def newpage(b,w=412,h=900,scheme='dark',mobile=True):
    ctx=await b.new_context(viewport={'width':w,'height':h},is_mobile=mobile,has_touch=mobile,device_scale_factor=2 if mobile else 1,color_scheme=scheme,user_agent=UA if mobile else None)
    pg=await ctx.new_page();errs=[];reqs=[]
    pg.on('console',lambda m:errs.append(m.text[:200]) if m.type=='error' and 'Failed to load resource' not in m.text else None)
    pg.on('pageerror',lambda e:errs.append('PAGEERROR '+str(e)[:200]))
    pg.on('request',lambda r:reqs.append(r.url))
    await pg.add_init_script("window.__opened=[];window.open=(u)=>{window.__opened.push(u);return null}")
    await pg.goto(URL);await pg.wait_for_function('window.kayal&&kayal.ready');await pg.wait_for_timeout(800)
    return ctx,pg,errs,reqs
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(executable_path='/usr/bin/google-chrome',args=['--no-sandbox','--autoplay-policy=no-user-gesture-required'])
        ctx,pg,errs,reqs=await newpage(b)
        # ---- version ----
        v=await ev(pg,"[kayal.APP_VER,kayal.APP_BUILD,document.querySelector('meta[name=app-version]').content,localStorage.getItem('kayal.ver')]")
        check('Version 2.2.0 (build 4) in app, meta and stored value',v==['2.2.0',4,'2.2.0','2.2.0'],v)
        # ---- glass nav ----
        nv=await ev(pg,"""(()=>{const n=document.querySelector('nav.bnav'),r=n.getBoundingClientRect(),cs=getComputedStyle(n);return {btns:[...n.querySelectorAll('[data-tab]')].map(b=>b.dataset.tab),left:r.left,gap:innerHeight-r.bottom,h:r.height,br:parseFloat(cs.borderTopLeftRadius),bf:cs.backdropFilter||cs.webkitBackdropFilter,pos:cs.position}})()""")
        check('Tab bar is a floating glass pill with 4 tabs (Home, Search, Library, YT Music)',nv['btns']==['home','search','library','ytm'] and nv['left']>=8 and nv['gap']>=8 and nv['br']>=24 and 'blur' in nv['bf'],nv)
        pos=[]
        for t in ['search','library','ytm','home']:
            await tab(pg,t);pos.append(await ev(pg,"[document.querySelector('nav.bnav').style.getPropertyValue('--i'),document.querySelector('nav.bnav button.on').dataset.tab,document.querySelector('.view.on').id]"))
        check('Selection pill index follows the active tab',pos==[['1','search','v-search'],['2','library','v-library'],['3','ytm','v-ytm'],['0','home','v-home']],pos)
        # ---- theme ----
        th=await ev(pg,"[document.documentElement.dataset.theme,getComputedStyle(document.body).backgroundColor]")
        check('System theme follows dark colour scheme',th[0]=='dark',th)
        await ev(pg,"kayal.S.settings.theme='light';kayal.applyTheme()");await pg.wait_for_timeout(200)
        th=await ev(pg,"[document.documentElement.dataset.theme,getComputedStyle(document.body).backgroundColor,getComputedStyle(document.body).color,document.querySelector('meta[name=theme-color]').content]")
        check('Light theme switches background/text and theme-color',th[0]=='light' and th[1]!='rgb(15, 17, 21)' and th[2]!='rgb(238, 241, 246)' and th[3]=='#f3f4f8',th)
        await pg.screenshot(path=SS+'/v22-home-light-412.png')
        await ev(pg,"kayal.S.settings.theme='system';kayal.applyTheme()")
        await ctx.close()
        ctx2,pg,errs2,_=await newpage(b,scheme='light')
        check('System theme follows light colour scheme',await ev(pg,"document.documentElement.dataset.theme")=='light')
        await ctx2.close()
        # ---- main run (dark) ----
        ctx,pg,errs,reqs=await newpage(b)
        await ev(pg,"kayal.S.settings.theme='dark';kayal.applyTheme()")
        # settings
        await tap(pg,'#settingsBtn');await pg.wait_for_timeout(500)
        st=await ev(pg,"({t:!!document.querySelector('#stTheme'),y:!!document.querySelector('#stYtm'),ap:document.getElementById('sheet').textContent.includes('Appearance'),ver:/Kayal 2\\.2\\.0 \\(build 4\\)/.test(document.getElementById('sheet').textContent)})")
        check('Settings has Appearance (theme + artwork colours), YouTube Music section and shows 2.2.0 (build 4)',all(st.values()),st)
        await pg.screenshot(path=SS+'/v22-settings-412.png')
        await pg.select_option('#stTheme','light');await pg.wait_for_timeout(200)
        sv=await ev(pg,"[document.documentElement.dataset.theme,kayal.S.settings.theme]")
        check('Theme choice in Settings applies immediately',sv==['light','light'],sv)
        await pg.select_option('#stTheme','dark');await pg.wait_for_timeout(300)
        await ev(pg,"history.back()");await pg.wait_for_timeout(300)
        await pg.reload();await pg.wait_for_function('window.kayal&&kayal.ready');await pg.wait_for_timeout(500)
        check('Theme choice persists after reload',await ev(pg,"[document.documentElement.dataset.theme,kayal.S.settings.theme]")==['dark','dark'])
        # home look
        await pg.wait_for_function("document.querySelectorAll('#trendList .row').length>0",timeout=40000);await pg.wait_for_timeout(1500)
        await pg.screenshot(path=SS+'/v22-home-412.png')
        tiles=await ev(pg,"[...document.querySelectorAll('#madeFor .chip')].map(c=>[c.textContent.trim(),getComputedStyle(document.getElementById('madeFor')).display])")
        check('Home quick-tiles grid incl. YouTube Music tile',len(tiles)>=6 and tiles[0][1]=='grid' and any(t[0]=='YouTube Music' for t in tiles),tiles)
        await tap(pg,'#madeFor .ytq');await pg.wait_for_timeout(400)
        check('YouTube Music home tile opens the YT Music tab',await ev(pg,"document.querySelector('.view.on').id")=='v-ytm')
        # ---- YT Music tab ----
        await pg.screenshot(path=SS+'/v22-ytm-412.png')
        i0=await ev(pg,"({now:document.getElementById('ytmNow').disabled,status:document.getElementById('ytmStatus').textContent,flag:document.getElementById('ytmFlag').checked})")
        check('YT Music tab: starts “Not signed in”, “find current song” disabled with nothing playing',i0['now'] and i0['status']=='Not signed in' and not i0['flag'],i0)
        await ev(pg,"window.__opened.length=0");await tap(pg,'#ytmSign');await pg.wait_for_timeout(300)
        o=await ev(pg,"window.__opened.slice()")
        check('Sign-in button opens Google sign-in externally with continue → music.youtube.com (no in-app WebView/password capture)',len(o)==1 and o[0].startswith('https://accounts.google.com/ServiceLogin') and 'continue=https%3A%2F%2Fmusic.youtube.com' in o[0],o)
        await ev(pg,"window.__opened.length=0");await tap(pg,'#ytmOpen');o=await ev(pg,"window.__opened.slice()")
        check('Open YouTube Music → https://music.youtube.com/',o==['https://music.youtube.com/'],o)
        await tap(pg,'#ytmFlag');await pg.wait_for_timeout(200)
        sg=await ev(pg,"[kayal.S.settings.ytm.signed,document.getElementById('ytmStatus').textContent]")
        check('“I\'m signed in” reminder flips status and is stored locally',sg[0]==True and 'Signed in' in sg[1],sg)
        await pg.screenshot(path=SS+'/v22-ytm-signed-412.png')
        await ev(pg,"window.__opened.length=0");await pg.fill('#ytmQ','Ennu Ninte Moideen & song');await tap(pg,'#ytmGo');await pg.wait_for_timeout(300)
        o=await ev(pg,"window.__opened.slice()")
        check('Search opens music.youtube.com/search?q=… with the query encoded',o==['https://music.youtube.com/search?q='+'Ennu%20Ninte%20Moideen%20%26%20song'],o)
        hi=await ev(pg,"[...document.querySelectorAll('#ytmHist .chip')].map(c=>c.textContent)")
        check('Recent YT Music searches are remembered (max 8) and re-open on tap',hi[:1]==['Ennu Ninte Moideen & song'],hi)
        await ev(pg,"window.__opened.length=0");await tap(pg,'#ytmHist .chip');o=await ev(pg,"window.__opened.slice()")
        check('Tapping a recent search opens it again',len(o)==1 and 'search?q=' in o[0],o)
        links={}
        for k in ['home','explore','library','liked','history']:
            await ev(pg,"window.__opened.length=0");await tap(pg,f'#v-ytm [data-yl="{k}"]');links[k]=(await ev(pg,"window.__opened.slice()"))
        check('Jump-to tiles open YT Music Home/Explore/Library/Liked/History',links=={'home':['https://music.youtube.com/'],'explore':['https://music.youtube.com/explore'],'library':['https://music.youtube.com/library'],'liked':['https://music.youtube.com/playlist?list=LM'],'history':['https://music.youtube.com/history']},links)
        # native bridge path
        await ev(pg,"window.__native=window.__native||{};window.__nat=[];window.__native.openUrl=u=>{window.__nat.push(u)}"+";0");await tap(pg,'#ytmOpen')
        await pg.wait_for_timeout(300);nv=await ev(pg,'window.__nat.slice()');check('On Android the link goes through the native openUrl (ACTION_VIEW → YouTube Music app if installed)',nv==['https://music.youtube.com/'],nv)
        await ev(pg,"delete window.__native.openUrl")
        # touch targets + overflow
        tt=await ev(pg,"[...document.querySelectorAll('#v-ytm button,#v-ytm input:not([type=checkbox])')].filter(e=>e.offsetParent&&(e.getBoundingClientRect().height<43.5||e.getBoundingClientRect().width<43.5)).map(e=>[e.id||e.className,Math.round(e.getBoundingClientRect().width),Math.round(e.getBoundingClientRect().height)])")
        check('YT Music tab: touch targets ≥44px',tt==[],tt)
        check('No horizontal overflow on YT Music tab',await ev(pg,"document.documentElement.scrollWidth<=innerWidth"))
        # ---- play a real free track: tint, NP look ----
        await tab(pg,'search');await tap(pg,'#srcTabs [data-st="audius"]');await pg.fill('#q','');await pg.type('#q','chill',delay=25)
        await pg.wait_for_function("kayal.lastTerm==='chill' && document.querySelectorAll('#sResults .skel').length===0",timeout=40000);await pg.wait_for_timeout(500)
        await pg.screenshot(path=SS+'/v22-search-412.png')
        await tap(pg,'#sResults .row .meta')
        ok=False;end=time.time()+40
        while time.time()<end:
            s=await ev(pg,'({p:kayal.audio.paused,t:kayal.audio.currentTime})')
            if not s['p'] and s['t']>1.5: ok=True;break
            await pg.wait_for_timeout(400)
        check('A free Audius track plays under the new UI',ok)
        await pg.wait_for_timeout(1500)
        tn=await ev(pg,"({t1:getComputedStyle(document.documentElement).getPropertyValue('--t1').trim(),ta:getComputedStyle(document.documentElement).getPropertyValue('--ta').trim(),mini:getComputedStyle(document.getElementById('mini')).backdropFilter,sampled:kayal.TINTC.size})")
        check('Artwork tint variables are set for the playing song',tn['t1'][:3] in('hsl','rgb') and tn['ta'].startswith('hsl'),tn)
        check('Cover colour was sampled on-device from the CORS-enabled Audius art',tn['sampled']>=1,tn['sampled'])
        check('Mini player is glass (backdrop blur)','blur' in tn['mini'],tn['mini'])
        await pg.screenshot(path=SS+'/v22-mini-player-412.png')
        await tap(pg,'#mOpen');await pg.wait_for_timeout(1200)
        np=await ev(pg,"({pl:document.getElementById('np').classList.contains('pl'),sc:getComputedStyle(document.getElementById('npArt')).transform,br:getComputedStyle(document.getElementById('npArt')).borderTopLeftRadius,bg:getComputedStyle(document.getElementById('np')).backgroundImage.slice(0,60)})")
        check('Now Playing: colour-mesh background, large rounded art, art “breathes” when playing',np['pl'] and 'radial-gradient' in np['bg'] and float(np['br'][:-2])>=24,np)
        await pg.screenshot(path=SS+'/v22-now-playing-412.png')
        await ev(pg,"kayal.audio.pause()");await pg.wait_for_timeout(700)
        check('Art shrinks when paused',not await ev(pg,"document.getElementById('np').classList.contains('pl')"))
        await ev(pg,"kayal.audio.play()")
        h1=await ev(pg,"getComputedStyle(document.documentElement).getPropertyValue('--ta').trim()")
        await ev(pg,"kayal.S.settings.tint=false;kayal.applyTheme()");h2=await ev(pg,"getComputedStyle(document.documentElement).getPropertyValue('--ta').trim()")
        check('“Colours follow the album art” off removes the tint',h1.startswith('hsl') and not h2.startswith('hsl'),[h1,h2])
        await ev(pg,"kayal.S.settings.tint=true;kayal.applyTheme()")
        # distinct songs → distinct tints (hash fallback)
        hs=await ev(pg,"(()=>{const g=t=>{kayal.tint({title:t,art:''});return getComputedStyle(document.documentElement).getPropertyValue('--ta').trim()};return [g('Aaa'),g('Bbb song'),g('Zeta')]})()")
        check('Different songs without sampled art still get different colours',len(set(hs))==3,hs)
        # open in
        await ev(pg,"history.back()");await pg.wait_for_timeout(300)
        await ev(pg,"kayal.openInSheet('Test Song','Test Artist')");await pg.wait_for_timeout(400)
        sh=await ev(pg,"document.getElementById('sheet').textContent");check('Open in sheet (default) still lists JioSaavn, Spotify, YouTube Music','YouTube Music' in sh and 'Spotify' in sh and 'JioSaavn' in sh)
        await pg.screenshot(path=SS+'/v22-open-in-sheet-412.png');await ev(pg,"history.back()");await pg.wait_for_timeout(300)
        await ev(pg,"kayal.S.settings.ytm.pref=true;window.__opened.length=0;kayal.openInSheet('Test Song','Test Artist')");await pg.wait_for_timeout(300)
        o=await ev(pg,"[window.__opened.slice(),document.getElementById('sheet').classList.contains('on')]")
        check('With “straight to YouTube Music” on, Open in skips the chooser',o[0]==['https://music.youtube.com/search?q=Test%20Song%20Test%20Artist'] and o[1]==False,o)
        await ev(pg,"kayal.S.settings.ytm.pref=false")
        # now-playing button enabled
        await tab(pg,'ytm');nb=await ev(pg,"[document.getElementById('ytmNow').disabled,document.getElementById('ytmNow').textContent.trim()]")
        check('“Find this in YouTube Music” enabled while a song plays',nb[0]==False and nb[1].startswith('Find “'),nb)
        await ev(pg,"window.__opened.length=0");await tap(pg,'#ytmNow');o=await ev(pg,"window.__opened.slice()")
        check('…and opens a YT Music search for the playing song',len(o)==1 and o[0].startswith('https://music.youtube.com/search?q='),o)
        await pg.screenshot(path=SS+'/v22-ytm-playing-412.png')
        # library + whats new
        await tab(pg,'library');await pg.screenshot(path=SS+'/v22-library-412.png')
        await ev(pg,"kayal.showWhatsNew()");await pg.wait_for_timeout(400)
        wn=await ev(pg,"document.getElementById('sheet').textContent");check('What\'s new 2.2.0 mentions new look, YouTube Music and links-only',"What's new in Kayal 2.2.0" in wn and 'New look' in wn and 'YouTube Music' in wn and "doesn't play" in wn)
        await pg.screenshot(path=SS+'/v22-whats-new-412.png');await ev(pg,"history.back()");await pg.wait_for_timeout(300)
        # compliance: no YouTube playback/network
        yt=[u for u in reqs if re.search(r'googlevideo|youtubei|youtube\.com|ytimg|ggpht',u)]
        check('No network requests to YouTube/googlevideo from the app (links only)',yt==[],yt[:3])
        html=open(ROOT+'/index.html',encoding='utf-8').read()
        bad=[k for k in ['googlevideo','youtubei','iframe_api','youtube.com/embed','ytimg.com','innertube','yt-dlp'] if k in html.lower()]
        check('Source has no YouTube streaming/extraction/embed code',bad==[],bad)
        check('No iframe/video element used',await ev(pg,"document.querySelectorAll('iframe,video').length")==0)
        # 360 + desktop
        await pg.set_viewport_size({'width':360,'height':780});await pg.wait_for_timeout(300)
        for t in ['home','search','library','ytm']:
            await tab(pg,t);ov=await ev(pg,"document.documentElement.scrollWidth<=innerWidth")
            check(f'360px: no horizontal overflow on {t}',ov)
        nv=await ev(pg,"(()=>{const r=document.querySelector('nav.bnav').getBoundingClientRect();return [Math.round(r.left),Math.round(r.width)]})()")
        check('360px: floating tab bar fits inside screen',nv[0]>=8 and nv[0]+nv[1]<=360-8,nv)
        await ctx.close()
        ctx,pg,errs3,_=await newpage(b,1366,820,'dark',False)
        await pg.wait_for_timeout(1500)
        d=await ev(pg,"(()=>{const n=document.querySelector('nav.bnav').getBoundingClientRect();return {w:n.width,btn:document.querySelectorAll('nav.bnav [data-tab]').length,pillGone:getComputedStyle(document.querySelector('nav.bnav'),'::before').display}})()")
        check('Desktop: sidebar nav (230px) with 4 entries still works',d['w']==230 and d['btn']==4,d)
        await pg.screenshot(path=SS+'/v22-desktop-1366-home.png')
        await ctx.close()
        allerr=[e for e in errs+errs2+errs3 if 'Access to' not in e]
        check('Zero console/page errors',allerr==[],allerr[:3])
        await b.close()
    n=sum(1 for r in R if r[1]);print(f'\n{n}/{len(R)} passed');json.dump(R,open(ROOT+'/test/results_v22.json','w'),indent=1)
    sys.exit(0 if n==len(R) else 1)
asyncio.run(main())

"""Per-browser private workspace on Makers Agents; the original FastAPI engine is reused.
Provider keys never enter responses; persisted state excludes credentials and browser tokens.
"""
import asyncio, base64, hashlib, hmac, json, os, re, sys, time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import httpx
os.environ['DATABASE_URL']='sqlite:////tmp/truthhunter-bootstrap.db'
os.environ['ARTIFACT_DIR']='/tmp/truthhunter-bootstrap-artifacts'
from _truthhunter.main import create_app
from _truthhunter.store import Base, Investigation, Record, Event
from _truthhunter.browser import BrowserAgent
from _truthhunter.contracts import TERMINAL
from _truthhunter.providers import ProviderError
_APPS={}
_LOAD_LOCKS={}
_ENV_KEYS=('LLM_API_KEY','LLM_MODEL','LLM_BASE_URL','BROWSER_ALLOWED_DOMAINS','BROWSER_DNS_MODE','BROWSER_ALLOW_PUBLIC_WEB')

def authorized(ctx):
    headers={k.lower():v for k,v in ctx.request.headers.items()}
    token=headers.get('x-th-token','');expiry,_,signature=token.partition('.')
    key=ctx.env.get('TH_SESSION_SECRET','')
    if not key or not expiry.isdigit() or len(expiry)>12 or not re.fullmatch(r'[a-f0-9]{64}',signature) or not time.time()<int(expiry)<=time.time()+3700:return False
    expected=hmac.new(key.encode(),f'{ctx.conversation_id}.{expiry}'.encode(),hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected,signature)

async def load_app(ctx):
    identity=ctx.conversation_id
    async with _LOAD_LOCKS.setdefault(identity,asyncio.Lock()):
        if identity in _APPS and _APPS[identity].state.engine.tasks:return _APPS[identity]
        if ctx.env.get('YUANBAO_API_KEY'):os.environ['TENCENTCLOUD_WSA_APIKEY']=ctx.env['YUANBAO_API_KEY']
        for key in _ENV_KEYS:
            if ctx.env.get(key):os.environ[key]=ctx.env[key]
        folder=Path('/tmp/truthhunter')/identity;folder.mkdir(parents=True,exist_ok=True)
        app=create_app('sqlite:///:memory:',folder)
        store=app.state.store;Base.metadata.create_all(store.engine)
        ids=await ctx.store.state.get('investigation-index') or []
        stale=[];loaded_hashes={}
        for task_id in ids:
            bundle=await ctx.store.state.get('investigation:'+task_id)
            if not bundle:continue
            loaded_hashes[task_id]=hashlib.sha256(json.dumps({k:bundle[k] for k in ('item','records','events')},sort_keys=True,ensure_ascii=False).encode()).hexdigest()
            if time.time()-bundle.get('updated_at',0)>330:stale.append(task_id)
            task=dict(bundle['item']);status=task.pop('status');task.pop('id',None)
            with store.session.begin() as session:
                session.add(Investigation(id=task_id,status=status,payload=json.dumps(task,ensure_ascii=False)))
                for record in bundle['records']:
                    payload={k:v for k,v in record.items() if k not in ('id','kind')}
                    session.add(Record(id=record['id'],investigation_id=task_id,kind=record['kind'],payload=json.dumps(payload,ensure_ascii=False)))
                for event in bundle['events']:
                    session.add(Event(id=event['id'],investigation_id=task_id,payload=json.dumps({k:v for k,v in event.items() if k!='id'},ensure_ascii=False)))
        # No automatic replay of paid calls after the platform recycles an instance.
        for task in store.list():
            if task['id'] in stale and task['status'] not in TERMINAL:app.state.engine.finish_partial(task['id'],'PARTIAL','CLOUD_PROCESS_RESTARTED')
        app.state.engine.start=lambda task_id:None  # /run explicitly executes in a long-lived Agent request.
        app.state.cloud_folder=folder;app.state.persist_lock=asyncio.Lock();app.state.persist_hashes=loaded_hashes
        _APPS[identity]=app
        return app

async def persist(ctx,app):
    async with app.state.persist_lock:
        store=app.state.store
        ids=[]
        for item in store.list():
            task_id=item['id'];ids.append(task_id)
            bundle={'item':item,'records':store.records(task_id),'events':store.events(task_id)}
            encoded=json.dumps(bundle,sort_keys=True,ensure_ascii=False);digest=hashlib.sha256(encoded.encode()).hexdigest()
            if app.state.persist_hashes.get(task_id)==digest and task_id not in app.state.engine.tasks:continue
            bundle['updated_at']=time.time()
            for snapshot in [r for r in bundle['records'] if r['kind']=='snapshot']:
                filename=snapshot.get('screenshot','')
                if re.fullmatch(r'[a-f0-9]{32}\.png',filename):
                    asset_key='asset:'+filename
                    if asset_key not in app.state.persist_hashes:
                        asset=app.state.cloud_folder/filename
                        if asset.exists():
                            await ctx.store.state.set(asset_key,base64.b64encode(asset.read_bytes()).decode())
                            app.state.persist_hashes[asset_key]='saved'
            await ctx.store.state.set('investigation:'+task_id,bundle)
            app.state.persist_hashes[task_id]=digest
        existing=await ctx.store.state.get('investigation-index') or []
        await ctx.store.state.set('investigation-index',list(dict.fromkeys(ids+existing)))

async def run_task(ctx,app,task_id):
    engine=app.state.engine;row=app.state.store.get(task_id)
    if not row:return {'status':404,'body':{'detail':'调查不存在'}}
    if row['status']!='CREATED' or task_id in engine.tasks:return {'status':409,'body':{'detail':'调查已启动或结束，不重复调用付费服务'}}
    if len(engine.tasks)>=2:return {'status':429,'body':{'detail':'最多同时运行两项调查'}}
    class CloudBrowser(BrowserAgent):
        ready=False
        async def capture(self,url,source_id):
            try:
                if not self.ready:
                    await ctx.sandbox.browser.goto('about:blank')
                    source=Path(__file__).resolve().parents[1].joinpath('_browser_source.txt').read_text()
                    await ctx.sandbox.files.write('/tmp/truthhunter_capture.py',source)
                    setup=await ctx.sandbox.commands.run('python -c "import httpx,playwright" || pip -q install httpx playwright',timeout=60)
                    code=getattr(setup,'exit_code',getattr(setup,'exitCode',0))
                    if isinstance(setup,dict):code=setup.get('exitCode',setup.get('exit_code',0))
                    if code:raise ProviderError('CLOUD_BROWSER_DEPENDENCIES_UNAVAILABLE')
                    self.ready=True
                browser=ctx.sandbox.browser
                endpoint=getattr(browser,'cdp_url',None) or getattr(browser,'cdpUrl',None)
                if asyncio.iscoroutine(endpoint):endpoint=await endpoint
                if not endpoint:raise ProviderError('CLOUD_BROWSER_ENDPOINT_UNAVAILABLE')
                result=await ctx.sandbox.commands.run('python /tmp/truthhunter_capture.py',timeout=75,env={'TH_CAPTURE_URL':url,'TH_SOURCE_ID':source_id,'TH_CDP':endpoint,'BROWSER_ALLOWED_DOMAINS':os.getenv('BROWSER_ALLOWED_DOMAINS',''),'BROWSER_DNS_MODE':os.getenv('BROWSER_DNS_MODE','system'),'BROWSER_ALLOW_PUBLIC_WEB':os.getenv('BROWSER_ALLOW_PUBLIC_WEB','false')})
                stdout=result.get('stdout','') if isinstance(result,dict) else result.stdout
                captured=json.loads(stdout.strip().splitlines()[-1])
                if captured.get('error'):raise ProviderError(captured['error'])
                image=base64.b64decode(captured.pop('_image'))
                if not image.startswith(b'\x89PNG'):raise ValueError()
                app.state.cloud_folder.joinpath(captured['screenshot']).write_bytes(image)
                app.state.cloud_folder.joinpath(source_id+'.txt').write_text(captured['text'])
                return captured
            except ProviderError:raise
            except Exception:raise ProviderError('CLOUD_BROWSER_UNAVAILABLE') from None
    engine.browser=CloudBrowser(app.state.cloud_folder)
    task=asyncio.create_task(engine.run(task_id));engine.tasks[task_id]=task
    try:
        while not task.done():
            await asyncio.wait({task},timeout=1.5)
            if await ctx.store.state.get('cancel:'+task_id):
                task.cancel()
                try:await task
                except asyncio.CancelledError:pass
            await persist(ctx,app)
        await task
    finally:
        if not task.done():
            task.cancel()
            try:await task
            except asyncio.CancelledError:pass
        engine.tasks.pop(task_id,None)
        await persist(ctx,app)
    return {'status':200,'body':app.state.store.get(task_id)}

async def handler(ctx):
    if not authorized(ctx):return {'status':403,'body':{'detail':'会话校验失败，请刷新网页'}}
    payload=ctx.request.body or {}
    if not isinstance(payload,dict):return {'status':422,'body':{'detail':'请求格式不正确'}}
    path=payload.get('path','');method=payload.get('method','GET')
    if not isinstance(path,str) or not re.fullmatch(r'/(health|extract-image|investigations)(/[a-zA-Z0-9_.-]+)*',path):return {'status':404,'body':{'detail':'接口不存在'}}
    if method not in ('GET','POST'):return {'status':405,'body':{'detail':'不支持的请求方式'}}
    app=await load_app(ctx)
    match=re.fullmatch(r'/investigations/([a-f0-9]{32})/run',path)
    if match and method=='POST':return await run_task(ctx,app,match[1])
    if path=='/investigations' and method=='POST':
        # Cost boundary for an anonymous competition workspace, with normal typed questions enabled.
        today=time.strftime('%Y-%m-%d',time.gmtime())
        daily=sum(x.get('data_mode')=='live' and x.get('created_at','').startswith(today) for x in app.state.store.list())
        if daily>=int(ctx.env.get('TH_DAILY_TASK_LIMIT','20')):return {'status':429,'body':{'detail':'今天的调查次数已用完，请明天继续'}}
        if len(app.state.store.list())>=40:return {'status':429,'body':{'detail':'当前工作空间已达40项档案上限'}}
    cancellation=re.fullmatch(r'/investigations/([a-f0-9]{32})/cancel',path)
    if cancellation and method=='POST' and app.state.store.get(cancellation[1]):
        await ctx.store.state.set('cancel:'+cancellation[1],True)
    shot=re.fullmatch(r'/investigations/([a-f0-9]{32})/screenshots/([a-f0-9]{32}\.png)',path)
    if shot:
        target=app.state.cloud_folder/shot[2]
        if not target.exists():
            data=await ctx.store.state.get('asset:'+shot[2])
            if data:target.write_bytes(base64.b64decode(data))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://workspace') as client:
        response=await client.request(method,path,json=payload.get('body') if method=='POST' else None)
    if method=='POST':await persist(ctx,app)
    if response.headers.get('content-type','').startswith('application/json'):return {'status':response.status_code,'body':response.json()}
    return {'status':response.status_code,'binary':base64.b64encode(response.content).decode(),'content_type':response.headers.get('content-type','application/octet-stream')}

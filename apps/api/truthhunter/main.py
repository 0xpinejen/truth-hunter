import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, Response, FileResponse
from .contracts import CreateInvestigation, TERMINAL
from .store import Store, now
from .engine import Engine

def create_app(database_url=None, artifact_dir=None):
    store=Store(database_url or os.getenv('DATABASE_URL','sqlite:///./data/truthhunter.db'))
    artifacts=Path(artifact_dir or os.getenv('ARTIFACT_DIR','./artifacts'))
    engine=Engine(store,artifacts)

    @asynccontextmanager
    async def lifespan(app):
        # No automatic replay of potentially paid API calls on restart.
        for row in store.list():
            if row['status'] not in TERMINAL: engine.finish_partial(row['id'],'PARTIAL','PROCESS_RESTARTED')
        yield
        for id in list(engine.tasks): await engine.cancel(id)

    app=FastAPI(title='TruthHunter 2.0',version='0.1.0',lifespan=lifespan)
    app.state.store=store
    app.state.engine=engine
    app.add_middleware(CORSMiddleware,allow_origins=['http://127.0.0.1:3000','http://localhost:3000'],allow_methods=['GET','POST'],allow_headers=['Content-Type','Last-Event-ID'])

    def require(id):
        row=store.get(id)
        if not row: raise HTTPException(404,'Investigation not found')
        return row

    @app.get('/health')
    async def health():
        return {'status':'ok','configured':{'yuanbao':bool(os.getenv('TENCENTCLOUD_WSA_APIKEY')),'llm':bool(os.getenv('LLM_API_KEY') and os.getenv('LLM_MODEL'))},'connectivity':'not_verified','verification':'provenance_review_pending'}

    @app.get('/investigations')
    async def listing(): return store.list()

    @app.post('/investigations',status_code=201)
    async def create(body:CreateInvestigation):
        if len(engine.tasks)>=2: raise HTTPException(429,'最多同时运行两项调查')
        if body.data_mode=='fixture' and body.message!='演示服务是否永久无限免费？':
            raise HTTPException(422,'演示模式只接受预定义虚构案例')
        id=uuid4().hex
        store.create(id,dict(body.model_dump(),created_at=now()))
        store.emit(id,'CREATED','演示调查已创建' if body.data_mode=='fixture' else '调查已创建')
        engine.start(id)
        return require(id)

    @app.get('/investigations/{id}')
    async def detail(id:str):
        return dict(require(id),records=store.records(id),events=store.events(id))

    @app.post('/investigations/{id}/cancel')
    async def cancel(id:str):
        require(id); await engine.cancel(id); return require(id)

    @app.get('/investigations/{id}/events')
    async def events(id:str,request:Request,after:int=0):
        require(id)
        try: cursor=max(after,int(request.headers.get('last-event-id','0')))
        except ValueError: raise HTTPException(400,'Invalid event cursor')
        async def stream():
            nonlocal cursor
            heartbeat=0
            while not await request.is_disconnected():
                for event in store.events(id,cursor):
                    cursor=event['id']
                    yield f'id: {cursor}\nevent: investigation\ndata: {json.dumps(event,ensure_ascii=False)}\n\n'
                if require(id)['status'] in TERMINAL: break
                heartbeat+=1
                if heartbeat%30==0: yield ': heartbeat\n\n'
                await asyncio.sleep(.25)
        return StreamingResponse(stream(),media_type='text/event-stream',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})

    @app.get('/investigations/{id}/report.md')
    async def markdown(id:str):
        row=require(id)
        reports=store.records(id,'report')
        if not reports: raise HTTPException(409,'报告尚未生成')
        r=reports[0]
        # Plain-text Markdown export; do not render upstream HTML.
        def plain(value): return str(value).replace('<','&lt;').replace('>','&gt;').replace('[','\\[').replace(']','\\]')
        lines=['# TruthHunter 调查报告','',plain(row['message']),'',f"数据模式：{row['data_mode']} · 执行状态：{row['status']}",'']
        for a in r['assessments']:
            lines+=['## '+a['claim_id'],'结论：'+a['verdict'],plain(a.get('rationale','')),'引用：'+', '.join(a['evidence_ids']),'']
        lines+=['## 原文证据','']
        for e in r['evidence']:
            lines += [f"### {e['id']}",plain(e['quote']), '来源：'+plain(e['url']),'SHA-256：'+e['sha256'],'']
        lines+=['## 调查局限','']+['- '+plain(x) for x in r['limitations']]
        return Response('\n'.join(lines),media_type='text/markdown',headers={'Content-Disposition':f'attachment; filename="truthhunter-{id}.md"'})

    @app.get('/investigations/{id}/screenshots/{filename}')
    async def screenshot(id:str,filename:str):
        require(id)
        allowed={r['screenshot'] for r in store.records(id,'snapshot')}
        if filename not in allowed or Path(filename).name!=filename: raise HTTPException(404)
        path=artifacts/filename
        if not path.is_file(): raise HTTPException(404)
        return FileResponse(path,media_type='image/png')

    return app

app=create_app()

import asyncio, hashlib, hmac, importlib.util, json, sys, time, tempfile, shutil
from pathlib import Path
from types import SimpleNamespace
import pytest
ROOT=Path(__file__).resolve().parents[3]
_modules=tempfile.TemporaryDirectory(prefix='truthhunter-test-')
shutil.copytree(ROOT/'apps/api/truthhunter',Path(_modules.name)/'_truthhunter')
sys.path.insert(0,_modules.name)
# Bind the source-under-test package before the runtime adds its generated bundle path.
importlib.import_module('_truthhunter')
spec=importlib.util.spec_from_file_location('edgeone_rpc',ROOT/'agents/truthhunter/rpc.py')
rpc=importlib.util.module_from_spec(spec);spec.loader.exec_module(rpc)
class State:
    def __init__(self):self.values={}
    async def get(self,key):return json.loads(json.dumps(self.values.get(key)))
    async def set(self,key,value):self.values[key]=json.loads(json.dumps(value))
def context(identity,state=None):
    expiry=str(int(time.time())+300);secret='test-secret-with-no-provider-access'
    signature=hmac.new(secret.encode(),f'{identity}.{expiry}'.encode(),hashlib.sha256).hexdigest()
    return SimpleNamespace(conversation_id=identity,env={'TH_SESSION_SECRET':secret},request=SimpleNamespace(headers={'x-th-token':expiry+'.'+signature},body={}),store=SimpleNamespace(state=state or State()))
async def call(ctx,path,body=None):
    ctx.request.body={'path':path,'method':'POST' if body is not None else 'GET','body':body}
    return await rpc.handler(ctx)
def test_forged_and_expired_tokens_are_rejected():
    ctx=context('a'*32);assert rpc.authorized(ctx)
    ctx.request.headers['x-th-token']='0.'+'0'*64;assert not rpc.authorized(ctx)
    assert asyncio.run(call(ctx,'/health'))['status']==403
@pytest.mark.asyncio
async def test_cloud_fixture_survives_instance_recycle_and_isolated_workspace():
    ctx=context('b'*32)
    created=await call(ctx,'/investigations',{'message':'演示服务是否永久无限免费？','data_mode':'fixture','mode':'quick','workflow':'investigation'})
    assert created['status']==201;task_id=created['body']['id']
    assert (await call(ctx,f'/investigations/{task_id}/run',{}))['status']==200
    completed=(await call(ctx,f'/investigations/{task_id}'))['body']
    assert completed['status']=='COMPLETED'
    assert completed['records'][-1]['assessments'][0]['verdict']=='INSUFFICIENT'
    del rpc._APPS[ctx.conversation_id]
    restored=(await call(ctx,f'/investigations/{task_id}'))['body']
    assert restored['records']==completed['records'] and restored['events']==completed['events']
    stranger=context('c'*32)
    assert (await call(stranger,f'/investigations/{task_id}'))['status']==404
    assert (await call(ctx,f'/investigations/{task_id}/run',{}))['status']==409
    assert 'test-secret' not in json.dumps(ctx.store.state.values)
@pytest.mark.asyncio
async def test_recycled_pending_task_is_not_replayed():
    ctx=context('d'*32)
    created=(await call(ctx,'/investigations',{'message':'Python release date claim','data_mode':'live','mode':'quick','workflow':'investigation'}))['body']
    ctx.store.state.values['investigation:'+created['id']]['updated_at']=time.time()-400
    del rpc._APPS[ctx.conversation_id]
    restored=(await call(ctx,'/investigations/'+created['id']))['body']
    assert restored['status']=='PARTIAL'
    assert any('CLOUD_PROCESS_RESTARTED' in e['message'] for e in restored['events'])
    assert (await call(ctx,f"/investigations/{created['id']}/run",{}))['status']==409

@pytest.mark.asyncio
async def test_fresh_remote_progress_is_reloaded_without_marking_process_restarted():
    ctx=context('e'*32)
    created=(await call(ctx,'/investigations',{'message':'Python release date claim','data_mode':'live','mode':'quick','workflow':'investigation'}))['body']
    key='investigation:'+created['id']
    ctx.store.state.values[key]['item']['status']='SEARCHING'
    fresh=(await call(ctx,'/investigations/'+created['id']))['body']
    assert fresh['status']=='SEARCHING'
    ctx.store.state.values[key]['item']['status']='BROWSING'
    fresh=(await call(ctx,'/investigations/'+created['id']))['body']
    assert fresh['status']=='BROWSING'
    assert not any('CLOUD_PROCESS_RESTARTED' in e['message'] for e in fresh['events'])

@pytest.mark.asyncio
async def test_archive_order_survives_multiple_instance_reloads():
    ctx=context('f'*32)
    one=(await call(ctx,'/investigations',{'message':'older test claim','data_mode':'live','mode':'quick'}))['body']
    await asyncio.sleep(.002)
    two=(await call(ctx,'/investigations',{'message':'newer test claim','data_mode':'live','mode':'quick'}))['body']
    for _ in range(3):
        items=(await call(ctx,'/investigations'))['body']
        assert [x['id'] for x in items]==[two['id'],one['id']]

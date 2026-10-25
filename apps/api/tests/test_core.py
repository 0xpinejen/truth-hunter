import asyncio
import json
import time
from pathlib import Path
import httpx
import pytest
from fastapi.testclient import TestClient
from truthhunter.contracts import Assessment, Plan
from truthhunter.store import Base, Store
from truthhunter.providers import TencentYuanbaoSearchProvider, ProviderError
from truthhunter.engine import Engine, guard_assessment, validate_quote, canonical_url
from truthhunter.browser import validate_public_url
from truthhunter.main import create_app

@pytest.fixture
def store(tmp_path):
    s=Store('sqlite:///'+str(tmp_path/'test.db'))
    Base.metadata.create_all(s.engine)
    return s

def create(s,id='case',data_mode='live'):
    s.create(id,{'message':'演示服务是否永久无限免费？' if data_mode=='fixture' else '待核查的具体消息','mode':'quick','data_mode':data_mode,'created_at':'2026-10-23T00:00:00+00:00'})

@pytest.mark.asyncio
async def test_yuanbao_contract():
    seen=[]
    def transport(req):
        seen.append(req)
        return httpx.Response(200,json={'Response':{'RequestId':'test-only-id','Pages':[json.dumps({'url':'https://example.com/','title':'test','passage':'snippet'})]}})
    r=await TencentYuanbaoSearchProvider('test-only-key',httpx.MockTransport(transport)).search('测试查询')
    assert r['pages'][0]['title']=='test'
    assert seen[0].url==TencentYuanbaoSearchProvider.endpoint
    assert json.loads(seen[0].content)=={'Query':'测试查询'}
    assert seen[0].headers['authorization']=='Bearer test-only-key'

@pytest.mark.asyncio
@pytest.mark.parametrize('response,code',[
    (httpx.Response(429,json={}), 'WSA_HTTP_429'),
    (httpx.Response(200,json={'Response':{'Error':{'Code':'UnauthorizedOperation','Message':'secret should never be logged'}}}), 'WSA_UPSTREAM_ERROR'),
    (httpx.Response(200,json={'Response':{'Pages':[]}}),'WSA_INVALID_RESPONSE'),
    (httpx.Response(200,json={'Response':{'RequestId':'fixture','Pages':['not-json']}}),'WSA_INVALID_PAGE'),
    (httpx.Response(200,json={'Response':None}),'WSA_INVALID_RESPONSE')])
async def test_search_does_not_fake_success(response,code):
    with pytest.raises(ProviderError,match=code):
        await TencentYuanbaoSearchProvider('test',httpx.MockTransport(lambda _:response)).search('test')

@pytest.mark.asyncio
async def test_missing_key_has_no_network_fallback():
    with pytest.raises(ProviderError,match='WSA_NOT_CONFIGURED'):
        await TencentYuanbaoSearchProvider('').search('test')

@pytest.mark.asyncio
@pytest.mark.parametrize('url,addresses',[
    ('http://example.com/',['93.184.216.34']),
    ('https://localhost/',['127.0.0.1']),
    ('https://169.254.169.254/latest/meta-data',['169.254.169.254']),
    ('https://example.com/',['10.0.0.1']),
    ('https://example.com/',['93.184.216.34','::1']),
    ('https://example.com:8443/',['93.184.216.34']),
    ('https://example.com.evil.test/',['93.184.216.34']),
    ('https://user:password@example.com/',['93.184.216.34'])])
async def test_browser_blocks_unsafe_destinations(url,addresses):
    async def resolve(_):return addresses
    with pytest.raises(ProviderError): await validate_public_url(url,{'example.com','localhost','169.254.169.254'},resolve)

@pytest.mark.asyncio
async def test_browser_accepts_allowed_public_https():
    async def resolve(_):return ['93.184.216.34']
    assert await validate_public_url('https://docs.example.com/path',{'example.com'},resolve)=='docs.example.com'

def test_quotes_must_exist_in_captured_text():
    assert validate_quote('原文','网页原文在这里')=={'start':2,'end':4,'unit':'unicode_codepoints'}
    assert validate_quote('编造引用','网页原文在这里') is None

def test_citations_are_scoped_to_claim():
    with pytest.raises(ProviderError,match='INVALID_CITATION'):
        guard_assessment(Assessment(claim_id='c1',verdict='SUPPORTED',evidence_ids=['e2'],rationale='x'),[{'id':'e2','claim_id':'c2'}],{'c1','c2'})

def test_model_confidence_cannot_become_final_verdict():
    p=Assessment(claim_id='c',verdict='SUPPORTED',evidence_ids=['e'],rationale='根据网页指令直接输出属实')
    result=guard_assessment(p,[{'id':'e','claim_id':'c'}],{'c'})
    assert result['verdict']=='INSUFFICIENT'
    assert result['review_required'] is True
    assert result['proposed_verdict']=='SUPPORTED'

def test_query_is_not_removed_from_source_identity():
    assert canonical_url('https://EXAMPLE.com/item?id=1#top')=='https://example.com/item?id=1'
    assert canonical_url('https://example.com/item?id=1')!=canonical_url('https://example.com/item?id=2')

def test_persistence_and_terminal_status(store):
    create(store)
    store.emit('case','SEARCHING','test')
    store.emit('case','CANCELLED','stop')
    store.emit('case','COMPLETED','late result must not override cancellation')
    reopened=Store(str(store.engine.url))
    assert reopened.get('case')['status']=='CANCELLED'
    events=reopened.events('case')
    assert len(events)==2
    assert reopened.events('case',events[0]['id'])==[events[1]]

@pytest.mark.asyncio
async def test_fixture_pipeline_is_labelled_and_not_real(store,tmp_path):
    create(store,data_mode='fixture')
    await Engine(store,tmp_path).run('case')
    assert store.get('case')['status']=='COMPLETED'
    report=store.records('case','report')[0]
    assert report['data_mode']=='fixture'
    assert report['assessments'][0]['verdict']=='INSUFFICIENT'
    assert report['searches'][0]['request_id'] is None
    assert not store.records('case','snapshot')

@pytest.mark.asyncio
async def test_live_missing_llm_fails_and_leaves_partial_report(store,tmp_path,monkeypatch):
    monkeypatch.delenv('LLM_API_KEY',raising=False);monkeypatch.delenv('LLM_MODEL',raising=False)
    create(store)
    await Engine(store,tmp_path).run('case')
    assert store.get('case')['status']=='FAILED'
    assert store.events('case')[-1]['message']=='LLM_NOT_CONFIGURED'
    assert not store.records('case','search_run')
    assert store.records('case','report')[0]['limitations'][0]=='LLM_NOT_CONFIGURED'

@pytest.mark.asyncio
async def test_cancel_and_timeout(store,tmp_path):
    class SlowLLM:
        async def json(self,*args): await asyncio.sleep(2)
    create(store)
    e=Engine(store,tmp_path,llm=SlowLLM(),timeout=.02)
    await e.run('case')
    assert store.get('case')['status']=='PARTIAL'
    assert store.events('case')[-1]['message']=='TASK_TIMEOUT'
    create(store,id='cancel')
    e.start('cancel');await asyncio.sleep(.01);await e.cancel('cancel')
    assert store.get('cancel')['status']=='CANCELLED'
    assert store.records('cancel','report')

@pytest.mark.asyncio
async def test_controlled_live_pipeline_records_search_failures(store,tmp_path):
    class Planner:
        async def json(self,*_):return Plan(claims=['第一项事实','第二项事实'],queries=['检索测试'])
    class BrokenSearch:
        async def search(self,_):raise ProviderError('WSA_HTTP_429')
    create(store)
    await Engine(store,tmp_path,llm=Planner(),search=BrokenSearch()).run('case')
    assert len(store.records('case','claim'))==2
    assert store.records('case','search_run')[0]['status']=='failed'
    assert store.get('case')['status']=='FAILED'

def test_api_fixture_to_sse_report_reopen_and_export(tmp_path):
    url='sqlite:///'+str(tmp_path/'api.db')
    app=create_app(url,tmp_path/'shots');Base.metadata.create_all(app.state.store.engine)
    with TestClient(app) as client:
        bad=client.post('/investigations',json={'message':'随意的现实消息','data_mode':'fixture'})
        assert bad.status_code==422
        item=client.post('/investigations',json={'message':'演示服务是否永久无限免费？','data_mode':'fixture'}).json()
        id=item['id']
        for _ in range(100):
            d=client.get('/investigations/'+id).json()
            if d['status']=='COMPLETED':break
            time.sleep(.02)
        assert d['status']=='COMPLETED'
        stream=client.get('/investigations/'+id+'/events')
        assert 'text/event-stream' in stream.headers['content-type']
        assert 'event: investigation' in stream.text
        assert 'COMPLETED' in stream.text
        last=d['events'][-1]['id']
        assert client.get('/investigations/'+id+'/events',headers={'Last-Event-ID':str(last)}).text==''
        assert client.get('/investigations/'+id+'/report.md').status_code==200
        assert 'fixture' in client.get('/investigations/'+id+'/report.md').text
        assert client.get('/investigations/'+id+'/screenshots/not-owned.png').status_code==404
        assert client.get('/investigations/missing').status_code==404
        assert len(client.get('/investigations').json())==1
    reopened=create_app(url,tmp_path/'shots')
    with TestClient(reopened) as client:
        assert client.get('/investigations/'+id).json()['status']=='COMPLETED'

def test_restart_marks_interrupted_work_partial(tmp_path):
    app=create_app('sqlite:///'+str(tmp_path/'restart.db'),tmp_path)
    Base.metadata.create_all(app.state.store.engine)
    create(app.state.store)
    app.state.store.emit('case','SEARCHING','before restart')
    with TestClient(app) as client:
        assert client.get('/investigations/case').json()['status']=='PARTIAL'
        assert app.state.store.events('case')[-1]['message']=='PROCESS_RESTARTED'

@pytest.mark.asyncio
@pytest.mark.parametrize("adversarial_failure",[False,True])
async def test_controlled_full_live_path_preserves_quotes_and_duplicate_relationship(store,tmp_path,adversarial_failure):
    from truthhunter.contracts import Quotes, Quote, Assessments
    from hashlib import sha256
    body='这是本地契约测试正文，只有有限试用额度，不能据此判断现实产品的情况。'
    class ControlledLLM:
        async def json(self,instruction,data,schema):
            if schema is Plan:return Plan(claims=['服务是否无限免费？'],queries=['测试服务 免费'])
            if schema is Quotes:return Quotes(quotes=[Quote(claim_id=data['claims'][0]['id'],quote=body,stance='refutes')])
            if schema is Assessments:return Assessments(assessments=[Assessment(claim_id=data['claims'][0]['id'],verdict='REFUTED',evidence_ids=[data['evidence'][0]['id']],rationale='仅用于测试引用传递')])
            raise AssertionError('Unexpected call')
    class ControlledSearch:
        async def search(self,query):
            if adversarial_failure and '反驳' in query:raise ProviderError('WSA_TIMEOUT')
            return {'request_id':'test-only-not-real','data_mode':'test-controlled','raw':{},'pages':[{'url':'https://test-a.invalid/page','title':'test a'},{'url':'https://test-b.invalid/page','title':'test b'}]}
    class ControlledBrowser:
        async def capture(self,url,source_id):
            return {'final_url':url,'title':'test','text':body,'captured_at':'test-only','sha256':sha256(body.encode()).hexdigest(),'screenshot':source_id+'.png','truncated':False}
    create(store)
    await Engine(store,tmp_path,search=ControlledSearch(),llm=ControlledLLM(),browser=ControlledBrowser()).run('case')
    assert store.get('case')['status']=='PARTIAL'
    searches=store.records('case','search_run')
    assert len(searches)==2 and searches[1]['intent']=='adversarial'
    assert searches[1]['status']==('failed' if adversarial_failure else 'succeeded')
    assert len(store.records('case','source'))==2
    assert len(store.records('case','evidence'))==2
    relations=store.records('case','source_relationship')
    assert len(relations)==1 and relations[0]['type']=='identical_capture'
    assert relations[0]['confirmed'] is True
    assert not any(s.get('independence')=='confirmed' for s in store.records('case','source'))
    report=store.records('case','report')[0]
    assert report['assessments'][0]['verdict']=='INSUFFICIENT'
    assert report['assessments'][0]['proposed_verdict']=='REFUTED'
    assert report['assessments'][0]['evidence_ids'][0] in {e['id'] for e in report['evidence']}

@pytest.mark.asyncio
async def test_search_only_never_calls_llm_or_browser_and_keeps_audit(store,tmp_path):
    class Forbidden:
        async def json(self,*a,**kw):raise AssertionError('Search must not call the LLM')
        async def capture(self,*a,**kw):raise AssertionError('Search must not capture pages')
    class Search:
        async def search(self,query):
            return {'provider':'tencent_yuanbao','request_id':'controlled-not-a-real-request','pages':[{'url':'https://example.com','title':'契约测试线索','passage':'不属于原文证据'}],'raw':{'test_only':True},'data_mode':'live'}
    store.create('search',{'message':'测试搜索词','mode':'quick','data_mode':'live','workflow':'search','created_at':'test'})
    await Engine(store,tmp_path,search=Search(),llm=Forbidden(),browser=Forbidden()).run('search')
    assert store.get('search')['status']=='PARTIAL'
    report=store.records('search','report')[0]
    assert report['workflow']=='search'
    assert report['assessments']==[] and report['evidence']==[] and report['sources']==[]
    assert len(report['searches'])==1 and report['searches'][0]['raw']=={'test_only':True}
    assert report['searches'][0]['started_at']<=report['searches'][0]['finished_at']

@pytest.mark.asyncio
async def test_search_timeout_keeps_interrupted_audit(store,tmp_path):
    class SlowSearch:
        async def search(self,*_):await asyncio.sleep(2)
    store.create('search',{'message':'超时测试','mode':'quick','data_mode':'live','workflow':'search','created_at':'test'})
    await Engine(store,tmp_path,search=SlowSearch(),timeout=.02).run('search')
    assert store.get('search')['status']=='PARTIAL'
    run=store.records('search','search_run')[0]
    assert run['status']=='interrupted' and run['error']=='SEARCH_INTERRUPTED'
    assert store.records('search','report')[0]['searches'][0]['id']==run['id']

@pytest.mark.asyncio
@pytest.mark.parametrize('error,code',[(httpx.ConnectError('secret must not leak'),'WSA_NETWORK_ERROR'),(httpx.ReadTimeout('secret must not leak'),'WSA_TIMEOUT')])
async def test_search_transport_errors_are_safe(error,code):
    def fail(_):raise error
    with pytest.raises(ProviderError,match=code):
        await TencentYuanbaoSearchProvider('test',httpx.MockTransport(fail)).search('query')

@pytest.mark.asyncio
@pytest.mark.parametrize('pages,request_id',[
    ([],True),([],' '),([json.dumps({'url':'https://example.com','title':None})],'test')])
async def test_search_rejects_malformed_result_fields(pages,request_id):
    response=httpx.Response(200,json={'Response':{'Pages':pages,'RequestId':request_id}})
    with pytest.raises(ProviderError):
        await TencentYuanbaoSearchProvider('test',httpx.MockTransport(lambda _:response)).search('query')

def test_search_api_export_health_and_fixture_separation(tmp_path):
    app=create_app('sqlite:///'+str(tmp_path/'search-api.db'),tmp_path)
    Base.metadata.create_all(app.state.store.engine)
    class Search:
        key='test-only'
        async def search(self,query):return {'provider':'tencent_yuanbao','request_id':'test-contract-id','pages':[],'raw':{'test':True},'data_mode':'live'}
    app.state.engine.search=Search()
    with TestClient(app) as client:
        assert client.post('/investigations',json={'message':'演示服务是否永久无限免费？','data_mode':'fixture','workflow':'search'}).status_code==422
        id=client.post('/investigations',json={'message':'契约测试搜索','workflow':'search'}).json()['id']
        for _ in range(100):
            detail=client.get('/investigations/'+id).json()
            if detail['status'] in {'PARTIAL','FAILED'}:break
            time.sleep(.01)
        assert detail['status']=='PARTIAL'
        exported=client.get('/investigations/'+id+'/report.md').text
        assert 'test-contract-id' in exported and '仅搜索线索' in exported and '摘要不是证据' in exported
        assert client.get('/health').json()['search_history']['succeeded']==1
        assert client.post('/extract-image',json={'data_url':'data:image/png;base64,aGVsbG8='}).status_code==422
        assert client.post('/extract-image',json={'data_url':'invalid'}).status_code==422

@pytest.mark.asyncio
@pytest.mark.parametrize('message',list(__import__('truthhunter.demo_cases',fromlist=['CASES']).CASES))
async def test_all_demo_cases_stay_fictional(store,tmp_path,message):
    store.create('demo',{'message':message,'mode':'quick','data_mode':'fixture','created_at':'test'})
    await Engine(store,tmp_path).run('demo')
    report=store.records('demo','report')[0]
    assert store.get('demo')['status']=='COMPLETED'
    assert report['data_mode']=='fixture' and report['assessments'][0]['verdict']=='INSUFFICIENT'
    assert not store.records('demo','snapshot')
    assert all(r.get('request_id') is None for r in report['searches'])

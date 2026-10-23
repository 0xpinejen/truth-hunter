import asyncio
import hashlib
from uuid import uuid4
from urllib.parse import urlsplit, urlunsplit
from .contracts import Plan, Quotes, Assessments, TERMINAL
from .providers import TencentYuanbaoSearchProvider, CompatibleLLM, ProviderError
from .browser import BrowserAgent
from .store import now

def uid(): return uuid4().hex

def canonical_url(url):
    p = urlsplit(url)
    # Strip only fragments; query parameters can distinguish genuinely different documents.
    return urlunsplit((p.scheme.lower(),p.netloc.lower(),p.path or '/',p.query,''))

def validate_quote(quote, text):
    start = text.find(quote)
    return {'start':start,'end':start+len(quote),'unit':'unicode_codepoints'} if start >= 0 else None

def guard_assessment(proposal, evidence, claims):
    if proposal.claim_id not in claims: raise ProviderError('UNKNOWN_CLAIM')
    ids = list(dict.fromkeys(proposal.evidence_ids))
    by_id = {x['id']:x for x in evidence if x['claim_id']==proposal.claim_id}
    if any(x not in by_id for x in ids): raise ProviderError('INVALID_CITATION')
    # Exact excerpts alone do not establish relevance, source independence, or factual truth.
    # Until provenance review is implemented, substantive machine assessments remain proposals.
    return dict(proposal.model_dump(),evidence_ids=ids,proposed_verdict=proposal.verdict,
                verdict='INSUFFICIENT',review_required=True,
                limitation='来源独立性与证据相关性尚未完成复核，模型意见不是最终事实裁决。')

class Engine:
    def __init__(self, store, artifacts, search=None, llm=None, browser=None, timeout=180):
        self.store,self.artifacts = store,artifacts
        self.search = search or TencentYuanbaoSearchProvider()
        self.llm = llm or CompatibleLLM()
        self.browser = browser or BrowserAgent(artifacts)
        self.timeout = timeout
        self.tasks = {}

    def start(self, id):
        task = asyncio.create_task(self.run(id))
        self.tasks[id] = task
        task.add_done_callback(lambda _: self.tasks.pop(id,None))

    async def cancel(self, id):
        task = self.tasks.get(id)
        if task:
            task.cancel()
            try: await task
            except asyncio.CancelledError: pass
        row = self.store.get(id)
        if row and row['status'] not in TERMINAL:
            self.finish_partial(id,'CANCELLED','用户取消调查')

    def put(self,id,kind,data):
        rid=uid(); self.store.put(id,kind,data,rid); return dict(data,id=rid)

    def report(self,id,assessments=None,limitations=None):
        row=self.store.get(id)
        if self.store.records(id,'report'): return
        self.put(id,'report',{'title':row['message'],'created_at':now(),'data_mode':row['data_mode'],
            'assessments':assessments or [{'claim_id':c['id'],'verdict':'INSUFFICIENT','evidence_ids':[],'rationale':'调查未完成，不能得出事实结论。'} for c in self.store.records(id,'claim')],
            'limitations':limitations or [],'evidence':self.store.records(id,'evidence'),
            'sources':self.store.records(id,'source'),'searches':self.store.records(id,'search_run')})

    def finish_partial(self,id,status,message):
        self.report(id,limitations=[message,'该报告仅记录已执行的步骤，不构成已完成的事实核验。'])
        self.store.emit(id,status,message)

    async def run(self,id):
        try:
            async with asyncio.timeout(self.timeout):
                row=self.store.get(id)
                if row['data_mode']=='fixture': await self.fixture(id)
                else: await self.live(id,row)
        except asyncio.CancelledError:
            self.finish_partial(id,'CANCELLED','调查已取消'); raise
        except TimeoutError: self.finish_partial(id,'PARTIAL','TASK_TIMEOUT')
        except Exception as error:
            code=error.code if isinstance(error,ProviderError) else 'EXECUTION_ERROR'
            self.finish_partial(id,'PARTIAL' if self.store.records(id,'evidence') else 'FAILED',code)

    async def live(self,id,row):
        self.store.emit(id,'PLANNING','正在拆解消息并制定搜索计划')
        plan=await self.llm.json('把消息拆成可核验原子声明，并提供最多两条简短检索词。',row['message'],Plan)
        claims=[self.put(id,'claim',{'text':x}) for x in plan.claims]
        queries=[(q,'discovery') for q in plan.queries]
        queries.append((plan.queries[0]+' 官方 澄清 反驳','adversarial'))
        pages={}
        for query,intent in queries:
            self.store.emit(id,'SEARCHING','正在执行元宝搜索',query=query,intent=intent)
            started=now()
            try:
                result=await self.search.search(query)
                self.put(id,'search_run',{'query':query,'intent':intent,'started_at':started,'finished_at':now(),'status':'succeeded',**result})
            except Exception as e:
                self.put(id,'search_run',{'query':query,'intent':intent,'started_at':started,'finished_at':now(),'status':'failed','error':e.code if isinstance(e,ProviderError) else 'SEARCH_FAILED','data_mode':'live'})
                raise
            for p in result['pages']:
                try: key=canonical_url(p['url'])
                except ValueError: continue
                pages.setdefault(key,p)
        failures=0
        for url,p in list(pages.items())[:(3 if row['mode']=='quick' else 6)]:
            source=self.put(id,'source',{'url':url,'title':p.get('title',''),'published_at':p.get('date') or None,
                'search_excerpt':p.get('passage',''),'status':'discovered','independence':'unconfirmed','data_mode':'live'})
            self.store.emit(id,'BROWSING','浏览器正在访问来源',url=url,source_id=source['id'])
            try:
                snap=await self.browser.capture(url,source['id'])
                snapshot=self.put(id,'snapshot',dict(snap,source_id=source['id'],data_mode='live'))
                self.store.emit(id,'EXTRACTING','已保存页面，正在定位原文证据',source_id=source['id'],screenshot=snap['screenshot'])
                quotes=await self.llm.json('只摘录正文中与声明直接有关的逐字原文，不得改写。返回 claim_id、quote、stance。没有则空列表。',{'claims':claims,'source_text':snap['text']},Quotes)
                for q in quotes.quotes:
                    span=validate_quote(q.quote,snap['text'])
                    if not span or q.claim_id not in {c['id'] for c in claims}: continue
                    self.put(id,'evidence',dict(q.model_dump(),source_id=source['id'],snapshot_id=snapshot['id'],url=snap['final_url'],locator=span,sha256=snap['sha256'],captured_at=snap['captured_at'],data_mode='live'))
            except asyncio.CancelledError: raise
            except Exception as e:
                failures+=1
                self.put(id,'capture_failure',{'source_id':source['id'],'code':e.code if isinstance(e,ProviderError) else 'CAPTURE_OR_EXTRACTION_FAILED'})
                self.store.emit(id,'BROWSING','来源访问或证据提取失败，已记录',source_id=source['id'])
        evidence=self.store.records(id,'evidence')
        snapshots=self.store.records(id,'snapshot')
        for i,a in enumerate(snapshots):
            for b in snapshots[i+1:]:
                if a['sha256']==b['sha256']:
                    self.put(id,'source_relationship',{'from_source':a['source_id'],'to_source':b['source_id'],'type':'identical_capture','confirmed':True,'reason':'抓取正文哈希相同；不表示已确认谁转载谁。'})
        self.store.emit(id,'VERIFYING','正在核对证据引用；来源独立性仍需复核')
        assessments=[]
        if evidence:
            proposed=await self.llm.json('对每个声明分析证据，引用且仅引用输入 evidence_ids。证据不足返回 INSUFFICIENT。',{'claims':claims,'evidence':evidence},Assessments)
            for a in proposed.assessments:
                assessments.append(guard_assessment(a,evidence,{c['id'] for c in claims}))
        assessed={x['claim_id'] for x in assessments}
        for c in claims:
            if c['id'] not in assessed:
                assessments.append({'claim_id':c['id'],'verdict':'INSUFFICIENT','evidence_ids':[],'rationale':'未获得可引用的完整核验结果。'})
        self.store.emit(id,'REPORTING','正在生成可追溯的阶段报告')
        self.report(id,assessments,['来源独立性核查与人工复核流程尚未实现，最终结论统一保留为证据不足。',f'{failures} 个来源访问或提取失败。','搜索摘要仅用于发现线索，不作为原文证据。'])
        self.store.emit(id,'PARTIAL','阶段报告已生成，事实核验尚未完成')

    async def fixture(self,id):
        for status,message in [('PLANNING','演示：拆解虚构消息'),('SEARCHING','演示：读取本地测试资料，未调用元宝 API'),('BROWSING','演示：使用本地页面样本，未访问真实网页')]:
            self.store.emit(id,status,message,data_mode='fixture'); await asyncio.sleep(.08)
        claim=self.put(id,'claim',{'text':'演示服务是否永久无限免费？','data_mode':'fixture'})
        self.put(id,'search_run',{'query':'演示服务 免费额度','status':'fixture','request_id':None,'pages':[],'data_mode':'fixture'})
        source=self.put(id,'source',{'title':'虚构服务条款 · 本地测试样本','url':'https://fixture.invalid/terms','status':'fixture','independence':'unconfirmed','data_mode':'fixture'})
        text='本地测试样本：基础功能在试用期内免费，试用结束后需要订阅。此内容为虚构数据。'
        evidence=self.put(id,'evidence',{'claim_id':claim['id'],'source_id':source['id'],'url':source['url'],'quote':text,'stance':'context','locator':{'start':0,'end':len(text),'unit':'unicode_codepoints'},'sha256':hashlib.sha256(text.encode()).hexdigest(),'captured_at':now(),'data_mode':'fixture'})
        for status,message in [('EXTRACTING','演示：定位样本文本'),('VERIFYING','演示：保留证据不足结论'),('REPORTING','演示：生成测试报告')]:
            self.store.emit(id,status,message,data_mode='fixture'); await asyncio.sleep(.08)
        self.report(id,[{'claim_id':claim['id'],'verdict':'INSUFFICIENT','evidence_ids':[evidence['id']],'rationale':'虚构测试资料不能证明任何现实消息。'}],['全部内容为本地 fixture；没有真实 API 请求、网页访问或现实核验结论。'])
        self.store.emit(id,'COMPLETED','演示流程完成；这不是真实调查',data_mode='fixture')

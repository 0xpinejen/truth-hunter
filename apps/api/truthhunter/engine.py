import asyncio
import hashlib
from uuid import uuid4
from urllib.parse import urlsplit, urlunsplit
from .contracts import Plan, Quotes, Assessments, TERMINAL, SourceSelection
from .providers import TencentYuanbaoSearchProvider, CompatibleLLM, ProviderError, llm_audit
from .browser import BrowserAgent
from .store import now
from .demo_cases import CASES

def uid(): return uuid4().hex

def canonical_url(url):
    p = urlsplit(url)
    # Strip only fragments; query parameters can distinguish genuinely different documents.
    return urlunsplit((p.scheme.lower(),p.netloc.lower(),p.path or '/',p.query,''))

def candidate_is_allowed(url,allowed):
    try:
        p=urlsplit(url);host=(p.hostname or '').lower().rstrip('.')
        return bool(p.scheme=='https' and host and not p.username and not p.password and p.port in (None,443) and (allowed is None or any(host==d or host.endswith('.'+d) for d in allowed)))
    except ValueError:return False

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

    async def model_json(self,id,instruction,data,schema):
        started=now();llm_audit.set(None)
        audit={'schema':schema.__name__,'instruction':instruction,'system_prompt_version':1,'started_at':started,'input_sha256':hashlib.sha256(__import__('json').dumps(data,ensure_ascii=False,sort_keys=True).encode()).hexdigest(),'data_mode':'live'}
        try:
            result=await self.llm.json(instruction,data,schema)
            self.put(id,'model_run',dict(audit,finished_at=now(),status='succeeded',output=result.model_dump(),**(llm_audit.get() or {})))
            return result
        except BaseException as error:
            self.put(id,'model_run',dict(audit,finished_at=now(),status='interrupted' if isinstance(error,asyncio.CancelledError) else 'failed',error=error.code if isinstance(error,ProviderError) else 'MODEL_CALL_INTERRUPTED_OR_INVALID',**(llm_audit.get() or {})))
            raise

    def report(self,id,assessments=None,limitations=None):
        row=self.store.get(id)
        if self.store.records(id,'report'): return
        self.put(id,'report',{'title':row['message'],'created_at':now(),'data_mode':row['data_mode'],
            'assessments':assessments or [{'claim_id':c['id'],'verdict':'INSUFFICIENT','evidence_ids':[],'rationale':'调查未完成，不能得出事实结论。'} for c in self.store.records(id,'claim')],
            'limitations':limitations or [],'evidence':self.store.records(id,'evidence'),
            'sources':self.store.records(id,'source'),'searches':self.store.records(id,'search_run'),
            'workflow':row.get('workflow','investigation'),'revision':1})

    def finish_partial(self,id,status,message):
        self.report(id,limitations=[message,'该报告仅记录已执行的步骤，不构成已完成的事实核验。'])
        self.store.emit(id,status,message)

    async def run(self,id):
        try:
            async with asyncio.timeout(self.timeout):
                row=self.store.get(id)
                if row['data_mode']=='fixture': await self.fixture(id)
                elif row.get('workflow')=='search': await self.search_only(id,row)
                else: await self.live(id,row)
        except asyncio.CancelledError:
            self.finish_partial(id,'CANCELLED','调查已取消'); raise
        except TimeoutError: self.finish_partial(id,'PARTIAL','TASK_TIMEOUT')
        except Exception as error:
            code=error.code if isinstance(error,ProviderError) else 'EXECUTION_ERROR'
            self.finish_partial(id,'PARTIAL' if self.store.records(id,'evidence') else 'FAILED',code)

    async def search_query(self,id,query,intent):
        self.store.emit(id,'SEARCHING','腾讯元宝搜索正在检索公开线索',query=query,intent=intent)
        started=now()
        run={'query':query,'intent':intent,'started_at':started,'provider':'tencent_yuanbao','data_mode':'live'}
        try:
            result=await self.search.search(query)
        except asyncio.CancelledError:
            self.put(id,'search_run',dict(run,finished_at=now(),status='interrupted',error='SEARCH_INTERRUPTED'))
            raise
        except Exception as error:
            self.put(id,'search_run',dict(run,finished_at=now(),status='failed',error=error.code if isinstance(error,ProviderError) else 'SEARCH_FAILED'))
            raise
        self.put(id,'search_run',dict(run,finished_at=now(),status='succeeded',**result))
        return result

    async def search_only(self,id,row):
        result=await self.search_query(id,row['message'],'discovery')
        self.store.emit(id,'REPORTING',f"元宝返回 {len(result['pages'])} 条线索，正在保存检索记录")
        self.report(id,limitations=['本次仅执行一次腾讯元宝搜索，未调用模型、访问网页或核验事实。','搜索摘要是检索线索，不是原文证据；RequestId 只说明服务返回了请求记录。'])
        self.store.emit(id,'PARTIAL','搜索完成；尚未进行事实核验')

    async def live(self,id,row):
        self.store.emit(id,'PLANNING','正在拆解消息并制定搜索计划')
        plan=await self.model_json(id,'把消息拆成可核验原子声明（保持原消息的肯定或否定说法，不能擅自纠正它），提供最多两条搜索词，优先第一方原始记录。',row['message'],Plan)
        claims=[self.put(id,'claim',{'text':x}) for x in plan.claims]
        queries=[(q,'discovery') for q in plan.queries]
        queries.append((plan.queries[0]+' 官方 澄清 反驳','adversarial'))
        pages={};search_failures=[]
        for query,intent in queries:
            try:result=await self.search_query(id,query,intent)
            except ProviderError as error:
                if not pages:raise
                search_failures.append(error.code)
                self.store.emit(id,'SEARCHING','本次检索失败，继续核对已有线索；失败不会计为反证完成',code=error.code)
                continue
            for p in result['pages']:
                try: key=canonical_url(p['url'])
                except ValueError: continue
                if key not in pages:pages[key]=dict(p,search_intents=[intent])
                elif intent not in pages[key]['search_intents']:pages[key]['search_intents'].append(intent)
        failures=0
        limit=3 if row['mode']=='quick' else 6
        allowed=getattr(self.browser,'allowed',None)
        candidates={uid():dict(p,url=url) for url,p in pages.items() if candidate_is_allowed(url,allowed)}
        selected=list(candidates)[:limit]
        if candidates and isinstance(self.llm,CompatibleLLM):
            selection=await self.model_json(id,'从实际返回的候选项选择最多'+str(limit)+'个source_ids。优先原始文件、不同出处、直接相关的支持和反驳内容，不能发明ID；同一原文不同网址不应挤占名额。',{'claims':claims,'candidates':[dict(p,id=k,passage=p.get('passage','')[:1800]) for k,p in candidates.items()]},SourceSelection)
            if any(k not in candidates for k in selection.source_ids):raise ProviderError('UNKNOWN_SELECTED_SOURCE')
            selected=list(dict.fromkeys(selection.source_ids))[:limit]
            self.put(id,'source_selection',selection.model_dump())
        adversarial=[k for k,p in candidates.items() if 'adversarial' in p['search_intents']]
        if adversarial and not any(k in adversarial for k in selected):selected=(selected[:limit-1]+adversarial[:1])
        for key in selected:
            p=candidates[key];url=p['url']
            source=self.put(id,'source',{'url':url,'title':p.get('title',''),'published_at':p.get('date') or None,
                'search_excerpt':p.get('passage',''),'search_intents':p['search_intents'],'status':'discovered','independence':'unconfirmed','data_mode':'live'})
            self.store.emit(id,'BROWSING','浏览器正在访问来源',url=url,source_id=source['id'])
            try:
                snap=await self.browser.capture(url,source['id'])
                snapshot=self.put(id,'snapshot',dict(snap,source_id=source['id'],data_mode='live'))
                self.store.emit(id,'EXTRACTING','已保存页面，正在定位原文证据',source_id=source['id'],screenshot=snap['screenshot'])
                quotes=await self.model_json(id,'只摘录正文中与声明直接有关的连续逐字原文，不得改写、拼接、省略；注意原消息中的日期与否定词。返回claim_id、quote、stance，无关则空列表。同时建议publisher、origin_kind、provenance_reason；如明确引用其他出处，填写逐字attribution_quote与页面实际links中的origin_url，无依据则unknown及空字符串。来源建议不等于独立性确认。',{'claims':claims,'source_text':snap['text'],'url':snap['final_url'],'links':snap.get('links',[])},Quotes)
                attribution=bool(quotes.attribution_quote and quotes.attribution_quote in snap['text'] and quotes.origin_url in {link['url'] for link in snap.get('links',[])})
                self.put(id,'source_profile',{'source_id':source['id'],'publisher':quotes.publisher,'origin_kind':quotes.origin_kind,'attribution_quote':quotes.attribution_quote,'origin_url':quotes.origin_url if attribution else '',
                    'attribution_verified':attribution,'rationale':quotes.provenance_reason,'review_required':True,'data_mode':'live'})
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
            proposed=await self.model_json(id,'对每个声明比较支持和反驳证据，引用且仅引用输入 evidence_ids。证据不足返回 INSUFFICIENT。不要把多个网址当作独立信源，保留冲突、时间和范围限制。',{'claims':claims,'evidence':evidence,'source_profiles':self.store.records(id,'source_profile')},Assessments)
            for a in proposed.assessments:
                assessments.append(guard_assessment(a,evidence,{c['id'] for c in claims}))
        assessed={x['claim_id'] for x in assessments}
        for c in claims:
            if c['id'] not in assessed:
                assessments.append({'claim_id':c['id'],'verdict':'INSUFFICIENT','evidence_ids':[],'rationale':'未获得可引用的完整核验结果。'})
        self.store.emit(id,'REPORTING','正在生成可追溯的阶段报告')
        self.report(id,assessments,['模型提议尚未经显式复核，不能作为最终事实裁决。',f'{failures} 个来源访问或提取失败。',f'{len(search_failures)} 次检索失败：'+('、'.join(search_failures) or '无')+'。','搜索摘要仅用于发现线索，不作为原文证据。'])
        self.store.emit(id,'PARTIAL','证据阶段完成，等待来源与结论复核')

    async def fixture(self,id):
        for status,message in [('PLANNING','演示：拆解虚构消息'),('SEARCHING','演示：读取本地测试资料，未调用元宝 API'),('BROWSING','演示：使用本地页面样本，未访问真实网页')]:
            self.store.emit(id,status,message,data_mode='fixture'); await asyncio.sleep(.08)
        message=self.store.get(id)['message']
        sample=CASES[message]
        claim=self.put(id,'claim',{'text':message,'data_mode':'fixture'})
        self.put(id,'search_run',{'query':'演示服务 免费额度','status':'fixture','request_id':None,'pages':[],'data_mode':'fixture'})
        source=self.put(id,'source',{'title':sample['title'],'url':'https://fixture.invalid/terms','status':'fixture','independence':'unconfirmed','data_mode':'fixture'})
        text=sample['text']
        evidence=self.put(id,'evidence',{'claim_id':claim['id'],'source_id':source['id'],'url':source['url'],'quote':text,'stance':'context','locator':{'start':0,'end':len(text),'unit':'unicode_codepoints'},'sha256':hashlib.sha256(text.encode()).hexdigest(),'captured_at':now(),'data_mode':'fixture'})
        for status,message in [('EXTRACTING','演示：定位样本文本'),('VERIFYING','演示：保留证据不足结论'),('REPORTING','演示：生成测试报告')]:
            self.store.emit(id,status,message,data_mode='fixture'); await asyncio.sleep(.08)
        self.report(id,[{'claim_id':claim['id'],'verdict':'INSUFFICIENT','evidence_ids':[evidence['id']],'rationale':'虚构测试资料不能证明任何现实消息。'}],['全部内容为本地 fixture；没有真实 API 请求、网页访问或现实核验结论。'])
        self.store.emit(id,'COMPLETED','演示流程完成；这不是真实调查',data_mode='fixture')

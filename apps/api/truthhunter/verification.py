"""Explicit, auditable review gates. Model proposals cannot call this finalizer."""
from urllib.parse import urlsplit
from hashlib import sha256
from .providers import ProviderError

def publisher_domain(url):
    host=(urlsplit(url).hostname or '').lower().rstrip('.')
    parts=host.split('.')
    count=3 if '.'.join(parts[-2:]) in {'com.cn','gov.cn','org.cn','co.uk','ac.uk','com.au','co.jp'} else 2
    return '.'.join(parts[-count:])

def adjudicate(submission,records):
    def fail(code):raise ProviderError(code)
    if not submission.acknowledged:fail('REVIEW_ACKNOWLEDGEMENT_REQUIRED')
    claims={r['id']:r for r in records if r['kind']=='claim'}
    evidence={r['id']:r for r in records if r['kind']=='evidence'}
    sources={r['id']:r for r in records if r['kind']=='source'}
    snapshots={r['source_id']:r for r in records if r['kind']=='snapshot'}
    def unique(rows,key):
        ids=[getattr(r,key) for r in rows]
        if len(ids)!=len(set(ids)):fail('DUPLICATE_REVIEW')
    unique(submission.sources,'source_id');unique(submission.evidence,'evidence_id');unique(submission.claims,'claim_id')
    if {r.claim_id for r in submission.claims}!=set(claims):fail('REVIEW_ALL_CLAIMS_REQUIRED')
    sr={r.source_id:r for r in submission.sources}
    er={r.evidence_id:r for r in submission.evidence}
    for id,r in sr.items():
        snap=snapshots.get(id)
        if id not in sources or not snap or r.basis_quote not in snap['text']:fail('REVIEW_SOURCE_BASIS_NOT_FOUND')
        if snap.get('transport')!='public_ip_pinned_tls_v2' or not snap.get('browser_offline'):fail('REVIEW_CAPTURE_REVALIDATION_REQUIRED')
        if r.role in {'unknown','attributed'} and r.independence_confirmed:fail('REVIEW_UNKNOWN_INDEPENDENCE')
    for id,r in er.items():
        e=evidence.get(id)
        snap=snapshots.get(e['source_id']) if e else None
        if not e or not snap or e['source_id'] not in sr:fail('REVIEW_UNKNOWN_EVIDENCE')
        text=snap['text'];loc=e['locator']
        if text[loc['start']:loc['end']]!=e['quote'] or snap['sha256']!=e['sha256'] or sha256(text.encode()).hexdigest()!=snap['sha256']:fail('REVIEW_INVALID_QUOTE')
    # Union source groups by reviewer-declared origin, shared publisher, original URL,
    # or identical captured body. A different domain never establishes independence.
    parent={id:id for id in sr}
    def root(x):
        while parent[x]!=x:x=parent[x]
        return x
    def union(a,b):parent[root(b)]=root(a)
    ids=list(sr)
    profiles={r['source_id']:r for r in records if r['kind']=='source_profile'}
    for i,a in enumerate(ids):
        for b in ids[i+1:]:
            if (sr[a].origin_group.casefold()==sr[b].origin_group.casefold()
                or publisher_domain(sources[a]['url'])==publisher_domain(sources[b]['url'])
                or snapshots[a]['sha256']==snapshots[b]['sha256']):union(a,b)
            # Only a captured attribution link is used for merging, never model guesses.
            for source,target in ((a,b),(b,a)):
                profile=profiles.get(source,{})
                if profile.get('attribution_verified') and profile.get('origin_url','').split('#')[0]==snapshots[target]['final_url'].split('#')[0]:union(a,b)
    adversarial=any(r['kind']=='search_run' and r.get('intent')=='adversarial' and r.get('status')=='succeeded' for r in records)
    results=[]
    for c in submission.claims:
        candidates=[evidence[id] for id,r in er.items() if evidence[id]['claim_id']==c.claim_id and r.relevant and r.time_matches and r.stance!='context']
        sides={stance:[e for e in candidates if er[e['id']].stance==stance] for stance in ('supports','refutes')}
        groups={stance:{root(e['source_id']) for e in es if sr[e['source_id']].independence_confirmed and sr[e['source_id']].role in {'primary','original_reporting'}} for stance,es in sides.items()}
        verdict='INSUFFICIENT';reason='未满足裁决门槛。'
        if c.method!='insufficient' and adversarial:
            if sides['supports'] and sides['refutes']:
                verdict='CONFLICTED';reason='经复核的支持与反驳证据同时存在，保留冲突。'
            elif c.method=='independent_sources':
                for stance,target in [('supports','SUPPORTED'),('refutes','REFUTED')]:
                    if len(groups[stance])>=2:verdict=target;reason='至少两个经显式复核的独立出处组一致，且已执行反证搜索。'
            elif c.method=='primary_document':
                if len(c.documentary_scope.strip())<20:fail('REVIEW_DOCUMENTARY_SCOPE_REQUIRED')
                for stance,target in [('supports','SUPPORTED'),('refutes','REFUTED')]:
                    if any(sr[e['source_id']].role=='primary' for e in sides[stance]):
                        verdict=target;reason='仅限复核者明确界定的第一方文件记载，不推广为一般现实事实。'
        results.append({'claim_id':c.claim_id,'verdict':verdict,'evidence_ids':[e['id'] for e in candidates],
            'rationale':c.rationale,'review_required':False,'method':c.method,'documentary_scope':c.documentary_scope,
            'decision_basis':reason,'independent_support_groups':len(groups['supports']),'independent_refute_groups':len(groups['refutes']),
            'adversarial_search_completed':adversarial})
    return results, {id:root(id) for id in sr}

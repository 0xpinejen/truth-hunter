"""Audit persisted live case integrity against files, review rules and the running local API.
This verifies traceability, not the truth of every source or the independence judgement itself.
"""
import argparse
import hashlib
import ipaddress
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit
import httpx
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'apps/api'))
from truthhunter.store import Store,now
from truthhunter.contracts import ReviewSubmission
from truthhunter.verification import adjudicate

def audit(store,artifacts,id,client):
    row=store.get(id);assert row and row['data_mode']=='live' and row['workflow']=='investigation'
    assert row['status']=='COMPLETED'
    records=store.records(id)
    kind=lambda name:[r for r in records if r['kind']==name]
    claims={r['id']:r for r in kind('claim')};sources={r['id']:r for r in kind('source')};snaps={r['id']:r for r in kind('snapshot')}
    assert claims and snaps
    searches=kind('search_run');assert 1<=len(searches)<=3
    assert any(r.get('intent')=='adversarial' and r['status']=='succeeded' for r in searches)
    for run in searches:
        if run['status']=='succeeded':assert run['request_id'] and run['raw']['RequestId']==run['request_id']
    for snap in snaps.values():
        assert snap['source_id'] in sources and snap['transport']=='public_ip_pinned_tls_v2' and snap.get('browser_offline') is True
        assert hashlib.sha256(snap['text'].encode()).hexdigest()==snap['sha256']
        shot=Path(snap['screenshot']);assert shot.name==str(shot)
        assert (artifacts/shot).read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
        assert (artifacts/shot.with_suffix('.txt')).read_bytes().decode()==snap['text']
        good=[r for r in snap['network'] if 'public_ip' in r]
        assert any(r['url']==snap['final_url'] and r['status']==200 for r in good)
        for r in good:
            assert ipaddress.ip_address(r['public_ip']).is_global
            assert (urlsplit(r['url']).hostname or '').rstrip('.')==r['tls_hostname']
        response=client.get(f'/investigations/{id}/screenshots/{shot.name}');assert response.status_code==200
        assert response.content==(artifacts/shot).read_bytes()
        assert client.get(f'/investigations/{id}/snapshots/{snap["id"]}').json()['sha256']==snap['sha256']
    for e in kind('evidence'):
        snap=snaps[e['snapshot_id']];assert e['source_id']==snap['source_id'] and e['claim_id'] in claims
        assert snap['text'][e['locator']['start']:e['locator']['end']]==e['quote']
        assert e['sha256']==snap['sha256'] and e['url']==snap['final_url']
    models=kind('model_run');assert models
    for run in models:
        if run['status']=='succeeded':assert run['request_id'] and run['raw']['id']==run['request_id'] and run['usage']['total_tokens']>0
    report=max(kind('report'),key=lambda r:r.get('revision',1));assert report['revision']>=2
    review=next(r for r in kind('review') if r['id']==report['review_id'])
    recalculated,groups=adjudicate(ReviewSubmission.model_validate({k:v for k,v in review.items() if k in ReviewSubmission.model_fields}),records)
    assert recalculated==report['assessments'] and groups==review['resolved_groups']
    assert {a['claim_id'] for a in report['assessments']}==set(claims)
    events=store.events(id);assert events[-1]['status']=='COMPLETED'
    stream=client.get(f'/investigations/{id}/events');assert stream.status_code==200
    replay=[json.loads(line[6:]) for line in stream.text.splitlines() if line.startswith('data: ')]
    assert replay==events
    assert client.get(f'/investigations/{id}/events',headers={'Last-Event-ID':str(events[-1]['id'])}).text==''
    exported=client.get(f'/investigations/{id}/report.md');assert exported.status_code==200
    assert '报告版本：'+str(report['revision']) in exported.text
    return {'id':id,'message':row['message'],'status':row['status'],'search_request_ids':[r['request_id'] for r in searches if r['status']=='succeeded'],
            'snapshots':len(snaps),'evidence':len(kind('evidence')),'capture_failures':kind('capture_failure'),'model_calls':len(models),
            'model_request_ids':[r['request_id'] for r in models if r.get('request_id')],
            'tokens':sum(r.get('usage',{}).get('total_tokens',0) for r in models),'report_revision':report['revision'],
            'review_type':review['review_type'],'assessments':report['assessments'],'events':len(events),'checks':'files, public IP/TLS identity, exact quotes, model IDs, review recomputation, API screenshot/text, SSE replay/cursor, latest Markdown'}

def main():
    p=argparse.ArgumentParser();p.add_argument('ids',nargs='+');p.add_argument('--database',default='sqlite:///./apps/api/data/truthhunter.db');p.add_argument('--artifacts',default='apps/api/artifacts');p.add_argument('--api',default='http://127.0.0.1:8000');p.add_argument('--out',default='artifacts/live-acceptance.json');a=p.parse_args()
    store=Store(a.database)
    with httpx.Client(base_url=a.api,trust_env=False,timeout=20) as client:results=[audit(store,Path(a.artifacts),id,client) for id in a.ids]
    report={'audited_at':now(),'data_mode':'live','note':'Traceability and explicit review audit; not a claim of independent human fact-checking or cross-organization verification.','cases':results}
    out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    for r in results:print(r['id'],r['status'],[a['verdict'] for a in r['assessments']],f"{r['snapshots']} snapshots, {r['evidence']} quotes, revision {r['report_revision']}")
if __name__=='__main__':main()

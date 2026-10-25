"""Withdraw final conclusions based on the superseded v1 capture transport.
Keeps every original report, review, snapshot and event; run only on explicit case IDs.
"""
import argparse,json,sys
from uuid import uuid4
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'apps/api'))
from truthhunter.store import Store,Record,Event,Investigation,now
p=argparse.ArgumentParser();p.add_argument('ids',nargs='+');a=p.parse_args()
s=Store('sqlite:///./apps/api/data/truthhunter.db')
reason='最终审计发现旧版取证的浏览器重定向未逐跳固定公网连接。撤回旧结论，原资料仅保留历史；需用 v2 离线渲染及受控逐跳取证重新调查。'
for id in a.ids:
 row=s.get(id);assert row and row['data_mode']=='live'
 if not any(r.get('transport')!='public_ip_pinned_tls_v2' for r in s.records(id,'snapshot')):continue
 current=max(s.records(id,'report'),key=lambda r:r.get('revision',1))
 payload={k:v for k,v in current.items() if k not in {'id','kind'}}
 payload.update(created_at=now(),revision=current.get('revision',1)+1,previous_report_id=current['id'],review=None,review_id=None,capture_revalidation_required=True,
     limitations=current['limitations']+[reason],assessments=[dict(a,previous_verdict=a['verdict'],verdict='INSUFFICIENT',review_required=True,rationale=reason) for a in current['assessments']])
 rid=uuid4().hex
 with s.session.begin() as db:
  entity=db.get(Investigation,id);entity.status='PARTIAL'
  db.add(Record(id=rid,investigation_id=id,kind='report',payload=json.dumps(payload,ensure_ascii=False)))
  db.add(Record(id=uuid4().hex,investigation_id=id,kind='audit_invalidation',payload=json.dumps({'reason':reason,'previous_report_id':current['id'],'replacement_report_id':rid,'created_at':now()},ensure_ascii=False)))
  db.add(Event(investigation_id=id,payload=json.dumps({'status':'PARTIAL','message':reason,'created_at':now(),'report_id':rid},ensure_ascii=False)))
 print(id,'PARTIAL','historical reports preserved; revalidation required')

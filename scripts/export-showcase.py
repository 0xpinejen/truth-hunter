"""Export only the four approved public acceptance cases; never export the database or raw provider payloads."""
import json, sqlite3, shutil, hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'apps/web/public/showcase'
IDS=['5b2229b18b064be394f630ed6999560a','e70e6f577a974a6082be1ab570e54389','7cf8c1e35d4b43308b57d1dfe79f888c','a58f7022b69a4a909f541f2725003971']
FIELDS={
 'claim': ['text','data_mode'],
 'source':['title','url','status','data_mode','independence'],
 'evidence':['claim_id','source_id','url','quote','stance','locator','sha256','captured_at','data_mode'],
 'snapshot':['source_id','title','final_url','captured_at','sha256','text','truncated','transport','browser_offline','resource_bundle_limited','screenshot'],
 'search_run':['query','intent','status','request_id','started_at','finished_at','provider','data_mode'],
 'source_profile':['source_id','publisher','origin_kind'],
 'model_run':['schema','status','model','usage','request_id','started_at','finished_at'],
 'report':['revision','assessments','limitations','review','data_mode','created_at'],
}
def main():
 OUT.mkdir(parents=True,exist_ok=True)
 db=sqlite3.connect(f"file:{ROOT/'apps/api/data/truthhunter.db'}?mode=ro",uri=True)
 cases=[]
 for case_id in IDS:
  row=db.execute('select payload,status from investigations where id=?',(case_id,)).fetchone()
  assert row and row[1]=='COMPLETED',case_id
  payload=json.loads(row[0]);assert payload['data_mode']=='live'
  detail={k:payload[k] for k in ['message','mode','workflow','data_mode','created_at'] if k in payload}
  detail.update(id=case_id,status=row[1],readonly=True,publication_note='已验收公开案例的只读节选。查询、引文、复核与时间来自本地存档；未公开完整模型输入、原始返回及网络日志；在线打开不触发新调查。')
  records=[]
  rows=db.execute('select id,kind,payload from records where investigation_id=?',(case_id,)).fetchall()
  maxrev=max(json.loads(v).get('revision',1) for _,k,v in rows if k=='report')
  for record_id,kind,raw in rows:
   if kind not in FIELDS:continue
   data=json.loads(raw)
   if kind=='report' and data.get('revision',1)!=maxrev:continue
   record={k:data[k] for k in FIELDS[kind] if k in data}
   record.update(id=record_id,kind=kind)
   if kind=='snapshot':
    assert data['transport']=='public_ip_pinned_tls_v2'
    assert hashlib.sha256(data['text'].encode()).hexdigest()==data['sha256']
    shot=Path(data['screenshot']);assert shot.name==str(shot)
    target=OUT/case_id;target.mkdir(exist_ok=True)
    shutil.copy2(ROOT/'apps/api/artifacts'/shot,target/shot)
   if kind in {'search_run','model_run'}:record['publication_note']='公开节选：完整原始调用返回仅保存在本地审计档案。'
   records.append(record)
  detail['records']=records
  detail['events']=[dict(json.loads(raw),id=i) for i,raw in db.execute('select id,payload from events where investigation_id=? order by id',(case_id,))]
  (OUT/f'{case_id}.json').write_text(json.dumps(detail,ensure_ascii=False),encoding='utf-8')
  reports=['tencent-final-report.md','python-final-report.md','mars-final-report.md','independent-eclipse-final-report.md']
  shutil.copy2(ROOT/'artifacts'/reports[IDS.index(case_id)],OUT/case_id/'report.md')
  cases.append({**{k:v for k,v in detail.items() if k not in {'records','events'}},'source_count':sum(x['kind']=='snapshot' for x in records),'evidence_count':sum(x['kind']=='evidence' for x in records),'verdict':next(x for x in records if x['kind']=='report')['assessments'][0]['verdict']})
 (OUT/'index.json').write_text(json.dumps(cases,ensure_ascii=False),encoding='utf-8')
 print(f'Exported {len(cases)} approved public cases. No credentials, database or raw provider payloads exported.')
if __name__=='__main__':main()

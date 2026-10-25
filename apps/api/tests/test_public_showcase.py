"""Integrity tests for the intentionally selected public subset, independent of local DB."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
PUBLIC=ROOT/'apps/web/public/showcase'

def cases():
    return [json.loads((PUBLIC/f"{i['id']}.json").read_text()) for i in json.loads((PUBLIC/'index.json').read_text())]

def test_public_subset_retains_original_citation_integrity():
    exported=cases()
    assert len(exported)==4
    for case in exported:
        assert case['readonly'] and case['data_mode']=='live' and case['status']=='COMPLETED'
        records=case['records']
        snapshots={r['source_id']:r for r in records if r['kind']=='snapshot'}
        for snap in snapshots.values():
            assert hashlib.sha256(snap['text'].encode()).hexdigest()==snap['sha256']
            assert snap['transport']=='public_ip_pinned_tls_v2' and snap['browser_offline']
            assert (PUBLIC/case['id']/snap['screenshot']).read_bytes().startswith(b'\x89PNG')
        for evidence in [r for r in records if r['kind']=='evidence']:
            snap=snapshots[evidence['source_id']]
            assert snap['sha256']==evidence['sha256']
            assert snap['text'][evidence['locator']['start']:evidence['locator']['end']]==evidence['quote']
        report=next(r for r in records if r['kind']=='report')
        assert report['revision']==2 and report['review']['review_type']=='assistant'
        assert (PUBLIC/case['id']/'report.md').is_file()

def test_public_subset_contains_no_raw_provider_or_private_state():
    for case in cases():
        assert set(case).isdisjoint({'api_key','credentials','database_url'})
        for record in case['records']:
            assert record['kind'] not in {'extraction','audit_invalidation'}
            assert set(record).isdisjoint({'raw','input','messages','authorization','prompt','network'})
            if record['kind'] in {'search_run','model_run'}:
                assert record['request_id'] and record['publication_note']

def test_public_verdicts_preserve_scope_and_independence():
    reports=[next(r for r in c['records'] if r['kind']=='report') for c in cases()]
    assert [r['assessments'][0]['verdict'] for r in reports]==['REFUTED','SUPPORTED','INSUFFICIENT','SUPPORTED']
    assert reports[-1]['assessments'][0]['independent_support_groups']==2
    assert all(r['assessments'][0]['documentary_scope'] for r in reports[:2])

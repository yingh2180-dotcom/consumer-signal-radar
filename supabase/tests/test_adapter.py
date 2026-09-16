import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))


def fixture():
    raw = b'record_id,review_text\nr1,good\n'
    record = dict(record_id='r1', review_text='good', target_product_id='',
                  dataset_role='pipeline_test', data_kind='synthetic_demo', is_synthetic='true',
                  product_name='演示产品 A', final_action='KEEP', clean_text='good', reason='ok',
                  duplicate_of=None, skin='未说明', scene='未说明', features=[dict(
                      feature_id='f1', record_id='r1', category='整体', sentiment='positive',
                      evidence='good', audit_status='RULE_VALIDATED')])
    metric = dict(decision_id='d1', category='整体', sentiment='positive', mention_count=1,
                  sample_size=1, mention_rate=1, support_status='LOW_SUPPORT', evidence_ids=['f1'])
    return raw, dict(snapshot_id='s1', run_id='run1', generated_at='2026-09-15T12:00:00Z',
        context='demo', mode='rules_demo', dataset_id='dataset1', versions={'schema_version':'demo-v1'},
        summary=dict(raw_count=1,kept_count=1,filtered_count=0,pending_count=0,error_count=0,
                     feature_count=1,business_count=0), records=[record], stages=[],
        qa=dict(raw_hash=hashlib.sha256(raw).hexdigest(),business_count=0,
                model_evaluation_status='NOT_EVALUATED'), warnings=[], filter_options={},
        slices={'全部|全部|全部':dict(summary={}, metrics=[metric],record_ids=['r1'],opportunities=[])})


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('sync_adapter'), 'sync adapter must be implemented')
        import sync_adapter
        self.a = sync_adapter
        self.raw, self.snapshot = fixture()

    def test_all_layers_and_traceability(self):
        plan = self.a.build_plan(self.snapshot, self.raw)
        for table in ['datasets','pipeline_runs','raw_records','cleaning_results','features',
                      'feature_checks','decisions','evidence_bindings','qa_reports','snapshots','review_actions']:
            self.assertIn(table, plan.tables)
        self.assertEqual(plan.tables['evidence_bindings'][0]['feature_id'], 'f1')
        self.assertEqual(plan.tables['raw_records'][0]['payload']['review_text'], 'good')
        self.assertNotIn('features', plan.tables['raw_records'][0]['payload'])
        self.assertNotIn('published_demo_snapshots', plan.tables)

    def test_reject_role_contamination_and_fake_hash(self):
        for field, value in [('dataset_role','business'),('data_kind','real'),('target_product_id','real-brand')]:
            s = copy.deepcopy(self.snapshot)
            s['records'][0][field] = value
            with self.assertRaises(self.a.ValidationError): self.a.build_plan(s,self.raw)
        with self.assertRaises(self.a.ValidationError): self.a.build_plan(self.snapshot,self.raw+b'changed')

    def test_invalid_evidence_rejected(self):
        self.snapshot['records'][0]['features'][0]['evidence']='invented'
        with self.assertRaises(self.a.ValidationError): self.a.build_plan(self.snapshot,self.raw)

    def test_dry_run_never_reads_secret_or_uses_network(self):
        plan = self.a.build_plan(self.snapshot,self.raw)
        with patch('os.getenv', side_effect=AssertionError('no env in dry-run')), patch('httpx.Client',side_effect=AssertionError('no network')):
            result = self.a.sync_all_layers(plan)
        self.assertEqual(result['status'],'DRY_RUN')

    def test_sync_requires_explicit_flag_and_matching_authorized_target(self):
        plan=self.a.build_plan(self.snapshot,self.raw)
        with patch.dict('os.environ',{'SUPABASE_URL':'https://test.supabase.co','SUPABASE_SECRET_KEY':'sb_secret_hidden'}):
            with self.assertRaises(self.a.SyncError): self.a.sync_all_layers(plan,execute=True)

    def test_raw_same_hash_reuse_and_different_hash_refusal(self):
        p=self.a.build_plan(self.snapshot,self.raw)
        row=p.tables['raw_records'][0]
        self.assertEqual(self.a.immutable_action(row,dict(row)), 'reuse')
        other=dict(row,content_hash='a'*64)
        with self.assertRaises(self.a.SyncError): self.a.immutable_action(row,other)

    def test_error_text_never_exposes_remote_body_or_key(self):
        import httpx
        transport=httpx.MockTransport(lambda request:httpx.Response(401,text='sb_secret_hidden'))
        client=self.a.RestClient('https://test.supabase.co','sb_secret_hidden',transport=transport)
        with self.assertRaises(self.a.SyncError) as err: client.request('GET','/rest/v1/raw_records')
        self.assertNotIn('hidden',str(err.exception))
        self.assertNotIn('sb_secret',repr(client))

    def test_new_secret_key_not_sent_as_bearer_jwt(self):
        import httpx
        seen=[]
        def handle(request):
            seen.append(request)
            return httpx.Response(200,json=[])
        client=self.a.RestClient('https://test.supabase.co','sb_secret_hidden',transport=httpx.MockTransport(handle))
        client.request('GET','/rest/v1/raw_records')
        self.assertEqual(seen[0].headers['apikey'],'sb_secret_hidden')
        self.assertNotIn('authorization',seen[0].headers)


if __name__=='__main__': unittest.main()

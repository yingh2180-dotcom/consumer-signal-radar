import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('backend.pipeline'), 'Pipeline has not been implemented')
        from backend import pipeline
        self.p = pipeline

    def test_isolation_and_fixed_count(self):
        rows, digest = self.p.load_input()
        self.assertEqual(len(rows), 1000)
        self.assertEqual(len({r['record_id'] for r in rows}), 1000)
        for key, value in [('target_product_id', 'real-brand'), ('dataset_role', 'business_core'), ('source_platform', 'real-platform'), ('publish_time_raw', '2026-09-15')]:
            polluted = copy.deepcopy(rows)
            polluted[0][key] = value
            with self.assertRaises(ValueError):
                self.p.validate_input(polluted)

    def test_counts_evidence_duplicates_and_multiview(self):
        rows, digest = self.p.load_input()
        snap = self.p.build_snapshot(rows, digest, 'test-run', [])
        self.assertEqual(snap['summary']['raw_count'], 1000)
        self.assertEqual(snap['summary']['filtered_count'], 40)
        self.assertEqual(snap['summary']['kept_count'], 960)
        self.assertEqual(snap['summary']['feature_count'], 980)
        self.assertEqual(snap['summary']['business_count'], 0)
        self.assertEqual(len(snap['slices']), 140)
        self.assertEqual(
            [stage['name'] for stage in snap['stages']],
            ['原始资料与演示隔离', '清洗与留痕', '原创规则观点抽取', '按记录去重统计', '数据呈现组装与质量核验'],
        )
        self.assertEqual(snap['stages'][4]['artifact'], 'snapshot.json')
        self.assertEqual(snap['stages'][4]['output_count'], 1)
        self.assertTrue(all(snap['qa'][k] for k in ['counts_consistent', 'schema_valid', 'evidence_valid']))
        self.assertEqual(snap['mode'], 'rules_demo')
        self.assertEqual(snap['qa']['model_evaluation_status'], 'NOT_EVALUATED')
        self.assertEqual(snap['qa']['trend_status'], 'NO_REAL_TIMESTAMPS')
        self.assertIsNone(snap['versions']['model_identifier'])
        records = {r['record_id']: r for r in snap['records']}
        self.assertEqual(records['SYN-20260915-0981']['final_action'], 'KEEP')
        self.assertEqual(records['SYN-20260915-0981']['duplicate_of'], 'SYN-20260915-0061')
        self.assertEqual(len(records['SYN-20260915-0041']['features']), 2)
        self.assertEqual(records['SYN-20260915-0001']['review_text'], '   ')
        for r in snap['records']:
            for f in r['features']:
                self.assertIn(f['evidence'], r['review_text'])
        self.assertEqual(len({f['category'] for r in snap['records'] for f in r['features']}), 13)
        for s in snap['slices'].values():
            for metric in s['metrics']:
                self.assertLessEqual(metric['mention_count'], metric['sample_size'])
                ids = metric['evidence_ids']
                self.assertEqual(len(ids), len(set(ids)))

    def test_stable_ids_reviews_scope_and_immutable_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / 'runtime'
            public = Path(tmp) / 'public' / 'snapshot.json'
            first = self.p.run_pipeline(runtime=runtime, public_path=public)
            first_path = runtime / 'runs' / first['run_id'] / 'snapshot.json'
            before = first_path.read_bytes()
            review = {'record_id': 'SYN-20260915-0061', 'action': 'FILTER', 'note': 'test', 'dataset_id': first['dataset_id'], 'raw_hash': first['qa']['raw_hash']}
            second = self.p.run_pipeline(runtime=runtime, public_path=public, reviews=[review])
            self.assertNotEqual(first['run_id'], second['run_id'])
            self.assertEqual(first_path.read_bytes(), before)
            self.assertEqual(second['summary']['kept_count'], 959)
            wrong = dict(review, dataset_id='different-dataset')
            third = self.p.build_snapshot(*self.p.load_input(), 'third', [wrong])
            self.assertEqual(third['summary']['kept_count'], 960)
            a = first['records'][70]['features'][0]['feature_id']
            self.assertEqual(a, second['records'][70]['features'][0]['feature_id'])
            for name in ['raw.json', 'cleaned.json', 'features.json', 'metrics.json', 'decisions.json', 'qa.json']:
                self.assertTrue((first_path.parent / name).is_file())

    def test_metrics_count_unique_records_not_labels(self):
        from backend.metrics import build_slice
        record = {'record_id': 'one', 'product_name': '演示产品 A', 'final_action': 'KEEP', 'features': [
            {'feature_id': 'f1', 'record_id': 'one', 'category': '包装', 'sentiment': 'negative', 'evidence': 'a'},
            {'feature_id': 'f2', 'record_id': 'one', 'category': '包装', 'sentiment': 'negative', 'evidence': 'b'}]}
        metric = build_slice([record], '全部|全部|全部')['metrics'][0]
        self.assertEqual(metric['mention_count'], 1)
        self.assertEqual(metric['mention_rate'], 1)
        self.assertEqual(metric['support_status'], 'LOW_SUPPORT')
        self.assertEqual(len(metric['evidence_ids']), 1)

    def test_unknown_text_has_no_invented_feature(self):
        from backend.extraction import extract
        self.assertEqual(extract('unfamiliar', '一段不含演示规则的文字'), [])

    def test_schema_rejects_pollution_invalid_enums_and_broken_lineage(self):
        snap = self.p.build_snapshot(*self.p.load_input(), 'schema-test', [])
        mutations = [
            lambda s: s.update(context='business'),
            lambda s: s.update(mode='ai'),
            lambda s: s['records'][60]['features'][0].update(category='编造分类'),
            lambda s: s['records'][60]['features'][0].update(sentiment='unknown'),
            lambda s: s['records'][60]['features'][0].update(evidence='不存在的证据'),
            lambda s: s['records'][60].update(clean_text='无匹配证据'),
            lambda s: s['records'][61]['features'][0].update(feature_id=s['records'][60]['features'][0]['feature_id']),
            lambda s: s['records'][60].update(dataset_role='business_core'),
            lambda s: s['slices']['全部|全部|全部']['metrics'][0].update(mention_count=999),
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutations.index(mutation)):
                tampered = copy.deepcopy(snap)
                mutation(tampered)
                with self.assertRaises(ValueError):
                    self.p.validate_snapshot(tampered)


if __name__ == '__main__':
    unittest.main()

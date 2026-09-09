import os
import tempfile
import unittest
from unittest.mock import patch
from . import engine


def rows(texts):
    return [dict(id=str(i),text=t,brand='未指明',product='未指明',date='',platform='测试',data_kind='工程测试') for i,t in enumerate(texts)]


class EngineTests(unittest.TestCase):
    def test_templates_not_independent_evidence(self):
        data=rows([f'上脸刺激。（合成场景 {i}）' for i in range(10)])
        result=engine.analyze_reviews(data)
        self.assertEqual(result['quality']['unique_evidence_count'],1)
        self.assertEqual(result['cards'],[])

    def test_multiaspect_and_unknown_brand(self):
        result=engine.analyze_reviews(rows(['吸收快，但是会搓泥，希望改善叠涂。']))
        r=result['reviews'][0]
        self.assertEqual(r['brand'],'未指明')
        self.assertEqual(r['sentiment'],'混合')
        self.assertTrue(all(f['excerpt'] in r['text'] for f in r['feedbacks']))

    def test_evidence_and_missing_dates(self):
        source=rows(['有些刺激想停用','脸上泛红了','晚上用了刺痛'])
        r=engine.analyze_reviews(source)
        card=r['cards'][0]
        self.assertIsNone(card['growth'])
        self.assertEqual(len(card['evidence']),3)
        self.assertEqual(len({engine.normalized_text(e['text']) for e in card['evidence']}),3)
        self.assertTrue(all(e['sentiment'] in ('负面','混合') for e in card['evidence']))
        self.assertIn('3 条为负面或混合反馈',card['observed_fact'])
        self.assertIn('尚未证明',card['hypothesis'])
        self.assertIn('待验证假设',card['boundary'])
        self.assertFalse(card['reviewed'])

    def test_provenance_declares_data_kind_without_claiming_verification(self):
        source=rows(['有些刺激想停用','脸上泛红了','晚上用了刺痛'])
        source[0]['data_kind']='合成演示数据'
        result=engine.analyze_reviews(source)
        self.assertEqual(result['provenance']['data_kinds'],{'合成演示数据':1,'工程测试':2})
        self.assertIn('未独立核验',result['provenance']['source_status'])

    def test_checkpoint_no_reprocessing(self):
        cp={};source=rows(['好用']*10)
        engine.analyze_reviews(source,checkpoint=cp)
        with patch.object(engine,'extract_offline',side_effect=AssertionError('reprocessed')):
            engine.analyze_reviews(source,checkpoint=cp)
        with self.assertRaises(ValueError):
            engine.analyze_reviews(rows(['另一批']),checkpoint=cp)

    def test_fake_excerpt_rejected(self):
        f=dict(topic='刺激与耐受',dimension='肤感',sentiment='负面',severity=2,excerpt='编造证据',scene='未提及',need='未明确表达',ingredients=[])
        with self.assertRaises(ValueError):engine._validate_feedbacks({'feedbacks':[f]},'真实评论')

    def test_paid_disabled_no_network(self):
        with patch.dict(os.environ,{'RADAR_API_KEY':'unit-test','RADAR_BASE_URL':'https://example.invalid','RADAR_PAID_ENABLED':'false'}),patch('urllib.request.urlopen',side_effect=AssertionError('network')):
            with self.assertRaises(ValueError):engine._request('/chat/completions',{'model':'qwen3.5-plus'})

    def test_cumulative_budget(self):
        with tempfile.TemporaryDirectory() as temp,patch.dict(os.environ,{'RADAR_DATA_DIR':temp,'RADAR_BUDGET_DB_PATH':os.path.join(temp,'budget.sqlite3'),'RADAR_BUDGET_CNY':'0.03'}):
            payload={'model':'qwen3.5-plus','max_tokens':4096,'messages':[]}
            engine._reserve_budget('/chat/completions',payload)
            with self.assertRaises(ValueError):engine._reserve_budget('/chat/completions',payload)

    def test_missing_labels_not_evaluated(self):
        r=engine.analyze_reviews(rows(['好用']))
        with self.assertRaises(ValueError):engine.evaluate_reviews(r['reviews'],[{'id':'0'}])

if __name__=='__main__':unittest.main()

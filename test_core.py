import os
import unittest
from unittest.mock import patch
from pathlib import Path
import pandas as pd
from core import normalize,extract_rule,analyze,opportunities,evaluate,read_csv,extract_llm


class PipelineTests(unittest.TestCase):
    def test_negation_and_unattributed_brand(self):
        self.assertEqual(extract_rule('不刺激，没有泛红，也不搓泥')['sentiment'],'正面')
        self.assertEqual(extract_rule('上脸烫但不是过敏，希望更温和')['topic'],'刺激与耐受')
        df,_=normalize(pd.DataFrame({'text':['某国货早C晚A太刺激']}))
        self.assertEqual(df.brand.iloc[0],'未指明')

    def test_quality_and_id_guard(self):
        df,q=normalize(pd.DataFrame({'text':['',' 好用 ','好用'],'date':['','bad','bad']}))
        self.assertEqual(len(df),1)
        self.assertEqual(q['removed'],2)
        self.assertEqual(q['invalid_dates'],1)
        with self.assertRaises(ValueError):normalize(pd.DataFrame({'text':['a','b'],'id':['x','x']}))
        with self.assertRaises(ValueError):normalize(pd.DataFrame({'other':['a']}))

    def test_small_and_evidence_threshold(self):
        df,_=normalize(pd.DataFrame({'text':['刺痛得停用','泵头坏了']}))
        result,_=analyze(df)
        self.assertEqual(opportunities(result),[])
        df,_=normalize(pd.DataFrame({'text':['单个未知评论']}))
        self.assertEqual(len(analyze(df)[0]),1)

    def test_evidence_and_missing_dates(self):
        df,_=normalize(pd.DataFrame({'text':['刺激啊','明显刺激','真的刺激'],'brand':['未指明']*3}))
        result,_=analyze(df,k=1)
        cards=opportunities(result)
        self.assertEqual(len(cards),1)
        self.assertIsNone(cards[0]['score'])
        self.assertEqual(len(cards[0]['evidence']),3)
        lookup=dict(zip(df.id,df.text))
        self.assertTrue(all(lookup[e['id']]==e['text'] for e in cards[0]['evidence']))

    def test_trend_equal_windows(self):
        raw=pd.DataFrame({'text':[f'刺激{i}' for i in range(14)],'date':pd.date_range('2026-08-01',periods=14).astype(str)})
        df,_=normalize(raw); result,_=analyze(df,k=1)
        c=opportunities(result)[0]
        self.assertAlmostEqual(c['growth'],0)
        self.assertAlmostEqual(c['score'],c['priority'])
        result.loc[result.parsed_date<pd.Timestamp('2026-08-08'),'cluster_name']='其他'
        recent=next(c for c in opportunities(result) if c['topic']!='其他')
        self.assertIsNone(recent['score'])

    def test_evaluation_guards_and_real_mismatch(self):
        df,_=normalize(pd.DataFrame({'text':['泵头坏了','温和好用']}));pred,_=analyze(df)
        gold=pred[['id','feedback_type','dimension','sentiment','severity']].copy()
        gold.loc[0,'sentiment']='正面'
        scores,n=evaluate(pred,gold)
        self.assertEqual(n,2);self.assertLess(scores['sentiment'],1)
        gold.loc[0,'dimension']=''
        with self.assertRaises(ValueError):evaluate(pred,gold)

    def test_llm_rejects_mismatched_ids(self):
        df,_=normalize(pd.DataFrame({'text':['测试']}))
        fake={'choices':[{'message':{'content':'{"reviews": []}'}}]}
        with patch.dict(os.environ,{'RADAR_MODEL':'test'}),patch('core.api_request',return_value=fake):
            with self.assertRaises(ValueError):extract_llm(df)

    def test_synthetic_full_pipeline(self):
        raw=(Path(__file__).parent/'data/synthetic_reviews.csv').read_bytes()
        df,_=normalize(read_csv(raw));result,method=analyze(df)
        cards=opportunities(result)
        self.assertEqual(len(result),1000)
        self.assertTrue(cards)
        self.assertTrue(all(len({e['text'] for e in c['evidence']})>=3 for c in cards))
        self.assertIn('非语义',method)


if __name__=='__main__':unittest.main(verbosity=2)

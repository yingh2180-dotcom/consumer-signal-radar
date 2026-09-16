"""Unique-record metrics and explicitly deterministic research candidates."""
from collections import defaultdict
import hashlib


def summary(records):
    counts = {action: len({r['record_id'] for r in records if r['final_action'] == action}) for action in ('KEEP', 'FILTER', 'PENDING', 'ERROR')}
    return {'raw_count': len({r['record_id'] for r in records}),
            'kept_count': counts['KEEP'], 'filtered_count': counts['FILTER'],
            'pending_count': counts['PENDING'], 'error_count': counts['ERROR'],
            'feature_count': sum(len(r['features']) for r in records), 'business_count': 0}


def build_slice(records, key):
    kept = [r for r in records if r['final_action'] == 'KEEP']
    grouped = defaultdict(dict)
    for record in kept:
        for f in record['features']:
            grouped[(f['category'], f['sentiment'])].setdefault(record['record_id'], f)
    metrics, opportunities = [], []
    for (category, sentiment), by_record in sorted(grouped.items()):
        evidence = list(by_record.values())[:5]
        status = 'LOW_SUPPORT' if len(by_record) < 3 else ('SUPPORTED' if len(evidence) >= 3 else 'INSUFFICIENT_EVIDENCE')
        decision_id = 'D-' + hashlib.sha256(f'{key}|{category}|{sentiment}'.encode()).hexdigest()[:20]
        metric = {'decision_id': decision_id, 'product': key.split('|')[0], 'category': category,
                  'sentiment': sentiment, 'mention_count': len(by_record), 'sample_size': len(kept),
                  'mention_rate': len(by_record) / len(kept) if kept else 0,
                  'support_status': status, 'evidence_ids': [f['feature_id'] for f in evidence]}
        metrics.append(metric)
        if sentiment == 'negative' and status == 'SUPPORTED':
            opportunities.append({'decision_id': decision_id, 'title': f'{category}：待验证研究候选',
                'fact': f'当前演示切片 {len(kept)} 条保留记录中，{len(by_record)} 条提及{category}负向观点。',
                'pattern': f'按固定类别规则汇总的{category}负向提及；不是聚类结果。',
                'hypothesis': f'真实目标用户可能存在与{category}相关的未满足需求；合成样本不能证实该假设。',
                'recommendation': f'把{category}列为访谈研究候选，暂不据此决定产品改动。',
                'validation_action': '另行获取合法真实业务样本，人工核查证据并开展用户访谈。',
                'evidence_ids': metric['evidence_ids'], 'method': 'deterministic_template'})
    return {'summary': summary(records), 'metrics': metrics,
            'record_ids': [r['record_id'] for r in records], 'opportunities': opportunities}

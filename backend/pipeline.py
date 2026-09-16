"""Five reproducible demo layers. Never imports generator labels or credentials."""
import csv
import hashlib
import io
import itertools
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .extraction import RULES, context, extract
from .metrics import build_slice, summary

BASE = Path(__file__).resolve().parents[1]
INPUT = BASE / 'data' / 'synthetic_reviews.csv'
RUNTIME = BASE / 'runtime'
PUBLIC = BASE / 'frontend' / 'public' / 'snapshot.json'
DATASET_ID = 'SYN-20260915-v1'
VERSIONS = {'app_version': '2.0', 'schema_version': 'demo-v1', 'clean_version': 'v1', 'prompt_version': None,
            'model_identifier': None, 'metric_version': 'v1', 'generator_version': 'v1'}
FILTERS = {'products': ['全部', '演示产品 A', '演示产品 B', '演示产品 C'],
           'skins': ['全部', '干皮', '油皮', '混合皮', '未说明'],
           'scenes': ['全部', '早间', '晚间', '出差', '日常', '初次尝试', '未说明']}


def now():
    return datetime.now(timezone.utc).isoformat()


def validate_input(rows):
    if len(rows) != 1000 or len({r.get('record_id') for r in rows}) != 1000:
        raise ValueError('Demo requires exactly 1000 unique records')
    for r in rows:
        required = {'data_kind': 'synthetic_demo', 'dataset_role': 'pipeline_test',
                    'source_origin': 'synthetic_generated', 'collection_method': 'synthetic_demo',
                    'is_synthetic': 'true', 'generator_version': 'v1', 'collection_batch_id': DATASET_ID}
        if any(r.get(k) != v for k, v in required.items()):
            raise ValueError('Demo isolation violation')
        if any(r.get(k) for k in ['target_product_id', 'source_platform', 'publish_time_raw', 'collection_time', 'source_url', 'sampling_stratum']):
            raise ValueError('Demo cannot contain real product, platform, source or timeline')
        if r.get('product_name') not in FILTERS['products'][1:] or not isinstance(r.get('review_text'), str):
            raise ValueError('Invalid demo record schema')
        if not r['record_id'].startswith('SYN-20260915-'):
            raise ValueError('Invalid record identity')


def load_input():
    content = INPUT.read_bytes()
    rows = list(csv.DictReader(io.StringIO(content.decode('utf-8-sig'))))
    validate_input(rows)
    return rows, hashlib.sha256(content).hexdigest()


def build_snapshot(rows, raw_hash, run_id, reviews):
    started = time.perf_counter()
    stages = []
    def stage(layer, name, incoming, outgoing, artifact, began):
        stages.append({'layer': layer, 'name': name, 'input_count': incoming, 'output_count': outgoing,
                       'status': 'COMPLETED', 'mode': 'rules_demo',
                       'duration_ms': round((time.perf_counter() - began) * 1000, 3), 'artifact': artifact})
    validate_input(rows)
    stage(1, '原始资料与演示隔离', len(rows), len(rows), 'raw.json', started)
    began = time.perf_counter()
    applicable = {r['record_id']: r for r in reviews if r.get('dataset_id') == DATASET_ID and r.get('raw_hash') == raw_hash and r.get('action') in ('KEEP', 'FILTER')}
    records, seen = [], {}
    for raw in rows:
        text = raw['review_text']
        cleaned = ' '.join(text.split())
        reason = 'RULE_EMPTY' if not cleaned else ('RULE_TEMPLATE' if cleaned == '此用户未填写具体评价' else 'RULE_KEEP')
        action = 'FILTER' if reason != 'RULE_KEEP' else 'KEEP'
        review = applicable.get(raw['record_id'])
        if review:
            action, reason = review['action'], 'HUMAN_REVIEW'
        skin, scene = context(text)
        duplicate = seen.get(text)
        seen.setdefault(text, raw['record_id'])
        records.append({**raw, 'clean_text': cleaned, 'final_action': action, 'reason': reason,
                        'duplicate_of': duplicate, 'skin': skin, 'scene': scene, 'features': []})
    stage(2, '清洗与留痕', len(rows), len(records), 'cleaned.json', began)
    began = time.perf_counter()
    for r in records:
        if r['final_action'] == 'KEEP':
            r['features'] = extract(r['record_id'], r['review_text'])
            if not r['features'] and r['reason'] != 'HUMAN_REVIEW':
                r['reason'] = 'NO_FEATURE'
        r['processing_status'] = 'FEATURE_EXTRACTED' if r['features'] else ('NO_FEATURE' if r['final_action'] == 'KEEP' else 'FILTERED')
    features = [f for r in records for f in r['features']]
    stage(3, '原创规则观点抽取', sum(r['final_action'] == 'KEEP' for r in records), len(features), 'features.json', began)
    began = time.perf_counter()
    slices = {}
    for product, skin, scene in itertools.product(*FILTERS.values()):
        chosen = [r for r in records if (product == '全部' or product == r['product_name']) and (skin == '全部' or skin == r['skin']) and (scene == '全部' or scene == r['scene'])]
        key = '|'.join((product, skin, scene))
        slices[key] = build_slice(chosen, key)
    stage(4, '按记录去重统计', len(features), sum(len(s['metrics']) for s in slices.values()), 'metrics.json', began)
    began = time.perf_counter()
    total = summary(records)
    qa = {'counts_consistent': total['raw_count'] == sum(total[k] for k in ['kept_count', 'filtered_count', 'pending_count', 'error_count']),
          'evidence_valid': all(f['evidence'] and f['evidence'] in r['review_text'] for r in records for f in r['features']),
          'schema_valid': False, 'raw_hash': raw_hash, 'business_count': 0,
          'model_evaluation_status': 'NOT_EVALUATED', 'trend_status': 'NO_REAL_TIMESTAMPS', 'clustering_status': 'NOT_ENABLED'}
    stage(5, '数据呈现组装与质量核验', sum(len(s['metrics']) for s in slices.values()), 1, 'snapshot.json', began)
    snap = {'snapshot_id': 'SNAP-' + run_id, 'run_id': run_id, 'generated_at': now(),
            'context': 'demo', 'mode': 'rules_demo', 'dataset_id': DATASET_ID,
            'versions': VERSIONS, 'summary': total, 'filter_options': FILTERS, 'records': records,
            'stages': stages, 'qa': qa,
            'warnings': ['仅为1000条原创合成样本的流程演示，真实业务样本为0。', 'rules_demo / demo-v1；未启用AI、人工Gold评测、聚类或真实时间趋势。', '规则词句针对演示输入设计；通过工程检查不代表真实模型准确率。', '研究候选来自固定模板，不能直接用于业务决策。'],
            'slices': slices}
    qa['schema_valid'] = validate_snapshot(snap)
    return snap


def validate_snapshot(snap):
    required = {'snapshot_id', 'run_id', 'generated_at', 'context', 'mode', 'dataset_id', 'versions', 'summary', 'filter_options', 'records', 'stages', 'qa', 'warnings', 'slices'}
    if not required <= snap.keys() or snap['context'] != 'demo' or snap['mode'] != 'rules_demo' or snap['dataset_id'] != DATASET_ID:
        raise ValueError('Snapshot context/schema mismatch')
    if snap['versions'] != VERSIONS or snap['filter_options'] != FILTERS:
        raise ValueError('Unsupported snapshot version/filter schema')
    validate_input(snap['records'])
    ids = {r['record_id'] for r in snap['records']}
    records = {r['record_id']: r for r in snap['records']}
    features = {f['feature_id']: f for r in snap['records'] for f in r['features']}
    if len(ids) != 1000 or len(features) != snap['summary']['feature_count'] or snap['summary'] != summary(snap['records']):
        raise ValueError('Snapshot identity/schema mismatch')
    for r in snap['records']:
        if r['final_action'] not in ('KEEP', 'FILTER', 'PENDING', 'ERROR'):
            raise ValueError('Invalid action')
        if r['skin'] not in FILTERS['skins'][1:] or r['scene'] not in FILTERS['scenes'][1:]:
            raise ValueError('Invalid record context')
        if r['duplicate_of'] is not None and (r['duplicate_of'] not in ids or records[r['duplicate_of']]['review_text'] != r['review_text'] or r['duplicate_of'] == r['record_id']):
            raise ValueError('Invalid duplicate lineage')
        if r['final_action'] != 'KEEP' and r['features']:
            raise ValueError('Excluded record has metric features')
        for f in r['features']:
            if set(f) != {'feature_id', 'record_id', 'category', 'sentiment', 'evidence', 'audit_status'}:
                raise ValueError('Invalid feature structure')
            if f['category'] not in RULES or f['sentiment'] not in ('positive', 'negative', 'neutral') or f['audit_status'] != 'RULE_VALIDATED':
                raise ValueError('Invalid feature enum')
            if f['record_id'] != r['record_id'] or not f['evidence'] or f['evidence'] not in r['review_text'] or f['evidence'] not in r['clean_text']:
                raise ValueError('Invalid evidence')
    expected_keys = {'|'.join(combo) for combo in itertools.product(*FILTERS.values())}
    if set(snap['slices']) != expected_keys:
        raise ValueError('Incomplete or unsupported slice schema')
    for key, s in snap['slices'].items():
        product, skin, scene = key.split('|')
        chosen = [r for r in snap['records'] if (product == '全部' or product == r['product_name']) and (skin == '全部' or skin == r['skin']) and (scene == '全部' or scene == r['scene'])]
        if s['record_ids'] != [r['record_id'] for r in chosen] or s['summary'] != summary(chosen):
            raise ValueError('Invalid slice membership or summary')
        kept = [r for r in chosen if r['final_action'] == 'KEEP']
        for m in s['metrics']:
            if m['category'] not in RULES or m['sentiment'] not in ('positive', 'negative', 'neutral') or m['product'] != product:
                raise ValueError('Invalid metric enum')
            mentioned = {r['record_id'] for r in kept if any(f['category'] == m['category'] and f['sentiment'] == m['sentiment'] for f in r['features'])}
            if m['sample_size'] != len(kept) or m['mention_count'] != len(mentioned) or m['mention_rate'] != (len(mentioned) / len(kept) if kept else 0):
                raise ValueError('Invalid metric')
            if any(fid not in features for fid in m['evidence_ids']):
                raise ValueError('Broken metric lineage')
            evidence_records = [features[fid]['record_id'] for fid in m['evidence_ids']]
            if len(evidence_records) != len(set(evidence_records)) or len(evidence_records) > 5 or not set(evidence_records) <= mentioned:
                raise ValueError('Invalid metric evidence records')
            if any(features[fid]['category'] != m['category'] or features[fid]['sentiment'] != m['sentiment'] for fid in m['evidence_ids']):
                raise ValueError('Invalid metric evidence topic')
            support = 'LOW_SUPPORT' if len(mentioned) < 3 else ('SUPPORTED' if len(evidence_records) >= 3 else 'INSUFFICIENT_EVIDENCE')
            if m['support_status'] != support:
                raise ValueError('Invalid support status')
        supported = {m['decision_id']: m for m in s['metrics'] if m['sentiment'] == 'negative' and m['support_status'] == 'SUPPORTED'}
        for decision in s['opportunities']:
            if decision['decision_id'] not in supported or decision['method'] != 'deterministic_template' or decision['evidence_ids'] != supported[decision['decision_id']]['evidence_ids']:
                raise ValueError('Unsupported research candidate')
    if [s['layer'] for s in snap['stages']] != [1, 2, 3, 4, 5] or any(s['mode'] != 'rules_demo' or s['status'] != 'COMPLETED' for s in snap['stages']):
        raise ValueError('Invalid stage schema')
    for field, value in {'business_count': 0, 'model_evaluation_status': 'NOT_EVALUATED', 'trend_status': 'NO_REAL_TIMESTAMPS', 'clustering_status': 'NOT_ENABLED'}.items():
        if snap['qa'].get(field) != value:
            raise ValueError('Invalid QA scope')
    if not snap['qa']['counts_consistent'] or not snap['qa']['evidence_valid']:
        raise ValueError('Snapshot QA failed')
    return True


def read_reviews(runtime=RUNTIME):
    path = Path(runtime) / 'reviews.jsonl'
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line] if path.exists() else []


def write_json(path, value, exclusive=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x' if exclusive else 'w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, separators=(',', ':'))


def run_pipeline(runtime=RUNTIME, public_path=PUBLIC, reviews=None, run_id=None):
    runtime, public_path = Path(runtime), Path(public_path)
    rows, digest = load_input()
    reviews = read_reviews(runtime) if reviews is None else reviews
    run_id = run_id or datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:10]
    snapshot = build_snapshot(rows, digest, run_id, reviews)
    folder = runtime / 'runs' / run_id
    folder.mkdir(parents=True, exist_ok=False)
    artifacts = {'raw.json': rows, 'cleaned.json': snapshot['records'],
                 'features.json': [f for r in snapshot['records'] for f in r['features']],
                 'metrics.json': {k: s['metrics'] for k, s in snapshot['slices'].items()},
                 'decisions.json': {k: s['opportunities'] for k, s in snapshot['slices'].items()},
                 'qa.json': snapshot['qa'], 'snapshot.json': snapshot,
                 'reviews.json': [r for r in reviews if r.get('dataset_id') == DATASET_ID and r.get('raw_hash') == digest]}
    for name, value in artifacts.items():
        write_json(folder / name, value, exclusive=True)
    manifest = {'run_id': run_id, 'dataset_id': DATASET_ID, 'raw_hash': digest,
                'mode': 'rules_demo', 'versions': VERSIONS, 'status': 'COMPLETED',
                'generated_at': snapshot['generated_at'], 'artifacts': {name: hashlib.sha256((folder / name).read_bytes()).hexdigest() for name in artifacts}}
    write_json(folder / 'manifest.json', manifest, exclusive=True)
    # Pointer and publish copy can change; per-run archives are never rewritten.
    for target, value in [(runtime / 'latest.json', {'run_id': run_id}), (public_path, snapshot)]:
        temp = target.with_name(target.name + '.' + uuid.uuid4().hex + '.tmp')
        write_json(temp, value)
        os.replace(temp, target)
    return snapshot


if __name__ == '__main__':
    result = run_pipeline()
    print(json.dumps({'run_id': result['run_id'], 'summary': result['summary'], 'qa': result['qa']}, ensure_ascii=False))

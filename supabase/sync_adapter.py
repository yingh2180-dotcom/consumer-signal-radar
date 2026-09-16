"""Local-only by default. No dotenv loading, automatic login, or cloud discovery."""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass, field
import hashlib
import io
import json
import os
from pathlib import Path
import re
from urllib.parse import urlparse, quote

import httpx


class ValidationError(ValueError): pass
class SyncError(RuntimeError): pass


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def safe_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,180}', value):
        raise ValidationError('Invalid identifier')
    return value


def ensure(condition, reason):
    if not condition: raise ValidationError(reason)


def reject_secrets(value):
    if isinstance(value, dict):
        for key, child in value.items():
            ensure(not re.search(r'secret|password|api_key|authorization|access_token|gold|expected',key,re.I), 'Private configuration/reference field rejected')
            reject_secrets(child)
    elif isinstance(value, list):
        for child in value: reject_secrets(child)
    elif isinstance(value, str):
        ensure('sb_secret_' not in value and not re.search(r'eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+', value), 'Credential-like content rejected')


@dataclass
class SyncPlan:
    tables: dict
    files: list = field(repr=False)
    snapshot: dict = field(repr=False)

    def summary(self):
        return {'status':'DRY_RUN', 'connected':False, 'context':'demo',
                'run_id':self.snapshot['run_id'], 'snapshot_id':self.snapshot['snapshot_id'],
                'rows':{key:len(rows) for key,rows in self.tables.items()},
                'files':[{'bucket':f['bucket'],'path':f['path'],'bytes':len(f['content']),
                          'sha256':digest(f['content'])} for f in self.files],
                'public_write':False, 'gold_upload':False}


def build_plan(snapshot: dict, raw_csv: bytes, *, reviews=None, artifacts=None) -> SyncPlan:
    """Build complete L1-L5 payloads and validate locally. Never reads environment/network."""
    reject_secrets(snapshot)
    ensure(snapshot.get('context')=='demo' and snapshot.get('mode')=='rules_demo', 'Only rules_demo context allowed')
    ensure(snapshot['summary'].get('business_count')==0 and snapshot['qa'].get('business_count')==0, 'Business count must be zero')
    raw_hash=digest(raw_csv)
    ensure(snapshot['qa'].get('raw_hash')==raw_hash, 'Raw CSV hash differs from snapshot')
    dataset_id=safe_id(snapshot['dataset_id']); run_id=safe_id(snapshot['run_id']); snapshot_id=safe_id(snapshot['snapshot_id'])
    raw_rows=list(csv.DictReader(io.StringIO(raw_csv.decode('utf-8-sig'))))
    raw_by_id={r['record_id']:r for r in raw_rows}
    records=snapshot['records']
    ensure(len(raw_by_id)==len(raw_rows)==len(records), 'Duplicate or missing Raw records')
    ensure(set(raw_by_id)=={r['record_id'] for r in records}, 'Snapshot identifiers differ from Raw')
    tables={name:[] for name in ['datasets','pipeline_runs','raw_records','cleaning_results','features',
        'feature_checks','decisions','evidence_bindings','review_actions','qa_reports','snapshots']}
    tables['datasets']=[dict(dataset_id=dataset_id,raw_hash=raw_hash,context='demo',dataset_role='pipeline_test',data_kind='synthetic_demo')]
    tables['pipeline_runs']=[dict(run_id=run_id,dataset_id=dataset_id,mode='rules_demo',
        generated_at=snapshot['generated_at'],versions=snapshot['versions'],stages=snapshot['stages'])]
    counts={action:0 for action in ['KEEP','FILTER','PENDING','ERROR']}
    feature_ids=set()
    for record in records:
        rid=safe_id(record['record_id'])
        ensure(record.get('dataset_role')=='pipeline_test' and record.get('data_kind')=='synthetic_demo', 'Only synthetic pipeline_test rows allowed')
        ensure(record.get('target_product_id') in ('',None) and str(record.get('is_synthetic')).lower()=='true','Real product binding or synthetic flag invalid')
        raw=raw_by_id[rid]
        ensure(all(record.get(key)==value for key,value in raw.items()), 'Snapshot changed an original Raw field')
        action=record.get('final_action'); ensure(action in counts,'Invalid cleaning action'); counts[action]+=1
        tables['raw_records'].append(dict(dataset_id=dataset_id,record_id=rid,content_hash=digest(canonical(raw)),payload=raw))
        tables['cleaning_results'].append(dict(run_id=run_id,dataset_id=dataset_id,record_id=rid,
            final_action=action,payload={k:record.get(k) for k in ['clean_text','reason','duplicate_of','skin','scene','processing_status']}))
        for feature in record['features']:
            fid=safe_id(feature['feature_id'])
            ensure(fid not in feature_ids and feature['record_id']==rid,'Duplicate feature or incorrect record binding')
            ensure(bool(feature['evidence']) and feature['evidence'] in record['review_text'],'Feature evidence is not a Raw substring')
            ensure(feature['sentiment'] in ('positive','negative','neutral') and feature['audit_status']=='RULE_VALIDATED','Invalid feature status')
            feature_ids.add(fid)
            tables['features'].append(dict(run_id=run_id,feature_id=fid,record_id=rid,dataset_id=dataset_id,payload=feature))
            tables['feature_checks'].append(dict(run_id=run_id,feature_id=fid,status='RULE_VALIDATED',payload={'evidence_valid':True}))
    summary=snapshot['summary']
    ensure(summary['raw_count']==len(raw_rows) and summary['feature_count']==len(feature_ids),'Raw/feature counts inconsistent')
    ensure(all(summary[key]==counts[action] for key,action in [('kept_count','KEEP'),('filtered_count','FILTER'),('pending_count','PENDING'),('error_count','ERROR')]),'Cleaning counts inconsistent')
    for slice_key, slice_data in snapshot['slices'].items():
        opportunities={o['decision_id']:o for o in slice_data['opportunities']}
        for metric in slice_data['metrics']:
            did=safe_id(metric['decision_id'])
            ensure(all(fid in feature_ids for fid in metric['evidence_ids']), 'Decision has missing feature evidence')
            tables['decisions'].append(dict(run_id=run_id,slice_key=slice_key,decision_id=did,
                payload={'metric':metric,'opportunity':opportunities.get(did)}))
            for fid in dict.fromkeys(metric['evidence_ids']):
                tables['evidence_bindings'].append(dict(run_id=run_id,slice_key=slice_key,decision_id=did,feature_id=fid))
    for review in reviews or []:
        reject_secrets(review)
        ensure(review.get('record_id') in raw_by_id and review.get('action') in ('KEEP','FILTER'), 'Invalid review record')
        tables['review_actions'].append(dict(run_id=run_id,review_id=digest(canonical(review)),record_id=review['record_id'],payload=review))
    tables['qa_reports']=[dict(run_id=run_id,payload=snapshot['qa'])]
    tables['snapshots']=[dict(snapshot_id=snapshot_id,run_id=run_id,content_hash=digest(canonical(snapshot)),payload=snapshot)]
    files=[dict(bucket='demo-raw',path=f'{dataset_id}/{raw_hash}/synthetic_reviews.csv',content=raw_csv)]
    allowed={'raw.json','cleaned.json','features.json','metrics.json','decisions.json','qa.json','manifest.json','reviews.json','snapshot.json'}
    for name, content in (artifacts or {}).items():
        ensure(name in allowed,'Artifact filename is outside allowlist')
        reject_secrets(json.loads(content))
        files.append(dict(bucket='demo-artifacts',path=f'{run_id}/{digest(content)}/{name}',content=content))
    if not any(f['path'].endswith('/snapshot.json') for f in files):
        content=canonical(snapshot)
        files.append(dict(bucket='demo-artifacts',path=f'{run_id}/{digest(content)}/snapshot.json',content=content))
    return SyncPlan(tables,files,snapshot)


def immutable_action(row, existing):
    if existing is None: return 'insert'
    field='raw_hash' if 'raw_hash' in row else 'content_hash'
    if row.get(field)!=existing.get(field): raise SyncError('Immutable content conflict; create a new dataset/run/snapshot identifier')
    return 'reuse'


class RestClient:
    def __init__(self,url,secret,*,transport=None):
        self._client=httpx.Client(base_url=url,headers={'apikey':secret},timeout=60,
                                  follow_redirects=False,transport=transport)

    def close(self): self._client.close()

    def request(self,method,path,**kwargs):
        try:
            response=self._client.request(method,path,**kwargs)
        except httpx.HTTPError:
            raise SyncError('Cloud request failed; inspect connectivity locally (details suppressed)') from None
        if response.is_error:
            raise SyncError(f'Cloud request rejected (HTTP {response.status_code}); response details suppressed')
        return response

    def immutable_rows(self,table,rows,key_fields,schema='demo_private'):
        headers={'Accept-Profile':schema,'Content-Profile':schema}
        for row in rows:
            params={key:f'eq.{row[key]}' for key in key_fields}
            existing=self.request('GET',f'/rest/v1/{table}',headers=headers,params=params).json()
            if immutable_action(row,existing[0] if existing else None)=='reuse': continue
            # Never upsert Raw. A concurrent insertion may fail; a retry then rechecks the hash.
            self.request('POST',f'/rest/v1/{table}',headers=headers,json=row)

    def upsert(self,table,rows,keys):
        for start in range(0,len(rows),200):
            self.request('POST',f'/rest/v1/{table}',params={'on_conflict':','.join(keys)},
                headers={'Content-Profile':'demo_private','Prefer':'resolution=merge-duplicates'},json=rows[start:start+200])

    def upload_immutable(self,item):
        path='/storage/v1/object/'+quote(item['bucket']+'/'+item['path'],safe='/')
        # Download only this exact content-addressed key. No bucket listing, no overwrite.
        try:
            response=self._client.get(path)
        except httpx.HTTPError:
            raise SyncError('Storage read failed; details suppressed') from None
        if response.status_code==200:
            if digest(response.content)!=digest(item['content']): raise SyncError('Raw/artifact object hash conflict')
            return
        if response.status_code not in (400,404):
            raise SyncError(f'Storage lookup rejected (HTTP {response.status_code})')
        self.request('POST',path,headers={'x-upsert':'false','Content-Type':'application/octet-stream'},content=item['content'])


KEYS={'pipeline_runs':['run_id'],'cleaning_results':['run_id','record_id'],
      'features':['run_id','feature_id'],'feature_checks':['run_id','feature_id'],
      'decisions':['run_id','slice_key','decision_id'],
      'evidence_bindings':['run_id','slice_key','decision_id','feature_id'],
      'review_actions':['run_id','review_id'],'qa_reports':['run_id']}


def sync_all_layers(plan,*,execute=False,authorized_url=None,approve_publication=False,transport=None):
    if not execute: return plan.summary()
    url=os.getenv('SUPABASE_URL','').rstrip('/')
    parsed=urlparse(url)
    if not authorized_url or authorized_url.rstrip('/')!=url:
        raise SyncError('Cloud sync disabled: exact target authorization required')
    if parsed.scheme!='https' or not re.fullmatch(r'[a-z0-9-]+\.supabase\.co',parsed.netloc) or parsed.path or parsed.query or parsed.fragment:
        raise SyncError('Only the explicitly authorized hosted Supabase HTTPS origin is accepted')
    secret=os.getenv('SUPABASE_SECRET_KEY','')
    if not secret.startswith('sb_secret_'): raise SyncError('Configure a server-only SUPABASE_SECRET_KEY locally; legacy/public keys are not accepted')
    client=RestClient(url,secret,transport=transport)
    try:
        client.immutable_rows('datasets',plan.tables['datasets'],['dataset_id'])
        client.upsert('pipeline_runs',plan.tables['pipeline_runs'],KEYS['pipeline_runs'])
        client.immutable_rows('raw_records',plan.tables['raw_records'],['dataset_id','record_id'])
        for name,keys in KEYS.items():
            if name!='pipeline_runs': client.upsert(name,plan.tables[name],keys)
        for item in plan.files: client.upload_immutable(item)
        client.immutable_rows('snapshots',plan.tables['snapshots'],['snapshot_id'])
        if approve_publication:
            row=dict(plan.tables['snapshots'][0],approved=True,context='demo')
            client.immutable_rows('published_demo_snapshots',[row],['snapshot_id'],schema='public')
    finally: client.close()
    result=plan.summary();result.update(status='SYNCED',connected=True,public_write=approve_publication)
    return result


def main():
    parser=argparse.ArgumentParser(description='Validate local layers; cloud writes require explicit target authorization.')
    parser.add_argument('--snapshot',required=True,type=Path)
    parser.add_argument('--raw-csv',required=True,type=Path)
    parser.add_argument('--run-dir',type=Path)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--authorized-url')
    parser.add_argument('--approve-publication',action='store_true')
    args=parser.parse_args()
    try:
        snapshot=json.loads(args.snapshot.read_text(encoding='utf-8-sig'))
        artifacts={};reviews=[]
        if args.run_dir:
            for name in ['raw.json','cleaned.json','features.json','metrics.json','decisions.json','qa.json','manifest.json','reviews.json','snapshot.json']:
                path=args.run_dir/name
                if path.is_file(): artifacts[name]=path.read_bytes()
            if 'reviews.json' in artifacts: reviews=json.loads(artifacts['reviews.json'])
        plan=build_plan(snapshot,args.raw_csv.read_bytes(),reviews=reviews,artifacts=artifacts)
        result=sync_all_layers(plan,execute=args.execute,authorized_url=args.authorized_url,approve_publication=args.approve_publication)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    except (ValidationError,SyncError) as error:
        print(json.dumps({'status':'FAILED','error':str(error)},ensure_ascii=False));return 1
    except (OSError,ValueError,KeyError,TypeError):
        print(json.dumps({'status':'FAILED','error':'Invalid or unreadable local artifact; details suppressed'}));return 1


if __name__=='__main__': raise SystemExit(main())

"""Loopback-only management API; public artifacts are synthetic snapshots only."""
import json
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from pydantic import BaseModel, ConfigDict, Field

from .pipeline import BASE, PUBLIC, RUNTIME, VERSIONS, now, read_reviews, run_pipeline


class RunRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    record_id: str = Field(min_length=1, max_length=80)
    action: Literal['KEEP', 'FILTER']
    note: str = Field(min_length=1, max_length=1000)


def create_app(runtime=RUNTIME, public_path=PUBLIC, dist=BASE / 'frontend' / 'dist'):
    runtime, public_path, dist = Path(runtime), Path(public_path), Path(dist)
    api = FastAPI(title='Consumer Insight Synthetic Demo', docs_url=None, redoc_url=None, openapi_url=None)
    guard = threading.Lock()
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='demo-pipeline')
    tasks = {}

    @api.middleware('http')
    async def local_access(request: Request, call_next):
        host = request.headers.get('host', '')
        try:
            address = urlsplit('http://' + host)
            local_host = address.hostname in ('127.0.0.1', 'localhost', '::1') and not address.username and not address.password
            _ = address.port
        except ValueError:
            local_host = False
        if not local_host:
            return JSONResponse({'detail': 'Only loopback Host is accepted'}, status_code=400)
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            origin = request.headers.get('origin')
            if origin != f'{request.url.scheme}://{host}' or request.headers.get('sec-fetch-site') == 'cross-site':
                return JSONResponse({'detail': 'Same-origin loopback request required'}, status_code=403)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        if request.url.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    def current_snapshot():
        if not public_path.exists():
            raise HTTPException(404, 'No snapshot yet; run python -m backend.pipeline')
        return json.loads(public_path.read_text(encoding='utf-8'))

    @api.get('/api/health')
    def health():
        return {'service': 'consumer-insight-demo-2.0', 'status': 'ok', 'context': 'demo', 'mode': 'rules_demo',
                'versions': VERSIONS, 'has_snapshot': public_path.is_file(), 'management_enabled': True}

    @api.get('/api/snapshot')
    def snapshot():
        return current_snapshot()

    @api.get('/api/runs')
    def runs():
        with guard:
            recent = dict(tasks)
        for path in sorted((runtime / 'runs').glob('*/manifest.json'), reverse=True)[:50]:
            item = json.loads(path.read_text(encoding='utf-8'))
            recent.setdefault(item['run_id'], {'run_id': item['run_id'], 'status': item['status'], 'generated_at': item['generated_at'], 'mode': item['mode']})
        return {'runs': sorted(recent.values(), key=lambda r: r['run_id'], reverse=True)[:50]}

    def execute(run_id):
        try:
            result = run_pipeline(runtime=runtime, public_path=public_path, run_id=run_id)
            with guard:
                tasks[run_id] = {'run_id': run_id, 'status': 'COMPLETED', 'generated_at': result['generated_at'], 'mode': 'rules_demo'}
        except Exception as exc:
            with guard:
                tasks[run_id] = {'run_id': run_id, 'status': 'FAILED', 'finished_at': now(), 'mode': 'rules_demo',
                                 'error': f'Pipeline failed: {type(exc).__name__}. Check the fixed input and local runtime.'}

    @api.post('/api/runs', status_code=202)
    def start_run(body: RunRequest = RunRequest()):
        with guard:
            running = next((r for r in tasks.values() if r['status'] == 'RUNNING'), None)
            if running:
                return dict(running)
            run_id = now().replace('-', '').replace(':', '').split('.')[0] + '-' + uuid.uuid4().hex[:10]
            task = {'run_id': run_id, 'status': 'RUNNING', 'started_at': now(), 'mode': 'rules_demo'}
            tasks[run_id] = task
            executor.submit(execute, run_id)
            return dict(task)

    @api.get('/api/reviews')
    def reviews():
        with guard:
            return {'reviews': read_reviews(runtime)}

    @api.post('/api/reviews', status_code=201)
    def review(body: ReviewRequest):
        snap = current_snapshot()
        if body.record_id not in {r['record_id'] for r in snap['records']}:
            raise HTTPException(404, 'Unknown record in current demo dataset')
        event = {**body.model_dump(), 'review_id': 'R-' + uuid.uuid4().hex,
                 'created_at': now(), 'dataset_id': snap['dataset_id'], 'raw_hash': snap['qa']['raw_hash'],
                 'reviewed_snapshot_id': snap['snapshot_id'], 'context': 'demo'}
        with guard:
            runtime.mkdir(parents=True, exist_ok=True)
            with (runtime / 'reviews.jsonl').open('a', encoding='utf-8') as log:
                log.write(json.dumps(event, ensure_ascii=False) + '\n')
                log.flush()
                os.fsync(log.fileno())
        return {'review': event, 'requires_new_run': True, 'message': '已追加审核记录；运行新批次后生效。'}

    @api.get('/{path:path}')
    def frontend(path: str):
        if path.startswith(('api/', 'runtime/', 'backend/')) or path in ('runtime', 'backend', 'api'):
            raise HTTPException(404, 'Not public')
        if not (dist / 'index.html').is_file():
            if path:
                raise HTTPException(404, 'Frontend build missing')
            return HTMLResponse('<h1>演示后端已启动</h1><p>前端尚未构建，请先完成本地前端构建。</p>', status_code=503)
        target = (dist / path).resolve()
        if not target.is_relative_to(dist.resolve()):
            raise HTTPException(404, 'Not found')
        if target.is_file():
            return FileResponse(target)
        if '.' in Path(path).name:
            raise HTTPException(404, 'Not found')
        return FileResponse(dist / 'index.html')

    return api


app = create_app()

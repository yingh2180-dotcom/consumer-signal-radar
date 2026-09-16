import importlib.util
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('backend.server'), 'API has not been implemented')
        from backend.server import create_app
        from backend.pipeline import run_pipeline
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.runtime = Path(self.temp.name) / 'runtime'
        self.public = Path(self.temp.name) / 'snapshot.json'
        self.snap = run_pipeline(runtime=self.runtime, public_path=self.public)
        self.client = TestClient(create_app(self.runtime, self.public, Path(self.temp.name) / 'dist'), base_url='http://127.0.0.1:18523')
        self.addCleanup(self.client.close)
        self.origin = {'Origin': 'http://127.0.0.1:18523'}

    def test_health_snapshot_and_runtime_not_public(self):
        self.assertEqual(self.client.get('/api/health').json()['service'], 'consumer-insight-demo-2.0')
        self.assertEqual(self.client.get('/api/snapshot').json()['run_id'], self.snap['run_id'])
        self.assertEqual(self.client.get('/runtime/reviews.jsonl').status_code, 404)
        self.assertEqual(self.client.get('/api/reviews', headers={'Host': 'attacker.example'}).status_code, 400)

    def test_cross_site_writes_and_extra_parameters_rejected(self):
        payload = {'record_id': self.snap['records'][60]['record_id'], 'action': 'FILTER', 'note': '测试'}
        for origin in [None, 'https://evil.example', 'http://localhost:18523', 'http://127.0.0.1:9999', 'null']:
            headers = {'Origin': origin} if origin else {}
            self.assertEqual(self.client.post('/api/reviews', json=payload, headers=headers).status_code, 403)
        self.assertEqual(self.client.post('/api/runs', json={'input_path': 'arbitrary'}, headers=self.origin).status_code, 422)
        self.assertEqual(self.client.post('/api/reviews', json=dict(payload, record_id='unknown'), headers=self.origin).status_code, 404)
        self.assertEqual(self.client.post('/api/reviews', json=dict(payload, action='DELETE'), headers=self.origin).status_code, 422)

    def test_reviews_append_only_and_do_not_mutate_snapshot(self):
        before = self.public.read_bytes()
        payload = {'record_id': self.snap['records'][60]['record_id'], 'action': 'FILTER', 'note': '第一条'}
        self.assertEqual(self.client.post('/api/reviews', json=payload, headers=self.origin).status_code, 201)
        first_log = (self.runtime / 'reviews.jsonl').read_bytes()
        self.assertEqual(self.client.post('/api/reviews', json=dict(payload, action='KEEP', note='第二条'), headers=self.origin).status_code, 201)
        self.assertTrue((self.runtime / 'reviews.jsonl').read_bytes().startswith(first_log))
        self.assertEqual(self.public.read_bytes(), before)
        log = self.client.get('/api/reviews').json()['reviews']
        self.assertEqual(len(log), 2)
        self.assertEqual(log[0]['raw_hash'], self.snap['qa']['raw_hash'])

    def test_runs_background_deduplicated_and_publish_new_snapshot(self):
        from backend.pipeline import run_pipeline
        started, release = threading.Event(), threading.Event()
        def slow_run(**kwargs):
            started.set()
            release.wait(5)
            return run_pipeline(**kwargs)
        with patch('backend.server.run_pipeline', side_effect=slow_run):
            first = self.client.post('/api/runs', json={}, headers=self.origin)
            self.assertEqual(first.status_code, 202)
            self.assertTrue(started.wait(2))
            second = self.client.post('/api/runs', json={}, headers=self.origin)
            self.assertEqual(first.json()['run_id'], second.json()['run_id'])
            release.set()
            for _ in range(100):
                states = self.client.get('/api/runs').json()['runs']
                task = next(r for r in states if r['run_id'] == first.json()['run_id'])
                if task['status'] != 'RUNNING':
                    break
                time.sleep(.03)
            self.assertEqual(task['status'], 'COMPLETED')
            self.assertNotEqual(self.client.get('/api/snapshot').json()['run_id'], self.snap['run_id'])


if __name__ == '__main__':
    unittest.main()

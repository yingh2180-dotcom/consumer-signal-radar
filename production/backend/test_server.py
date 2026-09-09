"""Isolated integration tests; never make real model requests."""
import csv
import io
import json
import os
import secrets
import sqlite3
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from . import db, server, worker


class IdentityPrimitiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = os.path.join(self.temp.name, 'legacy.sqlite3')
        self.env = patch.dict(os.environ, {'RADAR_DB_PATH': self.database})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def test_identity_schema_migrates_legacy_data(self):
        connection = sqlite3.connect(self.database)
        connection.executescript('''
            CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE sessions(token TEXT PRIMARY KEY,expires REAL NOT NULL);
            CREATE TABLE attempts(ip TEXT NOT NULL,at REAL NOT NULL);
            CREATE TABLE projects(id TEXT PRIMARY KEY,name TEXT NOT NULL,description TEXT NOT NULL,created_at REAL NOT NULL);
            CREATE TABLE previews(id TEXT PRIMARY KEY,project_id TEXT REFERENCES projects(id),payload TEXT NOT NULL,created_at REAL NOT NULL);
            CREATE TABLE batches(id TEXT PRIMARY KEY,project_id TEXT REFERENCES projects(id),name TEXT NOT NULL,row_count INTEGER NOT NULL,quality TEXT NOT NULL,created_at REAL NOT NULL,data_kind TEXT NOT NULL);
            CREATE TABLE reviews(id TEXT PRIMARY KEY,project_id TEXT REFERENCES projects(id),batch_id TEXT REFERENCES batches(id),fingerprint TEXT NOT NULL,payload TEXT NOT NULL,UNIQUE(project_id,fingerprint));
            CREATE TABLE jobs(id TEXT PRIMARY KEY,project_id TEXT REFERENCES projects(id),status TEXT NOT NULL,stage TEXT NOT NULL,processed INTEGER NOT NULL DEFAULT 0,total INTEGER NOT NULL,error TEXT NOT NULL DEFAULT '',mode TEXT NOT NULL,created_at REAL NOT NULL,updated_at REAL NOT NULL,parameters TEXT NOT NULL,checkpoint TEXT NOT NULL DEFAULT '{}',result TEXT,lease TEXT,lease_until REAL NOT NULL DEFAULT 0,cancel INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE reports(id TEXT PRIMARY KEY,project_id TEXT REFERENCES projects(id),job_id TEXT REFERENCES jobs(id),title TEXT NOT NULL,created_at REAL NOT NULL,draft INTEGER NOT NULL,payload TEXT NOT NULL,markdown TEXT NOT NULL);
            INSERT INTO projects VALUES ('legacy-project','旧样本','不得丢失',1);
            INSERT INTO batches VALUES ('legacy-batch','legacy-project','样本',1,'{}',1,'合成数据');
            INSERT INTO reviews VALUES ('legacy-review','legacy-project','legacy-batch','fingerprint','{"id":"legacy-review","text":"旧评论"}');
            INSERT INTO sessions VALUES ('anonymous-token',9999999999);
        ''')
        connection.commit()
        connection.close()

        db.init()
        db.init()

        with db.connect() as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM projects').fetchone()[0], 1)
            self.assertEqual(connection.execute('SELECT count(*) FROM batches').fetchone()[0], 1)
            self.assertEqual(connection.execute('SELECT count(*) FROM reviews').fetchone()[0], 1)
            project = connection.execute('SELECT owner_type,owner_user_id,source_project_id FROM projects').fetchone()
            self.assertEqual(dict(project), {'owner_type':'system','owner_user_id':None,'source_project_id':None})
            self.assertEqual(connection.execute('SELECT count(*) FROM sessions').fetchone()[0], 0)
            self.assertEqual(
                {row['name'] for row in connection.execute('PRAGMA table_info(sessions)')},
                {'token','expires','user_id','role'},
            )
            self.assertIn('username_norm', {row['name'] for row in connection.execute('PRAGMA table_info(users)')})

    def test_password_hash_and_username_normalization(self):
        encoded = server.hash_password('correct-horse-123')
        self.assertNotIn('correct-horse-123', encoded)
        self.assertTrue(server.verify_password('correct-horse-123', encoded))
        self.assertFalse(server.verify_password('wrong-password', encoded))
        self.assertEqual(server.normalize_username('  Alice_张三  '), ('alice_张三', 'Alice_张三'))
        for invalid in ('ab', 'a b', 'a@example', 'x' * 33):
            with self.assertRaises(ValueError):
                server.normalize_username(invalid)


class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env_path = os.path.join(self.temp.name, '.env')
        self.env = patch.dict(os.environ, {
            'RADAR_DB_PATH': os.path.join(self.temp.name, 'test.sqlite3'),
            'RADAR_ENV_PATH': self.env_path,
            'RADAR_ADMIN_PASSWORD': 'test-password-1234',
            'RADAR_API_KEY': '',
            'RADAR_BASE_URL': '',
            'RADAR_MODEL': '',
            'RADAR_EMBEDDING_MODEL': '',
            'RADAR_PAID_ENABLED': 'false',
            'RADAR_COOKIE_SECURE': 'false',
        })
        self.env.start()
        self.client = TestClient(server.app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.env.stop()
        self.temp.cleanup()

    def test_registers_and_logs_in_automatically(self):
        response = self.client.post('/api/auth/register', json={'username':' Alice_张三 ', 'password':'correct-horse-123'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['username'], 'Alice_张三')
        self.assertEqual(response.json()['role'], 'user')
        self.assertTrue(response.json()['id'])
        self.assertEqual(
            self.client.get('/api/auth/me').json(),
            {'id':response.json()['id'], 'username':'Alice_张三', 'role':'user'},
        )
        self.assertNotIn('password', response.text.casefold())
        with db.connect() as connection:
            stored = connection.execute('SELECT password_hash FROM users').fetchone()[0]
        self.assertNotEqual(stored, 'correct-horse-123')
        self.assertTrue(server.verify_password('correct-horse-123', stored))

    def test_duplicate_and_invalid_registration_are_rejected(self):
        first = self.client.post('/api/auth/register', json={'username':'Example-User', 'password':'correct-horse-123'})
        self.assertEqual(first.status_code, 200, first.text)
        duplicate = self.client.post('/api/auth/register', json={'username':' example-user ', 'password':'another-secret-456'})
        self.assertEqual(duplicate.status_code, 409, duplicate.text)
        self.assertIn('用户名已存在', duplicate.text)
        for body in (
            {'username':'ab', 'password':'correct-horse-123'},
            {'username':'bad name', 'password':'correct-horse-123'},
            {'username':'Valid_Name', 'password':'short'},
        ):
            self.assertIn(self.client.post('/api/auth/register', json=body).status_code, (400, 422))

    def test_user_relogin_logout_and_generic_failure(self):
        registered = self.client.post('/api/auth/register', json={'username':'ReturnUser', 'password':'correct-horse-123'}).json()
        self.assertEqual(self.client.post('/api/auth/logout').status_code, 200)
        self.assertEqual(self.client.get('/api/auth/me').status_code, 401)
        wrong = self.client.post('/api/auth/login', json={'username':'ReturnUser', 'password':'wrong-password'})
        missing = self.client.post('/api/auth/login', json={'username':'MissingUser', 'password':'wrong-password'})
        self.assertEqual((wrong.status_code, wrong.json()), (401, missing.json()))
        response = self.client.post('/api/auth/login', json={'username':' returnuser ', 'password':'correct-horse-123'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['id'], registered['id'])
        self.assertEqual(response.json()['role'], 'user')

    def test_administrator_login_remains_separate(self):
        self.assertEqual(self.client.post('/api/auth/login', json={'password':'test-password-1234'}).status_code, 422)
        failed = self.client.post('/api/auth/admin-login', json={'password':'wrong-password'})
        self.assertEqual(failed.status_code, 401)
        response = self.client.post('/api/auth/admin-login', json={'password':'test-password-1234'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {'id':'admin', 'username':'管理员', 'role':'admin'})
        self.assertEqual(self.client.get('/api/auth/me').json(), response.json())

    def test_settings_are_redacted_for_users_and_writable_only_by_admin(self):
        secret = 'sk-never-return-this-secret'
        configured = {
            'RADAR_API_KEY':secret,
            'RADAR_BASE_URL':'https://example.com/v1',
            'RADAR_MODEL':'qwen-plus',
            'RADAR_EMBEDDING_MODEL':'text-embedding-v4',
            'RADAR_PAID_ENABLED':'true',
        }
        with patch.dict(os.environ, configured):
            self.client.post('/api/auth/register', json={'username':'SettingsUser', 'password':'correct-horse-123'})
            response = self.client.get('/api/settings')
            self.assertEqual(set(response.json()), {'configured','paid_enabled','max_rows'})
            self.assertNotIn(secret, response.text)
            denied = self.client.post('/api/settings', json={
                'api_key':'sk-attempted-replacement',
                'base_url':'https://other.example/v1',
                'model':'other-model',
                'embedding_model':'other-embedding',
                'paid_enabled':False,
            })
            self.assertEqual(denied.status_code, 403, denied.text)
            self.assertEqual(os.environ['RADAR_API_KEY'], secret)
            self.client.post('/api/auth/logout')
            self.client.post('/api/auth/admin-login', json={'password':'test-password-1234'})
            admin = self.client.get('/api/settings')
            self.assertIn('model', admin.json())
            self.assertIn('base_url', admin.json())
            self.assertNotIn('api_key', admin.json())
            self.assertNotIn(secret, admin.text)


class DataIsolationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {
            'RADAR_DB_PATH': os.path.join(self.temp.name, 'test.sqlite3'),
            'RADAR_ENV_PATH': os.path.join(self.temp.name, '.env'),
            'RADAR_ADMIN_PASSWORD': 'test-password-1234',
            'RADAR_API_KEY': '',
            'RADAR_BASE_URL': '',
            'RADAR_MODEL': '',
            'RADAR_EMBEDDING_MODEL': '',
            'RADAR_PAID_ENABLED': 'false',
            'RADAR_COOKIE_SECURE': 'false',
        })
        self.env.start()
        self.clients = []
        self.admin = self._client()
        self.assertEqual(self.admin.post('/api/auth/admin-login', json={'password':'test-password-1234'}).status_code, 200)
        sample = self.admin.post('/api/projects', json={'name':'公共样本'}).json()
        self.sample_id = sample['id']
        self._import(self.admin, self.sample_id)
        with db.connect() as connection:
            connection.execute("UPDATE projects SET owner_type='system',owner_user_id=NULL WHERE id=?", (self.sample_id,))
        self.alice = self._client()
        self.bob = self._client()
        self.assertEqual(self.alice.post('/api/auth/register', json={'username':'Alice_User', 'password':'correct-horse-123'}).status_code, 200)
        self.assertEqual(self.bob.post('/api/auth/register', json={'username':'Bob_User', 'password':'correct-horse-456'}).status_code, 200)

    def tearDown(self):
        for client in reversed(self.clients):
            client.__exit__(None, None, None)
        self.env.stop()
        self.temp.cleanup()

    def _client(self):
        client = TestClient(server.app)
        client.__enter__()
        self.clients.append(client)
        return client

    def _import(self, client, project_id):
        content = 'text,brand\n上脸刺激希望温和,测试\n晚上泛红需要停用,测试\n用了刺痛不舒服,测试\n清爽吸收快,测试\n'
        preview = client.post(f'/api/projects/{project_id}/imports/preview', files={'file':('data.csv',content.encode(),'text/csv')})
        self.assertEqual(preview.status_code, 200, preview.text)
        response = client.post(f'/api/projects/{project_id}/imports', json={
            'preview_id':preview.json()['preview_id'],
            'mapping':{'text':'text','brand':'brand'},
            'source_name':'测试样本',
            'data_kind':'合成测试',
        })
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()['id']

    def test_project_lists_and_direct_resources_are_isolated(self):
        alice_project = self.alice.post('/api/projects', json={'name':'Alice 私人项目'}).json()
        bob_project = self.bob.post('/api/projects', json={'name':'Bob 私人项目'}).json()
        alice_ids = {project['id'] for project in self.alice.get('/api/projects').json()}
        bob_ids = {project['id'] for project in self.bob.get('/api/projects').json()}
        self.assertEqual(alice_ids, {self.sample_id, alice_project['id']})
        self.assertEqual(bob_ids, {self.sample_id, bob_project['id']})
        self.assertEqual(alice_project['owner_type'], 'user')
        self.assertTrue(alice_project['is_owner'])

        batch_id = self._import(self.alice, alice_project['id'])
        job = self.alice.post(f"/api/projects/{alice_project['id']}/jobs", json={'batch_ids':[batch_id]}).json()
        self.assertTrue(worker.run_once())
        result = self.alice.get(f"/api/jobs/{job['id']}/result").json()
        report = self.alice.post(f"/api/jobs/{job['id']}/reports", json={'draft':True}).json()
        card_id = result['cards'][0]['id']
        csv_file = {'file':('gold.csv', b'id,text\n1,example\n', 'text/csv')}
        attempts = [
            self.bob.get(f"/api/projects/{alice_project['id']}/imports"),
            self.bob.get(f"/api/projects/{alice_project['id']}/reviews"),
            self.bob.get(f"/api/projects/{alice_project['id']}/jobs"),
            self.bob.get(f"/api/projects/{alice_project['id']}/reports"),
            self.bob.post(f"/api/projects/{alice_project['id']}/imports/preview", files={'file':('data.csv', b'text\nprivate\n','text/csv')}),
            self.bob.post(f"/api/projects/{alice_project['id']}/imports", json={'preview_id':'missing','mapping':{'text':'text'}}),
            self.bob.post(f"/api/projects/{alice_project['id']}/demo"),
            self.bob.post(f"/api/projects/{alice_project['id']}/jobs", json={'batch_ids':[batch_id]}),
            self.bob.get(f"/api/jobs/{job['id']}"),
            self.bob.get(f"/api/jobs/{job['id']}/result"),
            self.bob.post(f"/api/jobs/{job['id']}/cancel"),
            self.bob.post(f"/api/jobs/{job['id']}/retry"),
            self.bob.patch(f"/api/jobs/{job['id']}/cards/{card_id}", json={'hypothesis':'越权', 'reviewed':False}),
            self.bob.post(f"/api/jobs/{job['id']}/reports", json={'draft':True}),
            self.bob.get(f"/api/reports/{report['id']}"),
            self.bob.get(f"/api/reports/{report['id']}/download"),
            self.bob.get(f"/api/jobs/{job['id']}/export.csv"),
            self.bob.get(f"/api/jobs/{job['id']}/annotation.csv"),
            self.bob.post(f"/api/jobs/{job['id']}/evaluate", files=csv_file),
        ]
        self.assertTrue(all(response.status_code == 404 for response in attempts), [(r.status_code,r.text) for r in attempts])

    def test_system_sample_is_read_only_and_copies_are_private(self):
        for client in (self.alice, self.bob):
            sample = next(project for project in client.get('/api/projects').json() if project['id']==self.sample_id)
            self.assertEqual(sample['owner_type'], 'system')
            self.assertFalse(sample['is_owner'])
            self.assertEqual(client.get(f'/api/projects/{self.sample_id}/reviews').json()['total'], 4)
            self.assertEqual(client.post(f'/api/projects/{self.sample_id}/demo').status_code, 404)

        alice_copy = self.alice.post(f'/api/projects/{self.sample_id}/copy').json()
        bob_copy = self.bob.post(f'/api/projects/{self.sample_id}/copy').json()
        self.assertNotEqual(alice_copy['id'], bob_copy['id'])
        self.assertEqual(alice_copy['source_project_id'], self.sample_id)
        self.assertEqual(bob_copy['source_project_id'], self.sample_id)
        self.assertTrue(alice_copy['is_owner'])
        self.assertEqual(self.alice.get(f"/api/projects/{alice_copy['id']}/reviews").json()['total'], 4)
        self.assertEqual(self.bob.get(f"/api/projects/{bob_copy['id']}/reviews").json()['total'], 4)
        self.assertEqual(self.bob.get(f"/api/projects/{alice_copy['id']}/reviews").status_code, 404)
        added = self.alice.post(f"/api/projects/{alice_copy['id']}/demo")
        self.assertEqual(added.status_code, 200, added.text)
        self.assertGreater(self.alice.get(f"/api/projects/{alice_copy['id']}/reviews").json()['total'], 4)
        self.assertEqual(self.bob.get(f"/api/projects/{bob_copy['id']}/reviews").json()['total'], 4)


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.env_path=os.path.join(self.temp.name,'.env')
        self.env=patch.dict(os.environ, {'RADAR_DB_PATH':self.temp.name+'/test.sqlite3','RADAR_ENV_PATH':self.env_path,'RADAR_ADMIN_PASSWORD':'test-password-1234','RADAR_API_KEY':'','RADAR_BASE_URL':'','RADAR_MODEL':'','RADAR_EMBEDDING_MODEL':'','RADAR_PAID_ENABLED':'false','RADAR_COOKIE_SECURE':'false'})
        self.env.start()
        self.client=TestClient(server.app)
        self.client.__enter__()
        self.assertEqual(self.client.post('/api/auth/admin-login',json={'password':'test-password-1234'}).status_code,200)
        self.pid=self.client.post('/api/projects',json={'name':'测试项目'}).json()['id']

    def tearDown(self):
        self.client.__exit__(None,None,None)
        self.env.stop()
        self.temp.cleanup()

    def imported(self):
        content='text,brand\n上脸刺激希望温和,测试\n晚上泛红需要停用,测试\n用了刺痛不舒服,测试\n清爽吸收快,测试\n'
        response=self.client.post(f'/api/projects/{self.pid}/imports/preview',files={'file':('data.csv',content.encode(),'text/csv')})
        self.assertEqual(response.status_code,200,response.text)
        response=self.client.post(f'/api/projects/{self.pid}/imports',json={'preview_id':response.json()['preview_id'],'mapping':{'text':'text','brand':'brand'},'source_name':'测试样本','data_kind':'合成测试'})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['row_count'],4)
        return response.json()['id']

    def queued(self):
        batch=self.imported()
        body={'batch_ids':[batch],'mode':'offline'}
        first=self.client.post(f'/api/projects/{self.pid}/jobs',json=body)
        self.assertEqual(first.status_code,200,first.text)
        duplicate=self.client.post(f'/api/projects/{self.pid}/jobs',json=body)
        self.assertEqual(first.json()['id'],duplicate.json()['id'])
        return first.json()['id']

    def test_end_to_end_report_snapshot_export(self):
        jid=self.queued()
        self.assertTrue(worker.run_once())
        self.assertEqual(self.client.get(f'/api/jobs/{jid}').json()['status'],'succeeded')
        data=self.client.get(f'/api/jobs/{jid}/result').json()
        self.assertEqual(len(data['reviews']),4)
        card=data['cards'][0]
        self.assertEqual(self.client.post(f'/api/jobs/{jid}/reports',json={'draft':False}).status_code,400)
        self.assertEqual(self.client.patch(f"/api/jobs/{jid}/cards/{card['id']}",json={'hypothesis':'待验证假设','reviewed':True}).status_code,200)
        report=self.client.post(f'/api/jobs/{jid}/reports',json={'title':'测试','draft':False}).json()
        self.client.patch(f"/api/jobs/{jid}/cards/{card['id']}",json={'hypothesis':'后续修订','reviewed':False})
        self.assertIn('待验证假设',self.client.get(f"/api/reports/{report['id']}").json()['markdown'])
        self.assertIn('数据类型：合成测试：4 条',report['markdown'])
        self.assertIn('系统未独立核验授权、真实性或代表性',report['markdown'])
        self.assertIn('**样本事实**',report['markdown'])
        self.assertIn('**结论边界**',report['markdown'])
        self.assertEqual(self.client.get(f'/api/jobs/{jid}/export.csv').status_code,200)
        self.assertEqual(self.client.get(f'/api/jobs/{jid}/annotation.csv').status_code,200)

    def test_cancel_and_retry(self):
        jid=self.queued()
        self.client.post(f'/api/jobs/{jid}/cancel')
        self.assertFalse(worker.run_once())
        self.assertEqual(self.client.post(f'/api/jobs/{jid}/retry').json()['status'],'queued')
        worker.run_once()
        self.assertEqual(self.client.get(f'/api/jobs/{jid}').json()['status'],'succeeded')

    def test_expired_lease_recovered(self):
        jid=self.queued()
        with db.connect() as c:
            c.execute("UPDATE jobs SET status='running',lease='old',lease_until=? WHERE id=?",(time.time()-1,jid))
        worker.run_once()
        self.assertEqual(self.client.get(f'/api/jobs/{jid}').json()['status'],'succeeded')

    def test_failure_checkpoint_and_resume(self):
        jid=self.queued()
        original=worker.engine.analyze_reviews
        def fail(rows,mode,clusters,progress,checkpoint):
            checkpoint['test_marker']='saved'
            progress('抽取',1,len(rows))
            raise ValueError('可恢复测试错误')
        with patch.object(worker.engine,'analyze_reviews',side_effect=fail):
            worker.run_once()
        self.assertEqual(self.client.get(f'/api/jobs/{jid}').json()['status'],'failed')
        with db.connect() as c:
            self.assertEqual(json.loads(c.execute('SELECT checkpoint FROM jobs WHERE id=?',(jid,)).fetchone()[0])['test_marker'],'saved')
        self.client.post(f'/api/jobs/{jid}/retry')
        worker.run_once()
        self.assertEqual(self.client.get(f'/api/jobs/{jid}').json()['status'],'succeeded')

    def test_running_cancel_keeps_checkpoint(self):
        jid=self.queued()
        def cancel_during_analysis(rows,mode,clusters,progress,checkpoint):
            checkpoint['test_marker']='cancelled-progress'
            self.client.post(f'/api/jobs/{jid}/cancel')
            progress('抽取',1,len(rows))
            raise AssertionError('取消必须阻止后续执行')
        with patch.object(worker.engine,'analyze_reviews',side_effect=cancel_during_analysis):
            worker.run_once()
        self.assertEqual(self.client.get(f'/api/jobs/{jid}').json()['status'],'cancelled')
        with db.connect() as c:
            self.assertEqual(json.loads(c.execute('SELECT checkpoint FROM jobs WHERE id=?',(jid,)).fetchone()[0])['test_marker'],'cancelled-progress')

    def test_spa_static_and_unknown_api(self):
        from pathlib import Path
        root=Path(self.temp.name)/'web'; root.mkdir()
        (root/'index.html').write_text('<main>radar</main>')
        with patch.dict(os.environ,{'RADAR_FRONTEND_DIR':str(root)}):
            self.assertEqual(self.client.get('/projects/example').status_code,200)
            self.assertEqual(self.client.get('/missing.js').status_code,404)
            self.assertEqual(self.client.get('/api/missing').status_code,404)
            self.assertEqual(self.client.get('/%2e%2e%2fsecret.txt').status_code,404)

    def test_auth_csrf_paid_and_scope(self):
        self.assertEqual(self.client.post('/api/projects',headers={'origin':'https://evil.test'},json={'name':'bad'}).status_code,403)
        bid=self.imported()
        self.assertEqual(self.client.post(f'/api/projects/{self.pid}/jobs',json={'batch_ids':[bid],'mode':'llm','consent':True}).status_code,400)
        other=self.client.post('/api/projects',json={'name':'other'}).json()['id']
        self.assertEqual(self.client.post(f'/api/projects/{other}/jobs',json={'batch_ids':[bid]}).status_code,400)
        self.client.post('/api/auth/logout')
        self.assertEqual(self.client.get('/api/projects').status_code,401)

    def test_settings_save_preserve_key_and_never_disclose_it(self):
        secret='sk-unit-test-secret-123456'
        with open(self.env_path,'w',encoding='utf-8') as stream:
            stream.write('RADAR_ADMIN_PASSWORD=keep-this\nUNRELATED=value\nRADAR_API_KEY=old-secret-key-123\n')
        response=self.client.post('/api/settings',json={
            'api_key':secret,
            'base_url':'https://dashscope.aliyuncs.com/compatible-mode/v1/',
            'model':'qwen3.5-plus',
            'embedding_model':'text-embedding-v4',
            'paid_enabled':True,
        })
        self.assertEqual(response.status_code,200,response.text)
        self.assertNotIn(secret,response.text)
        self.assertNotIn('api_key',response.json())
        self.assertEqual(response.json()['base_url'],'https://dashscope.aliyuncs.com/compatible-mode/v1')
        self.assertTrue(response.json()['key_configured'])
        saved=Path(self.env_path).read_text(encoding='utf-8')
        self.assertIn('RADAR_ADMIN_PASSWORD=keep-this',saved)
        self.assertIn('UNRELATED=value',saved)
        self.assertIn('RADAR_API_KEY='+secret,saved)
        self.assertEqual(os.environ['RADAR_API_KEY'],secret)
        self.assertTrue(response.json()['configured'])
        self.assertTrue(response.json()['paid_enabled'])

        response=self.client.post('/api/settings',json={
            'api_key':'',
            'base_url':'https://example.com/v1',
            'model':'qwen-plus',
            'embedding_model':'text-embedding-v4',
            'paid_enabled':False,
        })
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(os.environ['RADAR_API_KEY'],secret)
        self.assertIn('RADAR_API_KEY='+secret,Path(self.env_path).read_text(encoding='utf-8'))
        self.assertNotIn(secret,response.text)
        self.assertEqual(response.json()['base_url'],'https://example.com/v1')
        self.assertTrue(response.json()['key_configured'])

    def test_settings_status_reports_missing_key_without_disclosing_field(self):
        response=self.client.get('/api/settings')
        self.assertEqual(response.status_code,200,response.text)
        self.assertFalse(response.json()['key_configured'])
        self.assertEqual(response.json()['base_url'],'')
        self.assertNotIn('api_key',response.json())

    def test_settings_rejects_invalid_url_model_key_and_cross_site(self):
        valid={'api_key':'sk-valid-test-123','base_url':'https://example.com/v1','model':'qwen-plus','embedding_model':'text-embedding-v4','paid_enabled':False}
        for field,value in (('base_url','http://example.com/v1'),('base_url','https://user:pass@example.com/v1'),('model','bad model'),('embedding_model','../unsafe model'),('api_key','short')):
            body={**valid,field:value}
            response=self.client.post('/api/settings',json=body)
            self.assertEqual(response.status_code,400,(field,response.text))
        response=self.client.post('/api/settings',headers={'origin':'https://evil.test'},json=valid)
        self.assertEqual(response.status_code,403,response.text)

    def test_xlsx_import_and_csv_formula(self):
        from openpyxl import Workbook
        wb=Workbook(); wb.active.append(['text']); wb.active.append(['测试评论'])
        buf=io.BytesIO(); wb.save(buf)
        r=self.client.post(f'/api/projects/{self.pid}/imports/preview',files={'file':('data.xlsx',buf.getvalue())})
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['total_rows'],1)
        r=server.csv_response([{'text':'=HYPERLINK("evil")'}],['text'],'test.csv')
        self.assertIn("'=HYPERLINK",r.body.decode('utf-8-sig'))

    def test_review_searches_text_and_source_id(self):
        content='id,text\nSKU-CASE-908,普通体验记录\nOTHER-1,包含目标词的评论\n'
        preview=self.client.post(f'/api/projects/{self.pid}/imports/preview',files={'file':('data.csv',content.encode(),'text/csv')})
        self.assertEqual(preview.status_code,200,preview.text)
        imported=self.client.post(f'/api/projects/{self.pid}/imports',json={
            'preview_id':preview.json()['preview_id'],'mapping':{'id':'id','text':'text'},
            'source_name':'搜索测试','data_kind':'合成测试'})
        self.assertEqual(imported.status_code,200,imported.text)
        by_id=self.client.get(f'/api/projects/{self.pid}/reviews',params={'q':'case-908'}).json()
        by_text=self.client.get(f'/api/projects/{self.pid}/reviews',params={'q':'目标词'}).json()
        self.assertEqual([row['source_id'] for row in by_id['items']],['SKU-CASE-908'])
        self.assertEqual([row['source_id'] for row in by_text['items']],['OTHER-1'])

    def register(self, username='测试用户A'):
        password=secrets.token_urlsafe(18)
        response=self.client.post('/api/auth/register',json={'username':username,'password':password})
        self.assertEqual(response.status_code,200,response.text)
        return response.json(),password

    def test_identity_schema_migrates_legacy_data(self):
        legacy=Path(self.temp.name)/'legacy.sqlite3'
        connection=sqlite3.connect(legacy)
        connection.executescript('''
            CREATE TABLE projects(id TEXT PRIMARY KEY,name TEXT NOT NULL,description TEXT NOT NULL,created_at REAL NOT NULL);
            CREATE TABLE sessions(token TEXT PRIMARY KEY,expires REAL NOT NULL);
            INSERT INTO projects VALUES ('legacy','旧样本','保留',1);
            INSERT INTO sessions VALUES ('anonymous',99999999999);
        ''')
        connection.close()
        with patch.dict(os.environ,{'RADAR_DB_PATH':str(legacy)}):
            db.init()
            server.import_rows('legacy',[{'text':'旧评论'}],{'text':'text'},'旧批次','测试')
            with db.connect() as c:
                c.execute("INSERT INTO jobs(id,project_id,status,stage,total,mode,created_at,updated_at,parameters) VALUES ('job','legacy','succeeded','完成',1,'offline',1,1,'{}')")
                c.execute("INSERT INTO reports VALUES ('report','legacy','job','旧报告',1,1,'{}','原文')")
                tables=('projects','reviews','batches','jobs','reports')
                before={t:c.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in tables}
            db.init(); db.init()
            with db.connect() as c:
                self.assertIn('owner_type',{r['name'] for r in c.execute('PRAGMA table_info(projects)')})
                self.assertEqual(c.execute('SELECT owner_type FROM projects').fetchone()[0],'system')
                self.assertEqual(c.execute('SELECT count(*) FROM sessions').fetchone()[0],0)
                self.assertEqual(before,{t:c.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in tables})

    def test_password_hashing_and_username_normalization(self):
        self.assertTrue(callable(getattr(server,'hash_password',None)))
        password=secrets.token_urlsafe(18)
        first=server.hash_password(password); second=server.hash_password(password)
        self.assertNotEqual(first,second)
        self.assertNotIn(password,first)
        self.assertTrue(server.verify_password(password,first))
        self.assertFalse(server.verify_password(password+'x',first))
        self.assertFalse(server.verify_password(password,'broken'))
        self.assertEqual(server.normalize_username('  User中文_A-1  '),('user中文_a-1','User中文_A-1'))

    def test_registration_login_identity_and_session_rotation(self):
        old_cookie=self.client.cookies.get('radar_session')
        account,password=self.register(' User_A ')
        self.assertEqual(account['username'],'User_A')
        self.assertEqual(account['role'],'user')
        self.assertNotEqual(old_cookie,self.client.cookies.get('radar_session'))
        self.assertEqual(self.client.get('/api/auth/me').json()['id'],account['id'])
        self.assertEqual(self.client.get('/api/auth/me',headers={'cookie':'radar_session='+old_cookie}).status_code,401)
        duplicate=self.client.post('/api/auth/register',json={'username':'user_a','password':password})
        self.assertEqual(duplicate.status_code,409)
        self.client.post('/api/auth/logout')
        self.assertEqual(self.client.get('/api/auth/me').status_code,401)
        missing=self.client.post('/api/auth/login',json={'username':'missing','password':password})
        wrong=self.client.post('/api/auth/login',json={'username':'User_A','password':password+'x'})
        self.assertEqual((missing.status_code,missing.json()),(wrong.status_code,wrong.json()))
        self.assertEqual(missing.status_code,401)
        login=self.client.post('/api/auth/login',json={'username':'user_A','password':password})
        self.assertEqual(login.json()['id'],account['id'])
        self.assertNotIn(password,login.text)
        self.assertNotIn('hash',login.text)
        db.init()
        self.assertEqual(self.client.get('/api/auth/me').json()['id'],account['id'])
        admin=self.client.post('/api/auth/admin-login',json={'password':os.environ['RADAR_ADMIN_PASSWORD']})
        self.assertEqual(admin.status_code,200,admin.text)
        self.assertEqual(admin.json()['role'],'admin')

    def test_registration_validation_never_echoes_password(self):
        for username,password in [('ab','12345678'),('invalid name','12345678'),('a'*33,'12345678'),('valid_user','short'),('valid_user','x'*129)]:
            response=self.client.post('/api/auth/register',json={'username':username,'password':password})
            self.assertIn(response.status_code,(400,422))
            self.assertNotIn(password,response.text)

    def test_all_descendant_routes_are_isolated_between_users(self):
        self.register()
        self.pid=self.client.post('/api/projects',json={'name':'A私人'}).json()['id']
        jid=self.queued(); worker.run_once()
        data=self.client.get(f'/api/jobs/{jid}/result').json()
        cid=data['cards'][0]['id']
        rid=self.client.post(f'/api/jobs/{jid}/reports',json={}).json()['id']
        self.register('测试用户B')
        self.assertNotIn(self.pid,{p['id'] for p in self.client.get('/api/projects').json()})
        requests=[('GET',f'/api/projects/{self.pid}/{suffix}',{}) for suffix in ('imports','reviews','jobs','reports')]
        requests += [('GET',f'/api/jobs/{jid}{suffix}',{}) for suffix in ('','/result','/export.csv','/annotation.csv')]
        requests += [('GET',f'/api/reports/{rid}{suffix}',{}) for suffix in ('','/download')]
        requests += [('POST',f'/api/jobs/{jid}/{suffix}',{}) for suffix in ('cancel','retry','reports')]
        requests += [('POST',f'/api/projects/{self.pid}/{suffix}',{}) for suffix in ('demo','copy','jobs','imports')]
        requests += [('PATCH',f'/api/jobs/{jid}/cards/{cid}',{'json':{'hypothesis':'入侵','reviewed':False}})]
        requests += [('POST',f'/api/projects/{self.pid}/imports/preview',{'files':{'file':('x.csv',b'text\nx')}}),('POST',f'/api/jobs/{jid}/evaluate',{'files':{'file':('x.csv',b'id,text\nx,y')}})]
        for method,url,kwargs in requests:
            with self.subTest(method=method,url=url):
                self.assertEqual(self.client.request(method,url,**kwargs).status_code,404)
        self.client.post('/api/auth/admin-login',json={'password':os.environ['RADAR_ADMIN_PASSWORD']})
        self.assertEqual(self.client.get(f'/api/jobs/{jid}').status_code,404)
        self.assertEqual(self.client.get('/api/backup').status_code,404)

    def test_system_samples_are_read_only_and_copy_is_private(self):
        jid=self.queued(); worker.run_once()
        cid=self.client.get(f'/api/jobs/{jid}/result').json()['cards'][0]['id']
        with db.connect() as c:
            c.execute("UPDATE projects SET owner_type='system',owner_user_id=NULL WHERE id=?",(self.pid,))
        self.register()
        sample=next(p for p in self.client.get('/api/projects').json() if p['id']==self.pid)
        self.assertEqual(sample['owner_type'],'system'); self.assertFalse(sample['is_owner'])
        self.assertEqual(self.client.get(f'/api/jobs/{jid}/result').status_code,200)
        for url in (f'/api/projects/{self.pid}/demo',f'/api/projects/{self.pid}/jobs',f'/api/jobs/{jid}/retry',f'/api/jobs/{jid}/cancel',f'/api/jobs/{jid}/reports'):
            self.assertEqual(self.client.post(url,json={}).status_code,404)
        self.assertEqual(self.client.patch(f'/api/jobs/{jid}/cards/{cid}',json={'hypothesis':'改样本','reviewed':False}).status_code,404)
        copied=self.client.post(f'/api/projects/{self.pid}/copy')
        self.assertEqual(copied.status_code,200,copied.text)
        copy=copied.json()
        self.assertTrue(copy['is_owner']); self.assertEqual(copy['source_project_id'],self.pid)
        self.assertEqual(copy['owner_type'],'user')
        self.assertNotEqual(copy['id'],self.pid)
        original=self.client.get(f'/api/projects/{self.pid}/reviews').json()['items']
        own=self.client.get(f"/api/projects/{copy['id']}/reviews").json()['items']
        self.assertEqual([r['text'] for r in own],[r['text'] for r in original])
        self.assertTrue({r['id'] for r in own}.isdisjoint(r['id'] for r in original))
        self.assertEqual(self.client.post(f'/api/projects/{self.pid}/copy').json()['id'],copy['id'])
        self.register('测试用户B')
        self.assertEqual(self.client.get(f"/api/projects/{copy['id']}/reviews").status_code,404)
        self.assertEqual(self.client.get(f'/api/projects/{self.pid}/reviews').status_code,200)
        second=self.client.post(f'/api/projects/{self.pid}/copy').json()
        self.assertNotEqual(copy['id'],second['id'])

    def test_settings_role_redaction_and_write_guard(self):
        self.assertIn('base_url',self.client.get('/api/settings').json())
        self.register()
        self.assertEqual(set(self.client.get('/api/settings').json()),{'configured','paid_enabled','max_rows'})
        response=self.client.post('/api/settings',json={'api_key':secrets.token_urlsafe(20),'base_url':'https://example.com','model':'test','embedding_model':'test'})
        self.assertEqual(response.status_code,403,response.text)
        self.assertFalse(Path(self.env_path).exists())


if __name__=='__main__':
    unittest.main()

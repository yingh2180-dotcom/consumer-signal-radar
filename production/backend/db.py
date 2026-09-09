"""Single-instance durable storage; all connections enforce foreign keys."""
import json
import os
import sqlite3
import time
import uuid
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / '.env', override=False)

class ClosingConnection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()

def uid():
    return str(uuid.uuid4())

def connect():
    data_dir = Path(os.getenv('RADAR_DATA_DIR', str(Path(__file__).resolve().parent.parent / 'var')))
    path = Path(os.environ.get('RADAR_DB_PATH', str(data_dir / 'radar.sqlite3')))
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=20, factory=ClosingConnection)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys=ON')
    connection.execute('PRAGMA journal_mode=WAL')
    return connection

def init():
    with connect() as c:
        c.execute('BEGIN IMMEDIATE')
        c.execute('CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
        c.execute('CREATE TABLE IF NOT EXISTS attempts(ip TEXT NOT NULL,at REAL NOT NULL)')
        c.execute('''CREATE TABLE IF NOT EXISTS users(
            id TEXT PRIMARY KEY,
            username_norm TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('user','admin')),
            status TEXT NOT NULL CHECK(status IN ('active','disabled')),
            created_at REAL NOT NULL
        )''')

        session_exists = c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='sessions'").fetchone()
        if session_exists:
            session_columns = {row['name'] for row in c.execute('PRAGMA table_info(sessions)')}
            if not {'token','expires','user_id','role'}.issubset(session_columns):
                c.execute('DROP TABLE sessions')
                session_exists = False
        if not session_exists:
            c.execute('''CREATE TABLE sessions(
                token TEXT PRIMARY KEY,
                expires REAL NOT NULL,
                user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
                role TEXT NOT NULL CHECK(role IN ('user','admin'))
            )''')

        c.execute('''CREATE TABLE IF NOT EXISTS projects(
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            created_at REAL NOT NULL,
            owner_type TEXT NOT NULL DEFAULT 'system' CHECK(owner_type IN ('system','user')),
            owner_user_id TEXT,
            source_project_id TEXT REFERENCES projects(id) ON DELETE SET NULL
        )''')
        project_columns = {row['name'] for row in c.execute('PRAGMA table_info(projects)')}
        if 'owner_type' not in project_columns:
            c.execute("ALTER TABLE projects ADD COLUMN owner_type TEXT NOT NULL DEFAULT 'system' CHECK(owner_type IN ('system','user'))")
        if 'owner_user_id' not in project_columns:
            c.execute('ALTER TABLE projects ADD COLUMN owner_user_id TEXT')
        if 'source_project_id' not in project_columns:
            c.execute('ALTER TABLE projects ADD COLUMN source_project_id TEXT REFERENCES projects(id) ON DELETE SET NULL')
        c.execute("UPDATE projects SET owner_type='system',owner_user_id=NULL WHERE owner_type IS NULL OR owner_type NOT IN ('system','user')")

        for statement in (
            'CREATE TABLE IF NOT EXISTS previews(id TEXT PRIMARY KEY,project_id TEXT REFERENCES projects(id),payload TEXT NOT NULL,created_at REAL NOT NULL)',
            'CREATE TABLE IF NOT EXISTS batches(id TEXT PRIMARY KEY,project_id TEXT REFERENCES projects(id),name TEXT NOT NULL,row_count INTEGER NOT NULL,quality TEXT NOT NULL,created_at REAL NOT NULL,data_kind TEXT NOT NULL)',
            'CREATE TABLE IF NOT EXISTS reviews(id TEXT PRIMARY KEY,project_id TEXT REFERENCES projects(id),batch_id TEXT REFERENCES batches(id),fingerprint TEXT NOT NULL,payload TEXT NOT NULL,UNIQUE(project_id,fingerprint))',
            "CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,project_id TEXT REFERENCES projects(id),status TEXT NOT NULL,stage TEXT NOT NULL,processed INTEGER NOT NULL DEFAULT 0,total INTEGER NOT NULL,error TEXT NOT NULL DEFAULT '',mode TEXT NOT NULL,created_at REAL NOT NULL,updated_at REAL NOT NULL,parameters TEXT NOT NULL,checkpoint TEXT NOT NULL DEFAULT '{}',result TEXT,lease TEXT,lease_until REAL NOT NULL DEFAULT 0,cancel INTEGER NOT NULL DEFAULT 0)",
            'CREATE TABLE IF NOT EXISTS reports(id TEXT PRIMARY KEY,project_id TEXT REFERENCES projects(id),job_id TEXT REFERENCES jobs(id),title TEXT NOT NULL,created_at REAL NOT NULL,draft INTEGER NOT NULL,payload TEXT NOT NULL,markdown TEXT NOT NULL)',
            'CREATE INDEX IF NOT EXISTS reviews_batch ON reviews(batch_id)',
            'CREATE INDEX IF NOT EXISTS jobs_status ON jobs(status,lease_until)',
            'CREATE INDEX IF NOT EXISTS projects_owner ON projects(owner_type,owner_user_id,created_at)',
        ):
            c.execute(statement)

def job_public(row):
    return {k: row[k] for k in ('id','project_id','status','stage','processed','total','error','mode','created_at','updated_at')}

def dump(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)

"""Durable single-instance worker. Run: python -m backend.worker."""
import json
import os
import threading
import time
from pathlib import Path
try:
    from . import db, engine
except ImportError:
    import db, engine

LEASE_SECONDS = 120


class Cancelled(Exception):
    pass


def claim():
    now = time.time()
    with db.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        row = c.execute("SELECT * FROM jobs WHERE cancel=0 AND (status='queued' OR (status='running' AND lease_until<?)) ORDER BY created_at LIMIT 1", (now,)).fetchone()
        if not row:
            return None
        lease = db.uid()
        c.execute("UPDATE jobs SET status='running',stage='准备分析',lease=?,lease_until=?,updated_at=? WHERE id=?", (lease, now+LEASE_SECONDS, now, row['id']))
        return dict(c.execute('SELECT * FROM jobs WHERE id=?', (row['id'],)).fetchone())


def run_once():
    job = claim()
    if not job:
        return False
    jid, lease = job['id'], job['lease']
    state = json.loads(job['checkpoint'])
    stopped = threading.Event()

    def heartbeat():
        while not stopped.wait(15):
            with db.connect() as c:
                c.execute("UPDATE jobs SET lease_until=? WHERE id=? AND lease=? AND status='running' AND cancel=0", (time.time()+LEASE_SECONDS,jid,lease))

    def progress(stage, processed, total):
        with db.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute('SELECT cancel,lease,status FROM jobs WHERE id=?',(jid,)).fetchone()
            if not row or row['lease'] != lease or row['cancel'] or row['status'] != 'running':
                raise Cancelled()
            c.execute('UPDATE jobs SET stage=?,processed=?,total=?,checkpoint=?,updated_at=?,lease_until=? WHERE id=? AND lease=?',
                (stage,processed,total,db.dump(state),time.time(),time.time()+LEASE_SECONDS,jid,lease))

    thread=threading.Thread(target=heartbeat,daemon=True)
    thread.start()
    try:
        parameters=json.loads(job['parameters'])
        with db.connect() as c:
            source={r['id']:json.loads(r['payload']) for r in c.execute('SELECT id,payload FROM reviews WHERE project_id=?',(job['project_id'],))}
        rows=[source[rid] for rid in parameters['review_ids']]
        if job['mode']=='llm' and os.getenv('RADAR_PAID_ENABLED','false').lower() != 'true':
            raise ValueError('付费模型未启用，任务未发出请求。')
        data=engine.analyze_reviews(rows,mode=job['mode'],clusters=parameters['clusters'],progress=progress,checkpoint=state)
        progress('保存结果',len(rows),len(rows))
        with db.connect() as c:
            c.execute("UPDATE jobs SET status='succeeded',stage='分析完成',result=?,checkpoint=?,lease=NULL,lease_until=0,updated_at=? WHERE id=? AND lease=? AND cancel=0 AND status='running'",
                (db.dump(data),db.dump(state),time.time(),jid,lease))
    except Cancelled:
        pass
    except Exception as exc:
        # Do not expose arbitrary exception text, request headers, or input data.
        message=str(exc) if isinstance(exc,ValueError) else '分析内部错误，请检查服务日志并重试；已保存断点保留。'
        for key in ('RADAR_API_KEY','RADAR_ADMIN_PASSWORD'):
            secret=os.getenv(key)
            if secret:
                message=message.replace(secret,'[已隐藏]')
        with db.connect() as c:
            c.execute("UPDATE jobs SET status='failed',stage='分析失败',error=?,checkpoint=?,lease=NULL,lease_until=0,updated_at=? WHERE id=? AND lease=? AND cancel=0 AND status='running'",
                (message[:1000],db.dump(state),time.time(),jid,lease))
    finally:
        stopped.set()
        thread.join(timeout=2)
        with db.connect() as c:
            c.execute("UPDATE jobs SET checkpoint=?,lease=NULL,lease_until=0 WHERE id=? AND lease=? AND status='cancelled'",(db.dump(state),jid,lease))
    return True


def main():
    db.init()
    runtime=Path(os.environ.get('RADAR_DATA_DIR', str(Path(__file__).resolve().parent.parent / 'runtime'))).resolve()
    runtime.mkdir(parents=True,exist_ok=True)
    heart=runtime / 'worker-heartbeat.json'
    stopped=threading.Event()
    def write_heartbeat():
        while True:
            temporary=runtime / f'worker-heartbeat-{os.getpid()}.tmp'
            temporary.write_text(json.dumps({'pid':os.getpid(),'time':time.time()}),encoding='utf-8')
            temporary.replace(heart)
            if stopped.wait(10):
                break
    monitor=threading.Thread(target=write_heartbeat,daemon=True)
    monitor.start()
    try:
        while True:
            if not run_once():
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        stopped.set()
        monitor.join(timeout=2)


if __name__ == '__main__':
    main()

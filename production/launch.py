"""Idempotent local startup. No secrets printed, no browser or system changes."""
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from dotenv import load_dotenv

ROOT=Path(__file__).resolve().parent
load_dotenv(ROOT/'.env')
RUNTIME=Path(os.environ.get('RADAR_DATA_DIR',str(ROOT/'runtime'))).resolve()
os.environ['RADAR_DATA_DIR']=str(RUNTIME)
os.environ.setdefault('RADAR_BUDGET_DB_PATH',str((ROOT/'runtime'/'budget.sqlite3').resolve()))
os.environ.setdefault('RADAR_FRONTEND_DIR',str(ROOT/'frontend/dist'))
RUNTIME.mkdir(parents=True,exist_ok=True)
HOST=os.environ.get('RADAR_HOST','127.0.0.1')
PORT=int(os.environ.get('RADAR_PORT','18522'))
URL=f'http://127.0.0.1:{PORT}'


def health():
    try:
        with urllib.request.urlopen(URL+'/api/health',timeout=2) as r:
            return json.load(r).get('service')=='consumer-signal-radar'
    except Exception:return False


def launch(name,args):
    with (RUNTIME/(name+'.log')).open('ab') as log:
        process=subprocess.Popen([sys.executable]+args,cwd=ROOT,env=os.environ.copy(),stdin=subprocess.DEVNULL,stdout=log,stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0,start_new_session=os.name!='nt')
    return process.pid


def process_alive(pid):
    """Treat a heartbeat as live only while its recorded process exists."""
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, TypeError, ValueError):
        return False


if __name__=='__main__':
    if not (ROOT/'frontend/dist/index.html').exists():
        raise SystemExit('Frontend build missing. Run npm.cmd run build in frontend.')
    pids={}
    if not health():
        pids['api']=launch('api',['-m','uvicorn','backend.server:app','--host',HOST,'--port',str(PORT)])
        for _ in range(40):
            if health():break
            time.sleep(.5)
        else:raise SystemExit('API failed to start. See runtime/api.log.')
    heartbeat=RUNTIME/'worker-heartbeat.json'
    try:
        state=json.loads(heartbeat.read_text())
        alive=time.time()-float(state['time'])<30 and process_alive(state['pid'])
    except Exception:alive=False
    if not alive:pids['worker']=launch('worker',['-m','backend.worker'])
    (RUNTIME/'launcher.json').write_text(json.dumps({'started_at':time.time(),'pids':pids,'url':URL}),encoding='utf-8')
    print('Consumer Signal Radar is ready: '+URL)

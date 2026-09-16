"""Start only this local MVP, without reading old credentials or opening windows."""
import json
import os
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PYTHON_CANDIDATES = [
    ROOT / ".venv" / "Scripts" / "python.exe",
    ROOT.parent / ".venv" / "Scripts" / "python.exe",
]
PYTHON = next((path for path in PYTHON_CANDIDATES if path.is_file()), PYTHON_CANDIDATES[0])
PORT = 18523
URL = f"http://127.0.0.1:{PORT}"
SERVICE = "consumer-insight-demo-2.0"


def healthy():
    try:
        with urllib.request.urlopen(URL + "/api/health", timeout=2) as response:
            return json.load(response).get("service") == SERVICE
    except (OSError, ValueError):
        return False


def main():
    if not PYTHON.is_file():
        raise SystemExit("Project Python environment is missing; see README.md.")
    if not (ROOT / "frontend" / "dist" / "index.html").is_file():
        raise SystemExit("Frontend build is missing; the build step must complete before launch.")
    if healthy():
        print("Demo MVP is ready: " + URL)
        return
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", PORT)) == 0:
            raise SystemExit("Port 18523 belongs to another service; no process was stopped.")
    runtime = ROOT / "runtime"
    runtime.mkdir(exist_ok=True)
    if not (ROOT / "frontend" / "public" / "snapshot.json").exists():
        subprocess.run([str(PYTHON), "-m", "backend.pipeline"], cwd=ROOT, check=True)
    with (runtime / "server.log").open("ab") as log:
        process = subprocess.Popen(
            [str(PYTHON), "-m", "uvicorn", "backend.server:app", "--host", "127.0.0.1", "--port", str(PORT)],
            cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            start_new_session=os.name != "nt",
        )
    for _ in range(60):
        if healthy():
            (runtime / "launcher.json").write_text(
                json.dumps({"service": SERVICE, "pid": process.pid, "port": PORT, "url": URL}, indent=2),
                encoding="utf-8",
            )
            print("Demo MVP is ready: " + URL)
            return
        if process.poll() is not None:
            raise SystemExit("Demo startup failed; inspect runtime/server.log.")
        time.sleep(0.5)
    raise SystemExit("Startup verification timed out; inspect runtime/server.log.")


if __name__ == "__main__":
    main()

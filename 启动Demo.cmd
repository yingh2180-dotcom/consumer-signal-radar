@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Python environment missing. See README.md
  pause
  exit /b 1
)
start "" http://127.0.0.1:18521
".venv\Scripts\python.exe" -m streamlit run app.py --server.address 127.0.0.1 --server.port 18521
pause

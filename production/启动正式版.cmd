@echo off
cd /d "%~dp0"
"..\.venv\Scripts\python.exe" configure.py
"..\.venv\Scripts\python.exe" launch.py
if errorlevel 1 (
 pause
 exit /b 1
)
start "" http://127.0.0.1:18522

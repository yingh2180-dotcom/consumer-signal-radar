@echo off
cd /d "%~dp0"
"..\.venv\Scripts\python.exe" configure.py
notepad.exe .env

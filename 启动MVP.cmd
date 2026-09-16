@echo off
cd /d "%~dp0"
set "PYTHON=.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=..\.venv\Scripts\python.exe"
"%PYTHON%" launch.py
if errorlevel 1 pause

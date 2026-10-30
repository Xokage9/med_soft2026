@echo off
cd /d "%~dp0"
if not exist certs\server.key .venv\Scripts\python.exe tools\make_certs.py --force
start "MedSoft API (8443)" .venv\Scripts\python.exe -m server
start "MedSoft Client (8444)" .venv\Scripts\python.exe client\serve.py
timeout /t 2 >nul
start "" https://localhost:8444/

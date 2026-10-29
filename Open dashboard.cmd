@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" "scripts\setup_dashboard.py"
) else (
  python "scripts\setup_dashboard.py"
)
if errorlevel 1 (
  pause
  exit /b 1
)
start "" "%~dp0dashboard\.local\merch-store.pbip"

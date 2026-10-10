@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  py -3.11 -m venv .venv 2>nul
  if not exist ".venv\Scripts\python.exe" py -3 -m venv .venv 2>nul
  if not exist ".venv\Scripts\python.exe" python -m venv .venv
)

".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 exit /b 1

echo.
echo Starting CiviSort at http://127.0.0.1:5000/
echo Seed data is created only when the database is empty.
".venv\Scripts\python.exe" app.py

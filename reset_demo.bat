@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run run.bat once first so .venv exists.
  exit /b 1
)
echo WARNING: this DELETES all reports, events, saved plans and photos in data\ and reseeds the synthetic demo.
set /p CONFIRM=Type RESET to continue: 
if /I not "%CONFIRM%"=="RESET" (
  echo Cancelled. Nothing was changed.
  exit /b 1
)
".venv\Scripts\python.exe" -m civisort.seed --reset
echo Done. Start the server with run.bat and open http://127.0.0.1:5000/

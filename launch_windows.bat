@echo off
REM Resume Intelligence Studio - Windows launcher. Double-click to start.
REM First run creates a private Python environment in .venv (needs internet once).
setlocal
cd /d "%~dp0"
set PY=
where py >nul 2>nul && (py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul && set PY=py -3)
if not defined PY (
  where python >nul 2>nul && (python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul && set PY=python)
)
if not defined PY (
  echo Resume Intelligence Studio needs Python 3.11 or newer. Install it from python.org and tick "Add python.exe to PATH".
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo Setting up Resume Intelligence Studio ^(first run only^)...
  %PY% -m venv .venv || goto :fail
  ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :fail
)
start "" ".venv\Scripts\pythonw.exe" run_application.py %*
exit /b 0
:fail
echo Setup failed. See the messages above, or docs\TROUBLESHOOTING.md.
pause
exit /b 1

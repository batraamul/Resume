#!/bin/bash
# Resume Intelligence Studio — macOS launcher. Double-click in Finder.
# First run creates a private Python environment in ./.venv (needs internet once); later runs start immediately.
set -e
cd "$(dirname "$0")"
PY=""
for c in python3.13 python3.12 python3.11 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then
  osascript -e 'display dialog "Resume Intelligence Studio needs Python 3.11 or newer. Install it from python.org, then double-click this launcher again." buttons {"OK"} with icon caution' || true
  exit 1
fi
if [ ! -x ".venv/bin/python" ]; then
  echo "Setting up Resume Intelligence Studio (first run only)…"
  "$PY" -m venv .venv
  .venv/bin/python -m pip install --upgrade pip >/dev/null
  .venv/bin/python -m pip install -r requirements.txt
fi
exec .venv/bin/python run_application.py "$@"

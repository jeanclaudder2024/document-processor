#!/bin/bash
# Fix "address already in use" (port 8000) and restart the Document API
# Use when: pm2 restart fails, API keeps crashing with Errno 98
# Run from project root or document-processor: bash VPS_FIX_PORT_8000_AND_RESTART.sh
# If API runs as root, run: sudo bash VPS_FIX_PORT_8000_AND_RESTART.sh

set -e
echo "=============================================="
echo "  Fix Port 8000 + Restart Document API"
echo "=============================================="

# 1. Stop and remove pm2 apps that run the API (avoids duplicate binds)
echo ""
echo "1. Stopping pm2 API apps..."
for app in python-api python-a document-processor petrodealhub-api; do
  if pm2 describe "$app" &>/dev/null; then
    echo "   Stopping & deleting: $app"
    pm2 stop "$app" 2>/dev/null || true
    pm2 delete "$app" 2>/dev/null || true
  fi
done
pm2 save 2>/dev/null || true
echo "   Done."

# 2. Kill whatever is on port 8000
echo ""
echo "2. Freeing port 8000..."
PIDS=""
if command -v lsof &>/dev/null; then
  PIDS=$(lsof -ti:8000 2>/dev/null || true)
fi
if [ -z "$PIDS" ] && command -v fuser &>/dev/null; then
  PIDS=$(fuser -n tcp 8000 2>/dev/null || true)
fi
if [ -z "$PIDS" ] && command -v ss &>/dev/null; then
  PIDS=$(ss -tlnp 2>/dev/null | grep ':8000' | grep -oP 'pid=\K[0-9]+' | tr '\n' ' ' || true)
fi
if [ -n "$PIDS" ]; then
  for pid in $PIDS; do
    echo "   Killing PID $pid on port 8000"
    kill -9 "$pid" 2>/dev/null || true
  done
  sleep 2
else
  echo "   No process found on 8000."
fi

# 3. Double-check port is free
echo ""
echo "3. Verifying port 8000 is free..."
if lsof -ti:8000 &>/dev/null; then
  echo "   WARNING: Port 8000 still in use:"
  lsof -i:8000 2>/dev/null || true
  echo "   Run: sudo lsof -i:8000 then sudo kill -9 <PID>"
  exit 1
fi
echo "   Port 8000 is free."

# 4. Start API with pm2
DOC_DIR="${DOC_DIR:-/opt/petrodealhub/document-processor}"
if [ ! -d "$DOC_DIR" ]; then
  DOC_DIR="$(cd "$(dirname "$0")" && pwd)"
fi
if [ ! -f "$DOC_DIR/main.py" ]; then
  echo ""
  echo "   Project dir not found: $DOC_DIR"
  echo "   Set DOC_DIR or run from document-processor."
  exit 1
fi

echo ""
echo "4. Starting API (pm2)..."
cd "$DOC_DIR"
PYTHON="venv/bin/python"
[ -x "$PYTHON" ] || PYTHON="$(command -v python3 || command -v python)"
pm2 start "$PYTHON" --name "python-api" -- main.py
pm2 save
sleep 3

# 5. Health check
echo ""
echo "5. Health check..."
if curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:8000/health" 2>/dev/null | grep -q 200; then
  echo "   API is up: http://127.0.0.1:8000/health"
else
  echo "   API may still be starting. Check: pm2 logs python-api"
fi

echo ""
echo "=============================================="
echo "  Done. View logs: pm2 logs python-api"
echo "=============================================="

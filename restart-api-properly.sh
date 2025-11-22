#!/bin/bash
# Properly restart the API - handles port conflicts

echo "🔄 Restarting API..."

# Method 1: Try systemd service first
if systemctl is-active --quiet petrodealhub-api 2>/dev/null; then
    echo "✅ Found systemd service: petrodealhub-api"
    echo "🛑 Stopping service..."
    sudo systemctl stop petrodealhub-api
    sleep 2
    echo "▶️ Starting service..."
    sudo systemctl start petrodealhub-api
    sleep 2
    echo "📊 Service status:"
    sudo systemctl status petrodealhub-api --no-pager -l
    exit 0
fi

# Method 2: Try document-processor service
if systemctl is-active --quiet document-processor 2>/dev/null; then
    echo "✅ Found systemd service: document-processor"
    echo "🛑 Stopping service..."
    sudo systemctl stop document-processor
    sleep 2
    echo "▶️ Starting service..."
    sudo systemctl start document-processor
    sleep 2
    echo "📊 Service status:"
    sudo systemctl status document-processor --no-pager -l
    exit 0
fi

# Method 3: Kill process on port 8000
echo "🔍 Checking for process on port 8000..."
PID=$(sudo lsof -ti:8000 2>/dev/null)
if [ ! -z "$PID" ]; then
    echo "🛑 Found process $PID on port 8000, killing it..."
    sudo kill -9 $PID 2>/dev/null
    sleep 2
fi

# Method 4: Kill Python processes that might be the API
echo "🔍 Checking for Python processes..."
PYTHON_PIDS=$(ps aux | grep -E "python.*main\.py|uvicorn.*main" | grep -v grep | awk '{print $2}')
if [ ! -z "$PYTHON_PIDS" ]; then
    echo "🛑 Found Python processes: $PYTHON_PIDS"
    for pid in $PYTHON_PIDS; do
        echo "   Killing PID $pid..."
        sudo kill -9 $pid 2>/dev/null
    done
    sleep 2
fi

# Verify port is free
if sudo lsof -ti:8000 >/dev/null 2>&1; then
    echo "❌ Port 8000 is still in use!"
    echo "📋 Processes on port 8000:"
    sudo lsof -i:8000
    exit 1
fi

echo "✅ Port 8000 is now free"
echo "▶️ Starting API..."

# Navigate to directory
cd /opt/petrodealhub/document-processor || exit 1

# Activate venv if exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Start API in background
nohup python main.py > /tmp/api.log 2>&1 &
NEW_PID=$!

sleep 3

# Check if it started
if ps -p $NEW_PID > /dev/null; then
    echo "✅ API started successfully (PID: $NEW_PID)"
    echo "📋 Logs: tail -f /tmp/api.log"
    echo "📋 Health check: curl http://localhost:8000/health"
else
    echo "❌ API failed to start. Check /tmp/api.log"
    tail -20 /tmp/api.log
    exit 1
fi


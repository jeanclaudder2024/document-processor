#!/bin/bash
# Find and restart the API - works with systemd, nginx, or manual processes
# Usage: bash find-and-restart-api.sh

echo "🔍 Finding how the API is running..."
echo "===================================="

# Check if running as systemd service
echo ""
echo "1️⃣ Checking systemd services..."
SERVICES=("document-processor" "petrodealhub-api" "python-api" "document-processor-api")
FOUND_SERVICE=""

for service in "${SERVICES[@]}"; do
    if systemctl list-units --type=service --all | grep -q "$service"; then
        if systemctl is-active --quiet "$service" 2>/dev/null; then
            FOUND_SERVICE="$service"
            echo "✅ Found active service: $service"
            break
        elif systemctl is-enabled --quiet "$service" 2>/dev/null; then
            echo "ℹ️  Found service (not active): $service"
        fi
    fi
done

if [ -n "$FOUND_SERVICE" ]; then
    echo ""
    echo "🔄 Restarting service: $FOUND_SERVICE"
    sudo systemctl restart "$FOUND_SERVICE"
    sleep 2
    sudo systemctl status "$FOUND_SERVICE" --no-pager -l | head -20
    echo ""
    echo "✅ Service restarted!"
    echo "📋 View logs: sudo journalctl -u $FOUND_SERVICE -f"
    exit 0
fi

# Check if running as a process on port 8000
echo ""
echo "2️⃣ Checking for process on port 8000..."
if lsof -ti:8000 > /dev/null 2>&1; then
    PID=$(lsof -ti:8000)
    PROCESS=$(ps -p $PID -o comm= 2>/dev/null || echo "unknown")
    echo "✅ Found process on port 8000: PID=$PID, Process=$PROCESS"
    
    # Check if it's a Python process
    if echo "$PROCESS" | grep -q "python"; then
        echo ""
        echo "🔄 Restarting Python API process..."
        
        # Find the working directory
        WORK_DIR=$(pwdx $PID 2>/dev/null | awk '{print $2}' || lsof -p $PID 2>/dev/null | grep cwd | awk '{print $NF}')
        
        if [ -n "$WORK_DIR" ] && [ -f "$WORK_DIR/main.py" ]; then
            echo "   Working directory: $WORK_DIR"
            
            # Kill the process
            echo "   Stopping process $PID..."
            kill -9 $PID 2>/dev/null || true
            sleep 2
            
            # Start it again
            echo "   Starting API..."
            cd "$WORK_DIR"
            
            # Check for venv
            if [ -f "venv/bin/python" ]; then
                nohup venv/bin/python main.py > /tmp/api.log 2>&1 &
                NEW_PID=$!
                echo "   ✅ API started with PID: $NEW_PID"
            elif [ -f "../venv/bin/python" ]; then
                nohup ../venv/bin/python main.py > /tmp/api.log 2>&1 &
                NEW_PID=$!
                echo "   ✅ API started with PID: $NEW_PID"
            else
                # Try to find python
                PYTHON_CMD=$(which python3 || which python)
                if [ -n "$PYTHON_CMD" ]; then
                    nohup $PYTHON_CMD main.py > /tmp/api.log 2>&1 &
                    NEW_PID=$!
                    echo "   ✅ API started with PID: $NEW_PID"
                else
                    echo "   ❌ Could not find Python. Please start manually."
                    exit 1
                fi
            fi
            
            sleep 3
            if ps -p $NEW_PID > /dev/null 2>&1; then
                echo "   ✅ API is running!"
                echo "   📋 View logs: tail -f /tmp/api.log"
            else
                echo "   ⚠️  API may have failed to start. Check logs: tail -f /tmp/api.log"
            fi
        else
            echo "   ⚠️  Could not determine working directory. Please restart manually."
        fi
        exit 0
    fi
fi

# Check for Python processes running main.py
echo ""
echo "3️⃣ Checking for Python processes running main.py..."
PYTHON_PIDS=$(ps aux | grep "[p]ython.*main.py" | awk '{print $2}')
if [ -n "$PYTHON_PIDS" ]; then
    echo "✅ Found Python processes: $PYTHON_PIDS"
    for PID in $PYTHON_PIDS; do
        WORK_DIR=$(pwdx $PID 2>/dev/null | awk '{print $2}' || lsof -p $PID 2>/dev/null | grep cwd | awk '{print $NF}')
        echo "   PID $PID in directory: $WORK_DIR"
        
        if [ -f "$WORK_DIR/main.py" ]; then
            echo "   🔄 Restarting PID $PID..."
            kill -9 $PID 2>/dev/null || true
            sleep 2
            
            cd "$WORK_DIR"
            if [ -f "venv/bin/python" ]; then
                nohup venv/bin/python main.py > /tmp/api.log 2>&1 &
            else
                PYTHON_CMD=$(which python3 || which python)
                nohup $PYTHON_CMD main.py > /tmp/api.log 2>&1 &
            fi
            echo "   ✅ Restarted!"
        fi
    done
    exit 0
fi

# If nothing found, try to start it
echo ""
echo "4️⃣ No running API found. Attempting to start..."
PROJECT_DIRS=("/opt/petrodealhub/document-processor" "$HOME/aivessel-trade-flow-main/document-processor" "$HOME/aivessel-trade-flow/document-processor")

for DIR in "${PROJECT_DIRS[@]}"; do
    if [ -d "$DIR" ] && [ -f "$DIR/main.py" ]; then
        echo "✅ Found project directory: $DIR"
        cd "$DIR"
        
        if [ -f "venv/bin/python" ]; then
            echo "   Starting with venv..."
            nohup venv/bin/python main.py > /tmp/api.log 2>&1 &
            NEW_PID=$!
        else
            PYTHON_CMD=$(which python3 || which python)
            echo "   Starting with $PYTHON_CMD..."
            nohup $PYTHON_CMD main.py > /tmp/api.log 2>&1 &
            NEW_PID=$!
        fi
        
        sleep 3
        if ps -p $NEW_PID > /dev/null 2>&1; then
            echo "   ✅ API started with PID: $NEW_PID"
            echo "   📋 View logs: tail -f /tmp/api.log"
        else
            echo "   ⚠️  API may have failed. Check logs: tail -f /tmp/api.log"
        fi
        exit 0
    fi
done

echo ""
echo "❌ Could not find API or project directory."
echo "   Please check:"
echo "   1. Is the API running? Check: ps aux | grep python"
echo "   2. Is it on port 8000? Check: lsof -i :8000"
echo "   3. Where is the project? Check: find /opt /home -name main.py 2>/dev/null"



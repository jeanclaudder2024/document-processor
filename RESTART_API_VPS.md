# How to Restart API on VPS

## Quick Restart (Recommended)

```bash
cd /opt/petrodealhub/document-processor
git pull origin master
bash restart-api-properly.sh
```

## Manual Restart Methods

### Method 1: Using Systemd Service (if configured)

```bash
# Check service name
sudo systemctl list-units | grep -E "petrodealhub|document-processor"

# Stop and start
sudo systemctl stop petrodealhub-api
# OR
sudo systemctl stop document-processor

sudo systemctl start petrodealhub-api
# OR  
sudo systemctl start document-processor

# Check status
sudo systemctl status petrodealhub-api
```

### Method 2: Kill Process on Port 8000

```bash
# Find process using port 8000
sudo lsof -i:8000

# Kill it
sudo kill -9 $(sudo lsof -ti:8000)

# Start API
cd /opt/petrodealhub/document-processor
source venv/bin/activate  # if venv exists
nohup python main.py > /tmp/api.log 2>&1 &
```

### Method 3: Kill All Python Processes (Last Resort)

```bash
# Find Python processes
ps aux | grep python | grep main.py

# Kill them
sudo pkill -f "python.*main.py"

# Wait a moment
sleep 2

# Start API
cd /opt/petrodealhub/document-processor
source venv/bin/activate
nohup python main.py > /tmp/api.log 2>&1 &
```

## View Logs

```bash
# If using systemd:
sudo journalctl -u petrodealhub-api -f
# OR
sudo journalctl -u document-processor -f

# If running manually:
tail -f /tmp/api.log
```

## Verify API is Running

```bash
# Check health
curl http://localhost:8000/health

# Check if port is in use
sudo lsof -i:8000

# Check process
ps aux | grep python | grep main.py
```


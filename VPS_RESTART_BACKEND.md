# How to Restart the Backend on VPS

## Check How Backend is Running

First, check what's running the backend:

```bash
# Check if PM2 is running it
pm2 list

# Check if there's a process running on port 8000
sudo lsof -i :8000
# OR
sudo netstat -tlnp | grep 8000

# Check if uvicorn is running
ps aux | grep uvicorn
ps aux | grep python | grep main.py
```

## Restart Options

### Option 1: If using PM2
```bash
pm2 restart python-api
# OR
pm2 restart petrodealhub-api
# OR
pm2 restart all
```

### Option 2: If using systemd (but service not found)
```bash
# Check if service exists with different name
systemctl list-units | grep -i document
systemctl list-units | grep -i python
systemctl list-units | grep -i api

# If found, restart it:
sudo systemctl restart <service-name>
```

### Option 3: If running manually
```bash
# Find the process
ps aux | grep "python.*main.py"

# Kill it
kill <PID>

# Restart it
cd /opt/petrodealhub/document-processor
source venv/bin/activate
nohup python main.py > /dev/null 2>&1 &
```

### Option 4: Create systemd service (if needed)
```bash
cd /opt/petrodealhub/document-processor
bash create-document-processor-service.sh
# Then restart:
sudo systemctl restart document-processor
```

## Quick Restart (Try This First)

```bash
# Try PM2 first (most common)
pm2 restart all

# If that doesn't work, try finding and restarting manually
cd /opt/petrodealhub/document-processor
source venv/bin/activate
pkill -f "python.*main.py"  # Kill existing
nohup uvicorn main:app --host 0.0.0.0 --port 8000 > /tmp/api.log 2>&1 &
```

## Verify It's Running

```bash
# Check if API responds
curl http://localhost:8000/health

# Check logs
tail -f /tmp/api.log
# OR if using PM2
pm2 logs python-api
```


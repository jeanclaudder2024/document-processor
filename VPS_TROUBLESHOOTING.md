# VPS Troubleshooting Guide

## 502 Bad Gateway Error

This means nginx is running but can't connect to the backend API.

### Quick Fix:

```bash
# 1. Check if the API service is running
sudo systemctl status petrodealhub-api

# 2. If it's not running or failed, restart it
sudo systemctl restart petrodealhub-api

# 3. Check the logs for errors
sudo journalctl -u petrodealhub-api -n 100 --no-pager

# 4. Check if the service is enabled to start on boot
sudo systemctl enable petrodealhub-api
```

### Common Issues:

#### Issue 1: Service crashed due to Python error
**Solution:**
```bash
# Check logs for Python errors
sudo journalctl -u petrodealhub-api -n 200 | grep -i "error\|traceback\|exception"

# Fix the error, then restart
sudo systemctl restart petrodealhub-api
```

#### Issue 2: Port conflict
**Solution:**
```bash
# Check what's using port 8000
sudo netstat -tlnp | grep 8000
# or
sudo lsof -i :8000

# Check nginx configuration
sudo nano /etc/nginx/sites-available/petrodealhub
# Make sure it's pointing to the correct backend (usually http://127.0.0.1:8000)
```

#### Issue 3: Service not starting
**Solution:**
```bash
# Check service file
sudo systemctl cat petrodealhub-api

# Try running manually to see errors
cd /opt/petrodealhub/document-processor
source venv/bin/activate
python main.py
```

#### Issue 4: Dependencies missing
**Solution:**
```bash
cd /opt/petrodealhub/document-processor
source venv/bin/activate
pip install -r requirements.txt
```

### Check Service Configuration:

```bash
# View service file
sudo cat /etc/systemd/system/petrodealhub-api.service

# Should look something like:
# [Unit]
# Description=PetrodealHub Python API
# After=network.target
#
# [Service]
# Type=simple
# User=root
# WorkingDirectory=/opt/petrodealhub/document-processor
# Environment="PATH=/opt/petrodealhub/document-processor/venv/bin"
# ExecStart=/opt/petrodealhub/document-processor/venv/bin/python main.py
# Restart=always
# RestartSec=10
#
# [Install]
# WantedBy=multi-user.target
```

### Restart Everything:

```bash
# Reload systemd
sudo systemctl daemon-reload

# Restart API service
sudo systemctl restart petrodealhub-api

# Check status
sudo systemctl status petrodealhub-api

# Restart nginx
sudo systemctl restart nginx

# Check nginx status
sudo systemctl status nginx
```

### Verify API is Working:

```bash
# Test API directly (bypass nginx)
curl http://localhost:8000/templates

# Test through nginx
curl https://petrodealhub.com/api/templates
```


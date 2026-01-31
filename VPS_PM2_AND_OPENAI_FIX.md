# VPS: Fix Port 8000 + OpenAI "proxies" Error

Use this when:
- PM2 logs show **`[Errno 98] address already in use`** on port 8000
- Logs show **`Client.__init__() got an unexpected keyword argument 'proxies'`**

---

## 1. Fix port 8000 and restart API (run on VPS)

```bash
cd /opt/petrodealhub/document-processor
sudo bash VPS_FIX_PORT_8000_AND_RESTART.sh
```

This script:
- Stops and removes PM2 app `python-api` (and similar names)
- Kills any process using port 8000
- Starts the API again with PM2

If you prefer to do it manually:

```bash
# Stop PM2 app
pm2 stop python-api
pm2 delete python-api

# Free port 8000 (Linux)
sudo lsof -ti:8000 | xargs -r sudo kill -9
# or: sudo fuser -k 8000/tcp

# Start API
cd /opt/petrodealhub/document-processor
pm2 start venv/bin/python --name python-api -- main.py
pm2 save
```

---

## 2. Fix OpenAI "proxies" error (httpx compatibility)

The error happens when **httpx >= 0.28** is installed; the OpenAI client still passes `proxies`, which httpx 0.28+ no longer accepts.

On the VPS, in the project venv:

```bash
cd /opt/petrodealhub/document-processor
source venv/bin/activate
pip install 'httpx>=0.24.0,<0.28.0'
# Or reinstall all deps from requirements (includes the pin):
pip install -r requirements.txt
```

Then restart the API:

```bash
pm2 restart python-api
```

---

## 3. Check that it works

```bash
pm2 logs python-api --lines 30
curl -s http://127.0.0.1:8000/health
```

You should see the API start without "address already in use" and without the "proxies" warning (or with OpenAI client initializing if the key is set).

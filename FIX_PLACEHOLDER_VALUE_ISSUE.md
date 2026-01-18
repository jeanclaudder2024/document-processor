# Fix: Placeholders Still Showing "Value-XXXX"

## The Real Problem

The placeholders are still generating "Value-XXXX" instead of realistic data. This is **NOT related to plan saving** - it's a placeholder data generation issue.

## Root Cause

The API code has been fixed, but:
1. **API might not be restarted** after code update
2. **OpenAI might not be configured** (so it falls back to standard random)
3. **Placeholder settings in CMS might be wrong**

## Step-by-Step Fix

### Step 1: Verify API Has Latest Code

```bash
# On VPS
cd /opt/petrodealhub/document-processor
git log --oneline -5
# Should see commit: "Fix specific placeholder types (VIA, POSITION, BIN, OKPO)"
```

If not, pull latest:
```bash
git pull origin master
```

### Step 2: Restart API (CRITICAL)

```bash
# Find and restart API
cd /opt/petrodealhub/document-processor
bash find-and-restart-api.sh

# OR manually:
sudo systemctl restart document-processor
# OR
PID=$(sudo lsof -ti:8000) && sudo kill -9 $PID && sleep 2 && nohup venv/bin/python main.py > /tmp/api.log 2>&1 &
```

### Step 3: Verify API is Working

```bash
# Test health endpoint
curl http://localhost:8000/health

# Check OpenAI status
curl http://localhost:8000/health | grep -i openai
```

### Step 4: Check OpenAI Configuration

```bash
# Check if OPENAI_API_KEY is set
cd /opt/petrodealhub/document-processor
grep OPENAI_API_KEY .env

# If not set, add it:
echo "OPENAI_API_KEY=your-key-here" >> .env
# Then restart API
```

### Step 5: Check CMS Placeholder Settings

1. Open CMS: `http://your-server:8000/cms/editor.html?template_id=YOUR_TEMPLATE_ID`
2. For each placeholder showing "Value-XXXX":
   - Set Source to: **Random**
   - Set Random Mode to: **AI Generated (using OpenAI) - Default**
3. Click **Save Placeholder Settings**

### Step 6: Test Generation

Generate a document and check if placeholders are now realistic:
- VIA → Should be company name
- POSITION → Should be job title  
- BIN → Should be 12-digit number
- OKPO → Should be 8-10 digit number

## Why Plan Save Logic is NOT the Problem

The plan save function (`savePlan`) only saves:
- Template permissions (which templates a plan can access)
- Download limits
- Plan features

It does **NOT** affect:
- Placeholder data generation
- How placeholders are filled
- Random data generation

These are completely separate systems.

## If Still Not Working

Check API logs for errors:

```bash
# If systemd:
sudo journalctl -u document-processor -f | grep -i "placeholder\|via\|position\|value-"

# If manual:
tail -f /tmp/api.log | grep -i "placeholder\|via\|position\|value-"
```

Look for:
- "AI generated value" messages (good - AI is working)
- "OpenAI not available" warnings (bad - need to configure OpenAI)
- "Value-XXXX" in logs (bad - fallback is being used)

## Quick Fix Command

```bash
# On VPS - one command to fix everything:
cd /opt/petrodealhub/document-processor && \
git pull origin master && \
(sudo systemctl restart document-processor 2>/dev/null || \
 (PID=$(sudo lsof -ti:8000) && sudo kill -9 $PID && sleep 2 && \
  nohup venv/bin/python main.py > /tmp/api.log 2>&1 &)) && \
sleep 3 && \
curl http://localhost:8000/health
```


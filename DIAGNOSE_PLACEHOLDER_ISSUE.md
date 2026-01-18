# Diagnosing Placeholder "Value-XXXX" Issue

## The Real Problem

You're still seeing placeholders like:
- `VIA: Value-4549`
- `POSITION: Value-2726`
- `BIN: Value-2134`
- `OKPO: Value-4658`

## Root Cause Analysis

### 1. Check if API is Using Latest Code

The fixes I made should handle these placeholders. Verify the API has the latest code:

```bash
# On VPS
cd /opt/petrodealhub/document-processor
git log --oneline -5
# Should see: "Fix specific placeholder types (VIA, POSITION, BIN, OKPO)"
```

### 2. Check if API is Actually Restarted

```bash
# Check when API last started
ps aux | grep "[p]ython.*main.py" | head -1

# Check API logs for placeholder generation
sudo journalctl -u document-processor -n 100 | grep -i "placeholder\|value-"
# OR if manual process:
tail -100 /tmp/api.log | grep -i "placeholder\|value-"
```

### 3. Test Placeholder Generation Directly

```bash
# Test the API endpoint
curl -X POST http://localhost:8000/generate-document \
  -H "Content-Type: application/json" \
  -d '{
    "template_id": "YOUR_TEMPLATE_ID",
    "vessel_imo": "1234567"
  }' \
  --output test-document.pdf

# Check logs to see what values were generated
```

### 4. Check CMS Placeholder Settings

The issue might be that placeholders are set to use "random" but not "AI":

1. Open CMS editor for the template
2. Check each placeholder's "Random Mode" setting
3. Should be set to "AI Generated (using OpenAI)" - Default
4. If it's set to "Auto" or "Fixed", change it to "AI"

### 5. Check OpenAI Configuration

```bash
# On VPS, check if OpenAI is configured
cd /opt/petrodealhub/document-processor
grep -i "OPENAI" .env 2>/dev/null || echo "No .env file or OPENAI not set"

# Check API logs for OpenAI errors
sudo journalctl -u document-processor -n 200 | grep -i "openai\|ai.*not\|falling back"
```

## Most Likely Issues

### Issue 1: API Not Restarted After Code Update
**Solution:** Restart the API properly (see RESTART_API_NO_PM2.md)

### Issue 2: OpenAI Not Configured
**Solution:** Set OPENAI_API_KEY in .env file

### Issue 3: Placeholders Set to Wrong Mode
**Solution:** In CMS, set all placeholders to "AI Generated" mode

### Issue 4: Code Not Pulled on VPS
**Solution:** 
```bash
cd /opt/petrodealhub/document-processor
git pull origin master
# Then restart API
```

## Quick Diagnostic Commands

```bash
# 1. Check if latest code is on VPS
cd /opt/petrodealhub/document-processor
git log --oneline -1

# 2. Check API is running
curl http://localhost:8000/health

# 3. Check OpenAI status
curl http://localhost:8000/health | grep -i openai

# 4. Check placeholder generation in logs
sudo journalctl -u document-processor -f | grep -i "placeholder\|via\|position\|bin\|okpo"
```

## Next Steps

1. **First:** Verify API has latest code and is restarted
2. **Second:** Check OpenAI is configured
3. **Third:** Test with a simple placeholder
4. **Fourth:** Check CMS settings for that placeholder


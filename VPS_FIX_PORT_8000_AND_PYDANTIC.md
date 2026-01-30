# Fix Port 8000 "Already in Use" + Pydantic Schema Error

## 1. Port 8000 already in use (`Errno 98`)

**Symptom:** API fails to start with:
```text
ERROR: [Errno 98] error while attempting to bind on address ('0.0.0.0', 8000): address already in use
```

**Cause:** An old API process (or another app) is still using port 8000. Restarting via pm2 can spawn a new process before the old one releases the port.

**Fix:** Run the script (from project root or `document-processor`):

```bash
cd /opt/petrodealhub/document-processor
bash VPS_FIX_PORT_8000_AND_RESTART.sh
```

The script will:

1. Stop and remove pm2 apps: `python-api`, `python-a`, `document-processor`, `petrodealhub-api`
2. Kill any process on port 8000
3. Verify port 8000 is free
4. Start the API with pm2 as `python-api`
5. Run a quick health check

**Manual steps (if you prefer):**

```bash
pm2 stop python-api python-a 2>/dev/null; pm2 delete python-api python-a 2>/dev/null
pm2 save
lsof -ti:8000 | xargs -r kill -9
sleep 2
cd /opt/petrodealhub/document-processor
pm2 start venv/bin/python --name python-api -- main.py
pm2 save
pm2 logs python-api --lines 30
```

---

## 2. Pydantic schema error (Union / model)

**Symptom:** At startup, Python raises during schema generation:
```text
File "pydantic/_internal/_generate_schema.py" ...
  return self._match_generic_type(obj, origin)
  return self._union_schema(obj, ...)
```

**Cause:** FastAPI/Pydantic generating OpenAPI schema for `Body(...)` with a raw `Dict` can trigger this in some versions.

**Fix applied:** The `/templates/{template_id}/metadata` endpoint no longer uses `payload: Dict = Body(...)`. It now uses `Request` + `await request.json()`, so no body schema is generated. The endpoint behaviour is unchanged.

---

## 3. OpenAI key warning

**Symptom:** Logs show:
```text
WARNING: OpenAI API key not configured ... AI-powered placeholder matching will be disabled.
```

**Meaning:** AI-based placeholder mapping on upload is off. Upload and document generation still work; placeholder suggestions will use rules only.

**Optional:** Set `OPENAI_API_KEY` in `.env` or store `openai_api_key` in Supabase `system_settings` to enable AI placeholder matching.

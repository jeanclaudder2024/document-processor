# Forget / remove a template by name (e.g. "SGS ANALYSIS REPORT")

Use when a template **is not in the database**, causes problems, and you **cannot delete** it via the UI or normal delete API.

The **forget** endpoint marks the template as deleted and cleans config (placeholder_settings, metadata, plans). It does **not** touch Supabase or local files.

---

## 1. Call `POST /templates/forget` with JSON body

**Local (document-processor on port 8000):**

```bash
curl -s -X POST "http://127.0.0.1:8000/templates/forget" \
  -H "Content-Type: application/json" \
  -d '{"name": "SGS ANALYSIS REPORT"}' \
  -b "session=YOUR_SESSION_COOKIE"
```

**VPS (API behind Nginx, often `/api` prefix):**

```bash
curl -s -X POST "https://your-domain.com/api/templates/forget" \
  -H "Content-Type: application/json" \
  -d '{"name": "SGS ANALYSIS REPORT"}' \
  -b "session=YOUR_SESSION_COOKIE"
```

Replace `YOUR_SESSION_COOKIE` with a valid session cookie (from browser after logging in to the Document API, or from a prior login response).

---

## 2. Get a session cookie (if needed)

1. Log in:
   ```bash
   curl -s -X POST "http://127.0.0.1:8000/auth/login" \
     -H "Content-Type: application/json" \
     -d '{"username":"admin","password":"admin123"}' \
     -c cookies.txt -v
   ```
2. Use `-b cookies.txt` when calling `/templates/forget`, or copy the `session` value from `cookies.txt` into `-b "session=..."`.

---

## 3. Alternative: `template_name` in body

You can also send `template_name` instead of `name`:

```json
{"template_name": "SGS ANALYSIS REPORT"}
```

---

## 4. Result

On success you get something like:

```json
{
  "success": true,
  "message": "Template 'SGS ANALYSIS REPORT' forgotten (marked deleted, config cleaned)",
  "removed_from_placeholder_settings": true,
  "removed_from_metadata": false,
  "plans_updated": true
}
```

The template is then excluded from the templates list (via `deleted_templates.json`) and removed from placeholder settings, metadata, and plans where it was referenced.

# Fix RLS (Row-Level Security) Issue

## Problem
The error `'new row violates row-level security policy for table "plan_template_permissions"'` occurs because the Supabase client is using the **anon key** which is subject to Row-Level Security (RLS) policies.

## Solution
Use the **service_role key** for backend operations. The service_role key bypasses RLS policies and has full database access.

## Steps to Fix

### 1. Get Your Service Role Key
1. Go to your Supabase project dashboard
2. Go to **Settings** → **API**
3. Find **service_role** key (NOT the anon key)
4. Copy it

### 2. Set Environment Variable on VPS

On your VPS, add the service role key to your environment:

```bash
# Edit your .env file or systemd service file
sudo nano /etc/systemd/system/petrodealhub-api.service
```

Add this line in the `[Service]` section:
```
Environment="SUPABASE_SERVICE_ROLE_KEY=your-service-role-key-here"
```

Or if using a `.env` file:
```bash
cd /opt/petrodealhub/document-processor
echo "SUPABASE_SERVICE_ROLE_KEY=your-service-role-key-here" >> .env
```

### 3. Restart the Service

```bash
sudo systemctl daemon-reload
sudo systemctl restart petrodealhub-api
```

### 4. Verify

Test saving a plan again. The RLS error should be gone and permissions should save successfully.

## Security Note

⚠️ **IMPORTANT**: The service_role key has full database access and bypasses all RLS policies. Keep it secret and never expose it in frontend code or client-side JavaScript. It should only be used in backend/server-side code.

## Alternative: Fix RLS Policies

If you prefer to keep using the anon key, you can modify the RLS policies in Supabase to allow inserts. However, using the service_role key for backend operations is the recommended approach.


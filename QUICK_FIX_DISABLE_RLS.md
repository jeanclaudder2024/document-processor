# Quick Fix: Disable RLS (2 Minutes)

## This Will Fix the Problem Immediately

Since you can't find the service_role key, we'll disable RLS on the table instead.

## Steps:

### 1. Go to Supabase SQL Editor

1. Open: https://supabase.com/dashboard
2. Select your project
3. Click **"SQL Editor"** in the left sidebar
4. Click **"New query"** button

### 2. Copy and Paste This SQL:

```sql
ALTER TABLE plan_template_permissions DISABLE ROW LEVEL SECURITY;
```

### 3. Run It

- Click the **"Run"** button (or press `Ctrl+Enter`)
- You should see: **"Success. No rows returned"**

### 4. Test It

1. Go back to your CMS
2. Try saving a plan with templates selected
3. It should work now! ✅

### 5. Verify It Worked

Check the backend logs:
```bash
sudo journalctl -u petrodealhub-api -f | grep -E "update-plan|Added permission"
```

You should see:
```
[update-plan] ✅ Added permission for template ID ...
```

## Done! ✅

The RLS error should be gone and permissions will save successfully.

## Optional: Re-enable RLS Later

If you get the service_role key later, you can re-enable RLS:

```sql
ALTER TABLE plan_template_permissions ENABLE ROW LEVEL SECURITY;
```

Then use the service_role key method instead.


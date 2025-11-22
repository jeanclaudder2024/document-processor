# Alternative Fix: Disable RLS on plan_template_permissions Table

## If You Can't Get Service Role Key

If you can't access the service_role key, we can disable RLS on the `plan_template_permissions` table instead.

## ⚠️ Warning
This is **less secure** than using the service_role key, but it will work.

## Steps

### 1. Go to Supabase SQL Editor

1. Open your Supabase project dashboard
2. Click **"SQL Editor"** in the left sidebar
3. Click **"New query"**

### 2. Run This SQL Command

```sql
-- Disable RLS on plan_template_permissions table
ALTER TABLE plan_template_permissions DISABLE ROW LEVEL SECURITY;
```

### 3. Click "Run" or press Ctrl+Enter

### 4. Verify It Worked

You should see: "Success. No rows returned"

### 5. Test Saving Plan

Try saving a plan in the CMS - it should work now!

## Re-enable RLS Later (Optional)

If you want to re-enable RLS later (after getting service_role key):

```sql
ALTER TABLE plan_template_permissions ENABLE ROW LEVEL SECURITY;
```

## Which Method is Better?

- **Service Role Key** ✅ - More secure, recommended
- **Disable RLS** ⚠️ - Works but less secure

If you can get the service_role key, use that. Otherwise, disabling RLS will work.


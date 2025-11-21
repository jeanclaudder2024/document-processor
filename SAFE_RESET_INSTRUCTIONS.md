# Safe Plan Permissions Reset Instructions

## ⚠️ IMPORTANT: What This Does

The `reset_plan_permissions.sql` script is **100% SAFE** for your client subscriptions.

### ✅ What It DOES (Safe Operations):
- Deletes template permission mappings (`plan_template_permissions`)
- Deletes broker template permission mappings (`broker_template_permissions`)
- **These are just configuration data, NOT subscription data**

### ✅ What It DOES NOT Touch (Your Client Data):
- ❌ **User subscriptions** (`public.subscriptions`) - UNTOUCHED
- ❌ **Client accounts** (`public.subscribers`) - UNTOUCHED  
- ❌ **Subscription plans** (`public.subscription_plans`) - UNTOUCHED
- ❌ **Payment information** (Stripe IDs, billing) - UNTOUCHED
- ❌ **User profiles** (`public.profiles`) - UNTOUCHED
- ❌ **User accounts** (`auth.users`) - UNTOUCHED

## What Happens After Reset

1. **Client subscriptions remain active** - All your clients keep their subscriptions
2. **Payment information preserved** - Stripe IDs, billing cycles, etc. all intact
3. **Plan definitions remain** - Basic, Professional, Enterprise plans still exist
4. **Only permissions are cleared** - You need to reconfigure which templates each plan can access

## How to Run Safely

### Option 1: Test First (Recommended)

```sql
-- First, check what will be deleted (read-only)
SELECT COUNT(*) FROM public.plan_template_permissions;
SELECT COUNT(*) FROM public.broker_template_permissions;

-- Verify your client data is safe (read-only)
SELECT COUNT(*) FROM public.subscriptions;
SELECT COUNT(*) FROM public.subscribers;
```

### Option 2: Run the Reset Script

```bash
# Connect to your Supabase database
psql -h your-db-host -U your-user -d your-database -f reset_plan_permissions.sql
```

Or run it in Supabase SQL Editor.

### Option 3: Manual Reset (Safest)

If you want to be extra careful, you can manually delete permissions for specific plans:

```sql
-- Delete permissions for a specific plan only
DELETE FROM public.plan_template_permissions 
WHERE plan_id = (SELECT id FROM public.subscription_plans WHERE plan_tier = 'basic');

-- Or delete all at once
DELETE FROM public.plan_template_permissions;
DELETE FROM public.broker_template_permissions;
```

## After Reset

1. Go to CMS → Subscription Plans tab
2. Edit each plan
3. Select which templates each plan can access
4. Save - the new system will use template IDs (more reliable)

## Verification

After running the script, verify your client data is intact:

```sql
-- Check subscriptions (should show all your clients)
SELECT COUNT(*) FROM public.subscriptions;

-- Check subscribers (should show all your clients)
SELECT COUNT(*) FROM public.subscribers;

-- Check plan definitions (should show 3 plans)
SELECT plan_tier, plan_name FROM public.subscription_plans;
```

All of these should show your existing data - nothing is deleted!

## Need Help?

If you're unsure, you can:
1. **Backup first**: Export your database before running
2. **Test on staging**: Run on a test database first
3. **Contact support**: If you need assistance

---

**Summary**: This reset is safe. It only clears permission mappings, not subscription data. Your clients' accounts and subscriptions remain completely untouched.


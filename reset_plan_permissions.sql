-- ============================================================================
-- SAFE RESET: Template Permissions ONLY
-- ============================================================================
-- ⚠️  IMPORTANT: This script ONLY clears template permission mappings
-- ✅  SAFE: Does NOT affect ANY existing tables or data
-- ✅  ONLY touches these 2 tables:
--     - plan_template_permissions (which templates each plan can access)
--     - broker_template_permissions (which templates broker membership can access)
--
-- This script does NOT touch:
--     - subscription_plans (plan definitions - Basic, Professional, Enterprise)
--     - Any user data, accounts, or subscriptions
--     - Any other tables
--
-- After running this, you can rebuild permissions from the CMS.
-- ============================================================================

-- STEP 1: Show current state (for verification)
SELECT 
    'BEFORE: plan_template_permissions' as info,
    COUNT(*) as row_count
FROM public.plan_template_permissions
UNION ALL
SELECT 
    'BEFORE: broker_template_permissions' as info,
    COUNT(*) as row_count
FROM public.broker_template_permissions;

-- STEP 2: Delete plan template permissions (SAFE - only permission mappings)
DELETE FROM public.plan_template_permissions;

-- STEP 3: Delete broker template permissions (SAFE - only permission mappings)
DELETE FROM public.broker_template_permissions;

-- STEP 4: Verify cleanup
SELECT 
    'AFTER: plan_template_permissions' as info,
    COUNT(*) as remaining_rows
FROM public.plan_template_permissions
UNION ALL
SELECT 
    'AFTER: broker_template_permissions' as info,
    COUNT(*) as remaining_rows
FROM public.broker_template_permissions;

-- ============================================================================
-- ✅ RESET COMPLETE
-- ============================================================================
-- All template permissions have been cleared.
-- Only template permission tables were touched.
-- All other tables (plans, subscriptions, accounts) are UNTOUCHED.
-- You can now rebuild permissions from the CMS.
-- ============================================================================


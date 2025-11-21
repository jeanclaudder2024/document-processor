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

-- STEP 5: Verify subscription_plans table is untouched (plan definitions)
-- This table contains your plan definitions (Basic, Professional, Enterprise)
-- We only verify it exists and is untouched - we don't modify it
SELECT 
    'VERIFICATION: subscription_plans table (plan definitions - UNTOUCHED)' as info,
    COUNT(*) as plan_definitions_count
FROM public.subscription_plans;

-- ============================================================================
-- ✅ RESET COMPLETE
-- ============================================================================
-- All template permissions have been cleared.
-- Client subscriptions and accounts are UNTOUCHED.
-- You can now rebuild permissions from the CMS.
-- ============================================================================


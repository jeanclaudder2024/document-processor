-- ============================================================================
-- SAFE RESET: Plan Template Permissions Only
-- ============================================================================
-- ⚠️  IMPORTANT: This script ONLY clears template permission mappings
-- ✅  SAFE: Does NOT affect:
--     - User subscriptions (public.subscriptions)
--     - Client accounts (public.subscribers)
--     - Subscription plans (public.subscription_plans)
--     - Payment information (Stripe IDs, billing, etc.)
--     - User data (profiles, accounts, etc.)
--
-- This script ONLY deletes:
--     - plan_template_permissions (which templates each plan can access)
--     - broker_template_permissions (which templates broker membership can access)
--
-- After running this, you can rebuild permissions from the CMS without affecting
-- any client subscriptions or accounts.
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

-- STEP 5: Verify client data is untouched (should show all your subscriptions)
SELECT 
    'VERIFICATION: subscriptions table (client accounts)' as info,
    COUNT(*) as client_count
FROM public.subscriptions
UNION ALL
SELECT 
    'VERIFICATION: subscribers table (client accounts)' as info,
    COUNT(*) as subscriber_count
FROM public.subscribers
UNION ALL
SELECT 
    'VERIFICATION: subscription_plans table (plan definitions)' as info,
    COUNT(*) as plan_definitions_count
FROM public.subscription_plans;

-- ============================================================================
-- ✅ RESET COMPLETE
-- ============================================================================
-- All template permissions have been cleared.
-- Client subscriptions and accounts are UNTOUCHED.
-- You can now rebuild permissions from the CMS.
-- ============================================================================


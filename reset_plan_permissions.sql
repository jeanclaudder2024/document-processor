-- Reset all plan template permissions
-- This script clears all plan permissions so you can rebuild them from scratch

-- Delete all plan template permissions
DELETE FROM public.plan_template_permissions;

-- Delete all broker template permissions  
DELETE FROM public.broker_template_permissions;

-- Optional: Reset plans to default state (all templates allowed)
-- Uncomment the lines below if you want to reset plans to allow all templates
-- UPDATE public.subscription_plans SET max_downloads_per_month = 10 WHERE max_downloads_per_month IS NULL;

-- Verify cleanup
SELECT 
    'plan_template_permissions' as table_name,
    COUNT(*) as remaining_rows
FROM public.plan_template_permissions
UNION ALL
SELECT 
    'broker_template_permissions' as table_name,
    COUNT(*) as remaining_rows
FROM public.broker_template_permissions;


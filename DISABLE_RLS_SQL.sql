-- Disable Row-Level Security on plan_template_permissions table
-- This allows the anon key to insert/update/delete permissions
-- Run this in Supabase SQL Editor

ALTER TABLE plan_template_permissions DISABLE ROW LEVEL SECURITY;

-- Verify it's disabled (optional check)
SELECT tablename, rowsecurity 
FROM pg_tables 
WHERE schemaname = 'public' 
AND tablename = 'plan_template_permissions';


# Debug Template Count Issue - Step by Step

## Problem
All plans show `can_download: []` (0 templates) even after saving templates.

## What to Check in Backend Logs

After pulling latest code and restarting API, check logs when:
1. **Saving a plan** - Look for these log messages:
   ```
   [update-plan] 🔍 Searching for plan: 'basic'
   [update-plan] ✅ Found plan by plan_tier: 'basic' -> plan_id (UUID): <UUID>
   [update-plan] 🗑️ Deleting existing permissions for plan_id <UUID>
   [update-plan] ✅ Deleted X existing permissions
   [update-plan] ✅ Added permission for template ID <TEMPLATE_ID> to plan_id <UUID>
   [update-plan] 📊 After save - Found X template permissions for plan basic
   ```

2. **Loading plans** - Look for these log messages:
   ```
   [plans-db] 🔍 Querying permissions for plan basic (ID: <UUID>)
   [plans-db] 📊 Query result: X permission records found
   [plans-db] Plan basic found X permission records
   [plans-db] ✅ Added template 'TEMPLATE_NAME.docx' (ID: <TEMPLATE_ID>) to allowed_templates
   ```

## Common Issues to Check

### Issue 1: Plan ID Mismatch
**Symptom**: Permissions saved with one plan_id, but queried with different plan_id

**Check**: Compare the UUIDs:
- When saving: `[update-plan] ✅ Found plan... UUID: <UUID1>`
- When reading: `[plans-db] 🔍 Querying permissions... (ID: <UUID2>)`

**Fix**: If UUIDs don't match, the plan lookup is wrong.

### Issue 2: Template ID Not in Template Map
**Symptom**: Permissions exist but templates not found in template_map

**Check**: Look for:
```
[plans-db] ❌ Template ID <TEMPLATE_ID> not found in template_map!
[plans-db] ❌ Available template IDs in map: [...]
```

**Fix**: Template might be inactive or deleted. Check if template exists in database.

### Issue 3: Permissions Not Being Saved
**Symptom**: No insert logs after save

**Check**: Look for:
```
[update-plan] ✅ Added permission for template ID...
```

If missing, the insert is failing silently.

### Issue 4: Permissions Being Deleted But Not Re-inserted
**Symptom**: Delete count > 0 but insert count = 0

**Check**: Compare:
```
[update-plan] ✅ Deleted X existing permissions
[update-plan] ✅ Added permission... (should see multiple of these)
```

## Quick Test

1. Edit a plan (e.g., "basic")
2. Select 2-3 templates
3. Save
4. Check backend logs for:
   - Plan UUID used when saving
   - Plan UUID used when reading
   - Number of permissions inserted
   - Number of permissions found when reading
   - Template IDs in permissions vs template IDs in template_map

## Expected Flow

1. **Save**: 
   - Find plan by plan_tier → get UUID
   - Delete old permissions for that UUID
   - Insert new permissions for that UUID
   - Query back permissions for that UUID → should find them

2. **Read**:
   - Get plan from subscription_plans → get UUID
   - Query permissions for that UUID
   - Map template_ids to file_names using template_map
   - Return file_names array

## If Still Not Working

Check the actual database:
```sql
-- Check if permissions exist
SELECT plan_id, template_id, can_download 
FROM plan_template_permissions 
WHERE plan_id = '<PLAN_UUID_FROM_LOGS>';

-- Check plan UUIDs
SELECT id, plan_tier, plan_name 
FROM subscription_plans 
WHERE is_active = true;

-- Check template IDs
SELECT id, file_name, is_active 
FROM document_templates;
```

Compare the plan_id in permissions with the id in subscription_plans - they must match!


# Plan Template Count Issue - Full Analysis

## Problem
After saving a plan with selected templates, the display shows "0 templates" instead of the correct count.

## Flow Analysis

### 1. Save Plan Flow (`/update-plan` endpoint)

**Step 1: Delete existing permissions**
```python
delete_result = supabase.table('plan_template_permissions').delete().eq('plan_id', db_plan_id).execute()
```

**Step 2: Insert new permissions**
- For template IDs: Direct insert with `can_download: True`
- For template names: Match by name, then insert with `can_download: True`

**Step 3: Read back permissions for response**
```python
perms_res = supabase.table('plan_template_permissions').select('template_id, max_downloads_per_template').eq('plan_id', db_plan_id).execute()
```

**ISSUE FOUND**: The query doesn't filter by `can_download = True`, but it also doesn't need to since we just inserted them. However, it only selects `template_id` and `max_downloads_per_template`, not `can_download`.

**Step 4: Convert template IDs to file names**
```python
template_file_names = [ensure_docx_filename(template_id_to_name.get(tid, '')) for tid in template_ids if tid and template_id_to_name.get(tid)]
```

**POTENTIAL ISSUE**: If `template_id_to_name.get(tid)` returns empty string, the template won't be included in the list!

### 2. Read Plans Flow (`/plans-db` endpoint)

**Step 1: Read permissions**
```python
permissions_res = supabase.table('plan_template_permissions').select(
    'template_id, can_download, max_downloads_per_template').eq('plan_id', plan['id']).execute()
```

**Step 2: Filter by can_download**
```python
if perm.get('can_download'):
    template_id = perm['template_id']
    plan_template_ids.add(template_id)
    # Add template file_name to allowed_templates list
    template_info = template_map.get(template_id)
    if template_info:
        file_name = template_info.get('file_name', '')
        if file_name and file_name not in allowed_templates:
            allowed_templates.append(file_name)
```

**POTENTIAL ISSUE**: If `template_map.get(template_id)` returns None (template not found in active templates), the template won't be added to `allowed_templates`.

### 3. Frontend Display Flow

**Step 1: Save plan**
- Receives response with `plan_data.can_download`
- Updates `this.allPlans` with merged data
- Calls `this.displayPlans(this.allPlans)` immediately

**Step 2: Reload from database**
- Waits 800ms
- Calls `this.loadPlans(true)` which calls `/plans-db`
- This might overwrite the correct data with incorrect data if database query is wrong

## Root Causes Identified

### Issue 1: Template ID to Name Mapping
In `/update-plan` response, if a template_id doesn't exist in `all_templates` query, it won't be included in `template_file_names`. This could happen if:
- Template was deleted but permissions still exist
- Template is inactive but permissions still exist
- Race condition: template not yet committed to database

### Issue 2: Template Map Missing Templates
In `/plans-db`, if a template_id in permissions doesn't exist in `template_map` (which only includes active templates), it won't be added to `allowed_templates`.

### Issue 3: Timing Issue
The frontend updates display immediately, then reloads from database after 800ms. If the database query in `/plans-db` is wrong, it will overwrite the correct data.

## Solutions

1. **Fix template ID to name mapping**: Ensure we handle missing templates gracefully
2. **Fix template map**: Include all templates (or handle missing ones) in the map
3. **Add better logging**: Log when templates are missing from the map
4. **Fix timing**: Ensure database is ready before reading back
5. **Add validation**: Check that permissions were actually saved before returning response


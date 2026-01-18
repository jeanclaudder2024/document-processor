# Check Template Permissions in Database

## The Issue
Templates are showing "All Plans" even though you configured specific plans in CMS.

## Possible Causes
1. **API not restarted** - Old code still running
2. **Templates actually have all plan permissions** - Database has permissions for all 3 plans
3. **Permissions not saved** - RLS issue or save failed

## How to Check

### Step 1: Verify API is Updated
```bash
cd /opt/petrodealhub/document-processor
git pull origin master
# Check if you see the new code
grep -n "plan_name" main.py | head -5
```

### Step 2: Restart API
```bash
bash restart-api-properly.sh
# or
sudo systemctl restart petrodealhub-api
```

### Step 3: Check Database Permissions
```bash
# Use the debug endpoint
curl http://localhost:8000/debug-plan-permissions | python3 -m json.tool
```

This will show:
- Which plans exist
- Which templates exist
- Which permissions are set for each plan

### Step 4: Check Specific Template
If a template shows "All Plans", check if it has permissions for all 3 plans:

```bash
# Example: Check if template has permissions for all plans
curl http://localhost:8000/debug-plan-permissions | python3 -m json.tool | grep -A 10 "permissions"
```

## What "All Plans" Means

A template shows "All Plans" when:
- It has permissions for **ALL 3 active plans** (basic, professional, enterprise)
- This is correct if you selected all plans in CMS

A template shows specific plan names when:
- It has permissions for **SOME plans** (e.g., only "Basic Plan, Professional Plan")
- This is correct if you selected specific plans in CMS

A template shows `null` when:
- It has **NO plan permissions** (public template)
- This means it's available to everyone

## Fix If Wrong

If a template shows "All Plans" but should only show specific plans:

1. **Go to CMS**
2. **Edit the plan** that has too many templates
3. **Uncheck the templates** you don't want
4. **Save**

The template will then show only the plans that have permission.

## Verify After Fix

After restarting API and checking database:
1. Refresh your browser (Ctrl+Shift+R)
2. Check templates - they should show correct plan names
3. If still wrong, check the debug endpoint output




# Check Template Plan Permissions

## The Issue
Templates are showing "All Plans" but you configured specific plans in CMS.

## This Could Mean:
1. ✅ Templates actually have permissions for ALL 3 plans (basic, professional, enterprise)
2. ❌ Backend hasn't been restarted with new code
3. ❌ Logic is showing "All Plans" incorrectly

## Check Database State

On your VPS, run:
```bash
curl http://localhost:8000/debug-plan-permissions | python3 -m json.tool
```

This will show:
- Which plans exist
- Which templates each plan has permissions for
- If a template has permissions for all plans, it will show in all plan sections

## Check Specific Template

To see which plans have access to a specific template:
```bash
# Replace TEMPLATE_ID with actual template ID
curl "http://localhost:8000/templates" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for t in data.get('templates', []):
    if 'original sgs report' in t.get('name', '').lower():
        print(json.dumps(t, indent=2))
"
```

## If Templates Have All Plans

If the debug endpoint shows that templates have permissions for all 3 plans, then "All Plans" is **correct**. 

To fix this:
1. Go to CMS
2. Edit each plan
3. **Unselect** templates you don't want that plan to have
4. Save
5. Check again - should show specific plan names

## If Backend Not Updated

Make sure backend is restarted:
```bash
cd /opt/petrodealhub/document-processor
git pull origin master
bash restart-api-properly.sh
```

## Expected Behavior

- If template has permissions for **all 3 plans** → Shows "All Plans" ✅
- If template has permissions for **2 plans** → Shows "Basic Plan, Professional Plan" ✅
- If template has permissions for **1 plan** → Shows "Basic Plan" ✅
- If template has **no permissions** → Shows `null` ✅


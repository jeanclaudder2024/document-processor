# Test Plan Save - Step by Step

## Current Status (from debug endpoint)
- ✅ Plans exist: basic, professional, enterprise (with UUIDs)
- ✅ Templates exist: 15 templates (with UUIDs)
- ❌ **NO PERMISSIONS** for any plan (all have count: 0)

## This means permissions are NOT being saved!

## Test Steps

### 1. Open Browser Console (F12)
Keep console open to see logs

### 2. Edit a Plan
- Click "Edit" on "Basic Plan"
- Check console for:
  ```
  [editPlan] 📋 Templates loaded: X
  [editPlan] 📋 Template IDs available: [...]
  ```
- **CRITICAL**: Check if template IDs are shown (should be UUIDs like `39736442-5839-49b1-979f-7e9a337e335f`)

### 3. Select Templates
- Select 2-3 templates (check the checkboxes)
- Check console for warnings:
  ```
  [editPlan] ⚠️ Template has NO ID: ...
  ```
- If you see this, templates don't have IDs - that's the problem!

### 4. Click Save
- Watch console for:
  ```
  [savePlan] 🔍 Processing checkbox: {templateId: "...", ...}
  [savePlan] 📋 Template IDs: [...]
  [savePlan] 💾 Sending: {...}
  ```

### 5. Check Backend Logs
```bash
sudo journalctl -u petrodealhub-api -f | grep -E "update-plan"
```

Look for:
- `[update-plan] 📋 Received can_download dict:` - Shows what backend received
- `[update-plan] ✅ Using template IDs format:` - Shows if IDs are being used
- `[update-plan] ✅ Added permission for template ID` - Shows if permissions were saved
- `[update-plan] ✅ Set X template permissions using IDs` - Shows total count
- `[update-plan] 📊 After save - Found X template permissions` - Shows if they were read back

### 6. Check Database Again
```bash
curl http://localhost:8000/debug-plan-permissions | python3 -m json.tool | grep -A 5 "basic"
```

Should show permissions count > 0 if save worked.

## Expected Flow

1. **Frontend sends:**
   ```json
   {
     "can_download": {
       "template_ids": ["39736442-5839-49b1-979f-7e9a337e335f", ...],
       "template_names": []
     }
   }
   ```

2. **Backend receives and processes:**
   - Finds templates by ID
   - Inserts permissions
   - Returns response with can_download array

3. **Backend reads back:**
   - Queries permissions
   - Maps template IDs to file names
   - Returns file names array

## If Still Not Working

Check these specific things:

1. **Are template IDs being sent?**
   - Check `[savePlan] 📋 Template IDs:` in console
   - Should show UUIDs, not empty array

2. **Are template IDs being received?**
   - Check `[update-plan] 📋 Received can_download dict:` in backend logs
   - Should show template_ids array with UUIDs

3. **Are templates being found?**
   - Check `[update-plan] ✅ Added permission for template ID` in backend logs
   - Should see one log per template

4. **Are permissions being inserted?**
   - Check `[update-plan] 📋 Insert result: X records inserted` in backend logs
   - Should be > 0

5. **Are permissions being read back?**
   - Check `[update-plan] 📊 After save - Found X template permissions` in backend logs
   - Should match number of templates selected


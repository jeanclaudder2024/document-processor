# Frontend Test Guide - Plan Save Debugging

## Current Status
- ✅ Plans exist in database (basic, professional, enterprise)
- ✅ Templates exist in database (15 templates with UUIDs)
- ❌ **NO PERMISSIONS** for any plan (all have count: 0)
- ❌ Permissions are NOT being saved

## Test Steps

### 1. Ensure You're Logged In
- Open CMS in browser
- Make sure you see "User: Admin" or similar (not "Not authenticated")
- If not logged in, login first

### 2. Open Browser Console (F12)
- Go to Console tab
- Keep it open during the test

### 3. Monitor Backend Logs
On VPS, run:
```bash
sudo journalctl -u petrodealhub-api -f | grep -E "update-plan|Authenticated"
```

### 4. Test Save Flow

#### Step 1: Open Edit Plan Modal
- Click "Edit" button on "Basic Plan"
- **Check console for:**
  ```
  [editPlan] 📋 Templates loaded: X
  [editPlan] 📋 First template object: {...}
  [editPlan] 📋 Template IDs available: [...]
  ```
- **CRITICAL**: Check if template IDs are shown (should be UUIDs like `39736442-5839-49b1-979f-7e9a337e335f`)
- **If you see `NO_ID`**: Templates don't have IDs - that's the problem!

#### Step 2: Select Templates
- Select 2-3 templates (check the checkboxes)
- **Check console for warnings:**
  ```
  [editPlan] ⚠️ Template has NO ID: ...
  ```
- If you see this, templates don't have IDs

#### Step 3: Click Save
- Click "Save" button
- **Watch console for:**
  ```
  [savePlan] 🔍 Processing checkbox: {templateId: "...", ...}
  [savePlan] 📋 Template IDs: [...]
  [savePlan] 💾 Sending: {...}
  ```

#### Step 4: Check Backend Logs
- **Look for these logs:**
  ```
  Authenticated user: admin
  [update-plan] 📥 Received 'allowed' value: {...}
  [update-plan] 📥 Type of 'allowed': <class 'dict'>
  [update-plan] 📥 Dict keys: ['template_ids', 'template_names']
  [update-plan] 📥 Dict values: {...}
  [update-plan] 📊 Final 'allowed' value after processing: [...]
  [update-plan] 📊 Will process permissions: True
  [update-plan] ✅ Added permission for template ID ...
  [update-plan] 📊 After save - Found X template permissions
  ```

### 5. Verify Save Worked

After saving, check database:
```bash
curl http://localhost:8000/debug-plan-permissions | python3 -m json.tool | grep -A 5 "basic"
```

Should show `count > 0` if save worked.

## What to Look For

### If Template IDs Are Empty
**Problem**: Frontend isn't getting template IDs from `/templates` endpoint
**Check**: 
- Open: `http://your-server:8000/templates`
- Look for `"id"` field in each template
- Should be UUIDs like `"39736442-5839-49b1-979f-7e9a337e335f"`

### If Template IDs Are Sent But Not Found
**Problem**: Template IDs don't match database
**Check**:
- Backend log: `[update-plan] ❌ Template ID ... NOT FOUND in database!`
- Compare template IDs from frontend with debug endpoint

### If Permissions Are Saved But Not Read Back
**Problem**: Response building issue
**Check**:
- Backend log: `[update-plan] ✅ Set X template permissions using IDs`
- But debug endpoint shows count: 0
- This means save worked but read-back failed

### If No Logs Appear
**Problem**: Request isn't reaching backend
**Check**:
- Browser console for errors
- Network tab for failed requests
- Backend logs for any errors

## Share These Logs

When testing, share:
1. **Browser console logs** (all `[savePlan]` and `[editPlan]` logs)
2. **Backend logs** (all `[update-plan]` logs)
3. **Debug endpoint output** (after save)

This will help identify the exact issue!


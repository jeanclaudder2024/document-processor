# AI Random Data Generation - Test Plan

## Test Overview
This document outlines the complete test plan for AI-powered random data generation in the CMS.

## Prerequisites
- ✅ OpenAI API key configured in `.env` file
- ✅ OpenAI package installed (`pip install openai==1.3.0`)
- ✅ Document processor service running
- ✅ CMS accessible at `/cms/`

## Test Suite Location
**File:** `test-ai-random-data.html`  
**Access:** `http://your-server:8000/cms/test-ai-random-data.html`

## Test Cases

### Test 1: API Health Check
**Objective:** Verify API is running and OpenAI is enabled

**Steps:**
1. Open test suite: `http://localhost:8000/cms/test-ai-random-data.html`
2. Click "Run All Tests"
3. Check "API Health Check" result

**Expected Result:**
- ✅ API status: "healthy"
- ✅ OpenAI: "enabled"

**Pass Criteria:**
- API responds with status "healthy"
- OpenAI shows as "enabled" in health response

---

### Test 2: OpenAI Connection Test
**Objective:** Verify OpenAI API key is configured correctly

**Steps:**
1. Run test suite
2. Check "OpenAI Connection" test result

**Expected Result:**
- ✅ OpenAI is enabled
- ✅ API key configured

**Pass Criteria:**
- Health endpoint returns `"openai": "enabled"`

---

### Test 3: CMS Editor AI Option
**Objective:** Verify AI option appears in CMS editor

**Steps:**
1. Open CMS: `http://localhost:8000/cms/`
2. Login as admin
3. Go to Templates tab
4. Click "Edit Rules" on any template
5. Select a placeholder
6. Choose "Random" as source
7. Check "Random Mode" dropdown

**Expected Result:**
- ✅ Dropdown shows 3 options:
  - Auto (different per vessel)
  - Fixed (same for all vessels)
  - **AI Generated (using OpenAI)** ← Should be present

**Pass Criteria:**
- AI Generated option is visible and selectable

---

### Test 4: AI Data Generation Test
**Objective:** Test actual AI generation of random data

**Steps:**
1. Open CMS Editor for a template
2. Select a placeholder (e.g., "Company Name")
3. Set source to "Random"
4. Set Random Mode to "AI Generated (using OpenAI)"
5. Save settings
6. Generate a test document
7. Check generated value

**Expected Result:**
- ✅ AI generates realistic, context-aware data
- ✅ Data is different from standard random
- ✅ Data is professional and appropriate

**Pass Criteria:**
- Document generates successfully
- Placeholder is filled with AI-generated value
- Value is realistic and context-appropriate

---

### Test 5: AI vs Standard Random Comparison
**Objective:** Compare AI-generated vs standard random data

**Steps:**
1. Set placeholder to "Auto" mode, generate document
2. Set same placeholder to "AI Generated" mode, generate document
3. Compare the two values

**Expected Result:**
- ✅ AI-generated values are more realistic
- ✅ AI values are context-aware
- ✅ Standard random values are simpler/pattern-based

**Pass Criteria:**
- Clear difference in quality/realism between modes

---

### Test 6: Multiple Placeholders with AI
**Objective:** Test AI generation for multiple placeholders

**Steps:**
1. Select 3-5 different placeholders
2. Set all to "AI Generated" mode
3. Generate document
4. Check all values

**Expected Result:**
- ✅ All placeholders filled with AI-generated data
- ✅ Each value is appropriate for its placeholder
- ✅ Values are consistent and professional

**Pass Criteria:**
- All placeholders generate successfully
- Values are contextually appropriate

---

### Test 7: Error Handling
**Objective:** Test fallback when OpenAI fails

**Steps:**
1. Temporarily set invalid API key
2. Restart service
3. Try to generate document with AI mode
4. Check logs

**Expected Result:**
- ✅ System falls back to standard random data
- ✅ Error logged but generation continues
- ✅ User sees document generated (with fallback data)

**Pass Criteria:**
- No crashes or errors visible to user
- Fallback works seamlessly

---

## Manual Testing Checklist

### In CMS Editor:
- [ ] AI option appears in Random Mode dropdown
- [ ] Can select "AI Generated (using OpenAI)"
- [ ] Setting saves correctly
- [ ] Setting persists after page refresh

### In Document Generation:
- [ ] AI-generated values are realistic
- [ ] Values are context-appropriate
- [ ] Generation completes successfully
- [ ] No errors in console/logs

### Performance:
- [ ] AI generation completes within 5-10 seconds
- [ ] No timeout errors
- [ ] Multiple generations work consistently

---

## Automated Test Script

Run the automated test suite:

```bash
# Open in browser
http://localhost:8000/cms/test-ai-random-data.html

# Or with auto-run
http://localhost:8000/cms/test-ai-random-data.html?autorun
```

The test suite will:
1. ✅ Check API health
2. ✅ Verify OpenAI connection
3. ✅ Test CMS editor AI option
4. ✅ Test AI generation (if enabled)

---

## Troubleshooting

### AI Option Not Showing
- Check `editor.js` has "ai" option in dropdown
- Verify file is updated: `grep -i "ai generated" editor.js`

### OpenAI Not Enabled
- Check `.env` file has `OPENAI_API_KEY`
- Verify package installed: `pip list | grep openai`
- Restart service after adding key

### Generation Fails
- Check logs: `pm2 logs document-processor` or `journalctl -u document-processor -f`
- Verify API key is valid
- Check OpenAI account has credits

### Fallback Not Working
- Check `generate_realistic_random_data()` function
- Verify fallback logic in `main.py`

---

## Success Criteria

✅ All tests pass  
✅ AI option visible in CMS  
✅ AI generation works correctly  
✅ Fallback works when OpenAI unavailable  
✅ No errors in logs  
✅ Performance acceptable (<10s per generation)

---

## Test Report Template

```
Test Date: ___________
Tester: ___________
Environment: ___________

Test Results:
[ ] Test 1: API Health Check - PASS / FAIL
[ ] Test 2: OpenAI Connection - PASS / FAIL
[ ] Test 3: CMS Editor AI Option - PASS / FAIL
[ ] Test 4: AI Data Generation - PASS / FAIL
[ ] Test 5: AI vs Standard Comparison - PASS / FAIL
[ ] Test 6: Multiple Placeholders - PASS / FAIL
[ ] Test 7: Error Handling - PASS / FAIL

Issues Found:
1. ___________
2. ___________

Notes:
___________
```


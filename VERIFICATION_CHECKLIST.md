# Placeholder Replacement Verification Checklist

## ✅ What We've Fixed:

1. **Intelligent Matching for Random Source** ✅
   - When `source='random'` in CMS but no `databaseField` is set, system now tries intelligent matching first
   - This allows `deadweight`, `owner`, etc. to automatically match vessel database fields
   - Only uses random data if intelligent matching fails

2. **Double Brace Pattern Matching** ✅
   - Fixed pattern to correctly match `{{placeholder}}` format
   - Pattern matching verified with test script

3. **Comprehensive Document Processing** ✅
   - Processes body paragraphs
   - Processes table cells
   - Processes headers and footers
   - Preserves formatting

## 🔍 To Verify Everything Works:

### Step 1: Pull Latest Code on VPS
```bash
cd /opt/petrodealhub/document-processor
git pull origin master
sudo systemctl restart petrodealhub-api
```

### Step 2: Check Logs During Document Generation
```bash
sudo journalctl -u petrodealhub-api -f | grep -i "AUTO-MATCHED\|deadweight\|owner\|Replaced:"
```

Look for:
- `✅✅✅ AUTO-MATCHED (from random source): deadweight = '...'`
- `✅ Replaced: '{deadweight}' -> '...'`
- `✅ Replaced: '{{deadweight}}' -> '...'` (if using double braces)

### Step 3: Test Document Generation
Generate a document and check:
1. Are placeholders like `deadweight`, `owner` replaced with real vessel data?
2. Are placeholders in tables replaced?
3. Are placeholders in headers/footers replaced?
4. Are double-brace placeholders `{{placeholder}}` replaced?

### Step 4: Check for Issues

If placeholders are still not replaced:

1. **Check placeholder format in template:**
   - Are they `{placeholder}` or `{{placeholder}}`?
   - Are there spaces: `{ placeholder }` or `{placeholder}`?

2. **Check logs for errors:**
   ```bash
   sudo journalctl -u petrodealhub-api -n 500 | grep -i "error\|warning\|failed"
   ```

3. **Check if patterns are being built:**
   ```bash
   sudo journalctl -u petrodealhub-api -n 500 | grep -i "pattern\|Built"
   ```

4. **Verify data mapping:**
   ```bash
   sudo journalctl -u petrodealhub-api -n 500 | grep -i "Mapping:"
   ```

## Common Issues:

### Issue: Placeholders show "Value-XXXX"
**Solution:** ✅ FIXED - Intelligent matching now runs for `source='random'` placeholders

### Issue: Double braces not replaced `{{placeholder}}`
**Solution:** ✅ FIXED - Pattern matching updated

### Issue: Placeholders in tables not replaced
**Solution:** Code processes table cells - check logs to see if table processing runs

### Issue: Some placeholders replaced, others not
**Possible causes:**
- Placeholder name mismatch (check exact spelling)
- Placeholder in a format not supported (check pattern matching)
- Value is None or empty (check logs for warnings)

## Test Commands:

```bash
# Full diagnostic test
venv/bin/python3 test_placeholder_replacement.py "ICPO TEMPLATE.docx" --vessel-imo 1234567

# Pattern matching test
python3 test_pattern_matching.py

# Watch logs in real-time
sudo journalctl -u petrodealhub-api -f
```


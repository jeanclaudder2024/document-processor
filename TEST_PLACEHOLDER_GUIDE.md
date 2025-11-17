# Placeholder Replacement Testing Guide

## Quick Test Commands

### 1. Test Placeholder Extraction and Matching

```bash
cd /opt/petrodealhub/document-processor
python3 test_placeholder_replacement.py "ICPO TEMPLATE.docx" --vessel-imo TEST001
```

### 2. Test with Real Vessel IMO

```bash
python3 test_placeholder_replacement.py "ICPO TEMPLATE.docx" --vessel-imo 1234567
```

### 3. Test Full Document Generation (requires API running)

```bash
python3 test_placeholder_replacement.py "ICPO TEMPLATE.docx" --vessel-imo TEST001 --api-url http://localhost:8000
```

### 4. Check Logs for Placeholder Matching

```bash
# Watch logs in real-time
sudo journalctl -u petrodealhub-api -f | grep -i "placeholder\|matching\|summary"

# Check recent logs
sudo journalctl -u petrodealhub-api -n 200 --no-pager | grep -A 5 -B 5 "PLACEHOLDER\|matching"
```

### 5. Test API Endpoint Directly

```bash
# Test placeholder extraction
curl -X GET "http://localhost:8000/templates/ICPO%20TEMPLATE.docx" \
  -H "Cookie: session=YOUR_SESSION_TOKEN" | jq '.placeholders'

# Test document generation
curl -X POST "http://localhost:8000/generate-document" \
  -H "Content-Type: application/json" \
  -H "Cookie: session=YOUR_SESSION_TOKEN" \
  -d '{"template_name": "ICPO TEMPLATE.docx", "vessel_imo": "TEST001"}' \
  --output test_output.pdf
```

### 6. Check CMS Settings

```bash
# View placeholder settings file
cat storage/placeholder_settings.json | jq '."ICPO TEMPLATE.docx"'

# Check specific placeholder
cat storage/placeholder_settings.json | jq '."ICPO TEMPLATE.docx"."deadweight"'
```

## What the Test Script Shows

1. **Placeholder Extraction**: Lists all placeholders found in the template
2. **CMS Settings Loading**: Shows which placeholders are configured in CMS
3. **Placeholder Matching**: Shows which placeholders match CMS settings and which don't
4. **Vessel Data Matching**: Tests if placeholders can match vessel database fields
5. **Full Generation Test**: Tests the complete document generation process

## Common Issues and Solutions

### Issue: Placeholders showing "Value-XXXX"

**Cause**: Placeholder not matched to CMS settings or vessel database fields

**Solution**: 
- Check if placeholder is configured in CMS editor
- Verify placeholder name matches exactly (case-insensitive, but spaces/underscores matter)
- Check logs to see matching attempts

### Issue: Placeholder not found in CMS

**Cause**: Placeholder name mismatch between template and CMS settings

**Solution**:
- Run test script to see normalized names
- Update CMS settings to match extracted placeholder names
- Use the editor to configure all placeholders

### Issue: Database field not found

**Cause**: Field name in CMS doesn't match vessel database field

**Solution**:
- Check available vessel fields: `curl http://localhost:8000/vessel-fields`
- Update CMS databaseField to match exact field name
- Use intelligent matching (automatic) for common fields

## Debugging Steps

1. **Extract placeholders**:
   ```bash
   python3 -c "from main import extract_placeholders_from_docx; print(extract_placeholders_from_docx('templates/ICPO TEMPLATE.docx'))"
   ```

2. **Check CMS settings**:
   ```bash
   python3 -c "from main import read_json_file, PLACEHOLDER_SETTINGS_PATH; import json; print(json.dumps(read_json_file(PLACEHOLDER_SETTINGS_PATH, {}).get('ICPO TEMPLATE.docx', {}), indent=2))"
   ```

3. **Test matching**:
   ```bash
   python3 test_placeholder_replacement.py "ICPO TEMPLATE.docx"
   ```

4. **Check logs**:
   ```bash
   sudo journalctl -u petrodealhub-api -n 500 --no-pager | grep -i "placeholder\|deadweight\|owner"
   ```


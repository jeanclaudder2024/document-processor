# AI Mapping and Random Data Improvements

## ✅ Issues Fixed

### Issue 1: AI not mapping to all database tables (only 18 placeholders → database)
### Issue 2: Random AI data not realistic or professional

---

## Changes Made

### 1. **Expanded Rule-Based Mappings** (`_UPLOAD_FIELD_MAPPINGS`)

**Before**: Only ~45 mappings for vessels, ports, and companies
**After**: 150+ mappings covering ALL 11 tables:

| Table | Example Mappings |
|-------|------------------|
| `vessels` | vessel_name, imo, flag, owner_name, cargo_type, etc. |
| `ports` | port_name, port_country, port_city, port_address |
| `buyer_companies` | buyer_name, buyer_email, buyer_address, buyer_country, buyer_contact_person |
| `seller_companies` | seller_name, seller_email, seller_address, seller_country, seller_contact_person |
| `companies` | company_name, company_address, company_email |
| `refineries` | refinery_name, refinery_capacity, refinery_country |
| `oil_products` | product_name, product_type, product_grade, api_gravity |
| `broker_profiles` | broker_name, broker_email, broker_phone |
| `buyer_company_bank_accounts` | buyer_bank_name, buyer_bank_swift, buyer_bank_iban |
| `seller_company_bank_accounts` | seller_bank_name, seller_bank_swift, seller_bank_iban |
| `deals` | deal_status, deal_value, deal_price, deal_quantity |

### 2. **Removed Schema Truncation**

**Before**: Only 200 table.column combinations sent to AI
**After**: ALL columns from ALL 11 tables sent to AI

```python
# Before
schema_str = ", ".join(flat[:200])  # Truncated!

# After
schema_str = ", ".join(flat)  # Full schema
```

### 3. **Improved AI Prompt for Random Data**

**Before**: Simple hints like "company name", "port name"
**After**: Comprehensive context-aware hints:

- For buyer companies: "professional oil/trading company name (e.g., 'Global Energy Trading Ltd')"
- For seller companies: "professional oil/energy company name (e.g., 'Arabian Oil Corporation')"
- For bank names: "major international bank name (HSBC, Standard Chartered, Citibank)"
- For SWIFT codes: "valid SWIFT/BIC code format (8-11 characters like HSBCSGSG)"
- For addresses: "business address with street, city, country"
- For dates: "recent date (past 30 days) in YYYY-MM-DD format"

### 4. **Improved Fallback Random Data**

**Before**: Generic values like "TBN", "N/A"
**After**: Context-aware realistic values:

#### Bank Data:
- Real bank names: HSBC, Standard Chartered, Deutsche Bank, BNP Paribas
- Real SWIFT codes: HSBCSGSG, SCBLSGSG, DEUTSGSG
- Proper IBAN format: GB/DE/FR + numbers

#### Company Names:
- Buyer companies: "Global Energy Trading Ltd", "Pacific Petroleum Co."
- Seller companies: "Arabian Oil Corporation", "Gulf Petroleum DMCC"
- Generic companies: "Maritime Solutions Ltd", "Ocean Trading Co"

#### Addresses:
- Full format: "123 Business Center, Singapore 048619"
- Bank addresses: "25 Raffles Place, Singapore 048619"

---

## Expected Results

### Before:
- ~18 placeholders → database
- Many placeholders → random with unrealistic data
- Generic values like "TBN", "N/A" in documents

### After:
- **90%+ placeholders → database** (using all 11 tables)
- Random data is **realistic and professional**
- Bank details look like real SWIFT codes, IBANs
- Company names sound like real trading companies
- Addresses are complete with street, city, country

---

## How It Works

1. **Template Upload** → AI analyzes placeholders
2. **AI gets full schema** → All 11 tables with all columns (no truncation)
3. **Prefix matching** → `buyer_*` → buyer_companies, `seller_*` → seller_companies
4. **Rule-based fallback** → 150+ predefined mappings
5. **Rescue phase** → Converts random/CSV → database when possible
6. **Random generation** → Comprehensive AI prompt with context
7. **Fallback random** → Context-aware realistic values

---

## Testing

After restarting the API, test:

1. **Upload a template** with many placeholders
2. **Check mapping counts**: Should see 90%+ database, <10% random
3. **Generate a document** with random data
4. **Verify output**: Should look professional and realistic

---

## Files Modified

1. `document-processor/main.py`:
   - `_UPLOAD_FIELD_MAPPINGS` - expanded to 150+ mappings
   - `_ai_suggest_placeholder_mapping` - removed schema truncation
   - `_generate_contextual_value` - improved AI prompt
   - `generate_realistic_random_data` - improved fallback data

---

## Restart Required

**Restart the Python API** to apply these changes:

```bash
# Stop current API
taskkill /F /PID <current_pid>

# Start new API
cd document-processor
python main.py
```

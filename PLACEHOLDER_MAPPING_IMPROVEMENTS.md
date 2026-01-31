# Placeholder Mapping Improvements - 90%+ Database Priority

## ✅ Changes Made

### 1. **Expanded Schema Building** (`_build_schema_for_mapping()`)
- **Before**: Only 4 tables (vessels, ports, companies, refineries)
- **After**: All 11 supported tables:
  - `vessels` (INTEGER ID)
  - `ports` (INTEGER ID)
  - `companies` (INTEGER ID)
  - `buyer_companies` (UUID ID) ✨ NEW
  - `seller_companies` (UUID ID) ✨ NEW
  - `refineries` (UUID ID)
  - `oil_products` (UUID ID) ✨ NEW
  - `broker_profiles` (UUID ID) ✨ NEW
  - `buyer_company_bank_accounts` (UUID ID) ✨ NEW
  - `seller_company_bank_accounts` (UUID ID) ✨ NEW
  - `deals` (UUID ID) ✨ NEW

### 2. **Prefix-Based Rule Matching**
- **Before**: Only used `_UPLOAD_FIELD_MAPPINGS` dictionary (limited mappings)
- **After**: Uses prefix-based matching from `id_based_fetcher.py`:
  - `buyer_*` → `buyer_companies` table
  - `seller_*` → `seller_companies` table
  - `vessel_*` → `vessels` table
  - `port_*`, `departure_port_*`, `destination_port_*` → `ports` table
  - `refinery_*` → `refineries` table
  - `product_*` → `oil_products` table
  - `broker_*` → `broker_profiles` table
  - `buyer_bank_*` → `buyer_company_bank_accounts` table
  - `seller_bank_*` → `seller_company_bank_accounts` table
  - `deal_*` → `deals` table

### 3. **AI Prompt Updates**
- **Before**: Prioritized CSV for buyer/seller data
- **After**: 
  - **90%+ should be database** (explicit priority)
  - Database > CSV > Random (strict order)
  - CSV only when database has NO matching column
  - Random only when no database or CSV match (<5%)

### 4. **Rescue Logic Enhancement**
- **Before**: Only rescued random placeholders
- **After**: 
  - Rescues random placeholders → database
  - Rescues CSV placeholders → database (if database match exists)
  - Uses prefix-based matching for better accuracy

### 5. **CSV Mapping Override**
- **Before**: Accepted CSV mappings without checking database
- **After**: Before accepting CSV, checks if database has a match using prefix-based logic
  - If database match found → use database instead of CSV
  - Only uses CSV if no database match exists

## 📊 Expected Results

### Before:
- ~18 placeholders mapped to database
- Many placeholders mapped to CSV or random
- Only 4 tables available for mapping

### After:
- **90%+ placeholders mapped to database**
- All 11 tables available
- Prefix-based matching ensures accurate table selection
- CSV only when database truly has no match
- Random only as last resort (<5%)

## 🔍 How It Works

1. **Schema Building**: Fetches columns from all 11 tables (Supabase or predefined)
2. **AI Analysis**: AI receives all tables/columns and is instructed to prioritize database (90%+)
3. **Rule-Based Fallback**: Uses prefix-based matching to identify table from placeholder name
4. **Rescue Phase**: Converts CSV/random mappings to database when database match exists
5. **Final Result**: 90%+ database mappings

## 🎯 Prefix Matching Examples

| Placeholder | Prefix Detected | Table | Column Matched |
|------------|----------------|-------|----------------|
| `{{buyer_name}}` | `buyer_` | `buyer_companies` | `name` |
| `{{seller_email}}` | `seller_` | `seller_companies` | `email` |
| `{{vessel_imo}}` | `vessel_` | `vessels` | `imo` |
| `{{port_name}}` | `port_` | `ports` | `name` |
| `{{buyer_bank_swift}}` | `buyer_bank_` | `buyer_company_bank_accounts` | `swift_code` |
| `{{product_name}}` | `product_` | `oil_products` | `name` |
| `{{refinery_capacity}}` | `refinery_` | `refineries` | `capacity` |

## 📝 Testing

After restarting the API, test by:
1. Upload a template with many placeholders
2. Run AI scan
3. Check results - should see 90%+ mapped to database
4. Verify all 11 tables are available in dropdowns

## 🔄 Next Steps

1. **Restart Python API** to apply changes
2. **Test with real template** - upload and run AI scan
3. **Verify mappings** - check that 90%+ are database
4. **Monitor logs** - check rescue counts in logs

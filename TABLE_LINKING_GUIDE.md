# Database Table Linking Guide

## Current Status

### ✅ Currently Linked Tables

#### 1. **VESSELS** Table
- **Total Placeholders**: 60
- **Columns Used**: 27 out of 48 available columns
- **Placeholders Linked**:
  - `imo`, `imo_number`, `imonumber`, `imono` → `vessels.imo`
  - `vessel_name`, `vesselname`, `shipname`, `name` → `vessels.name`
  - `vessel_type`, `vesseltype`, `shiptype` → `vessels.vessel_type`
  - `flag`, `flag_state`, `flagstate`, `country` → `vessels.flag`
  - `mmsi`, `mmsinumber` → `vessels.mmsi`
  - `length`, `length_overall`, `lengthoverall`, `loa` → `vessels.length`
  - `width` → `vessels.width`
  - `beam`, `breadth` → `vessels.beam`
  - `draft` → `vessels.draft`
  - `deadweight`, `dwt` → `vessels.deadweight`
  - `gross_tonnage`, `grosstonnage` → `vessels.gross_tonnage`
  - `owner_name`, `ownername`, `vesselowner`, `owner` → `vessels.owner_name`
  - `operator_name`, `operatorname`, `vesseloperator` → `vessels.operator_name`
  - `callsign` → `vessels.callsign`
  - `built`, `year_built`, `yearbuilt` → `vessels.built`
  - `cargo_capacity`, `cargocapacity` → `vessels.cargo_capacity`
  - `cargo_type`, `cargotype` → `vessels.cargo_type`
  - `cargo_quantity`, `cargoquantity` → `vessels.cargo_quantity`
  - `oil_type`, `oiltype` → `vessels.oil_type`
  - `quantity` → `vessels.quantity`
  - `currentport`, `port` → `vessels.currentport`
  - `loading_port`, `loadingport` → `vessels.loading_port`
  - `buyer_name`, `buyername` → `vessels.buyer_name`
  - `seller_name`, `sellername` → `vessels.seller_name`
  - `email` → `vessels.email`
  - `phone` → `vessels.phone`
  - `address` → `vessels.address`

#### 2. **PORTS** Table
- **Total Placeholders**: 14
- **Columns Used**: 3 out of 21 available columns
- **Placeholders Linked**:
  - `port_name`, `portname`, `loadingportname`, `portofloading`, `portofdischarge`, `departureport`, `destinationport`, `dischargeport`, `portloading`, `portdischarge` → `ports.name`
  - `port_country`, `portcountry` → `ports.country`
  - `port_city`, `portcity` → `ports.city`

#### 3. **COMPANIES** Table
- **Total Placeholders**: 38
- **Columns Used**: 5 out of 19 available columns
- **Placeholders Linked**:
  - `company_name`, `companyname`, `buyer_company`, `buyercompany`, `seller_company`, `sellercompany`, `seller_company_name`, `sellercompanyname`, `buyer_company_name`, `buyercompanyname` → `companies.name`
  - `registration_country`, `registrationcountry`, `seller_country`, `sellercountry`, `buyer_country`, `buyercountry`, `seller_registration_country`, `sellerregistrationcountry`, `buyer_registration_country`, `buyerregistrationcountry` → `companies.country`
  - `legal_address`, `legaladdress`, `seller_legal_address`, `sellerlegaladdress`, `buyer_legal_address`, `buyerlegaladdress`, `seller_address`, `selleraddress`, `buyer_address`, `buyeraddress` → `companies.address`
  - `seller_email`, `selleremail`, `buyer_email`, `buyeremail` → `companies.email`
  - `seller_phone`, `sellerphone`, `buyer_phone`, `buyerphone` → `companies.phone`

#### 4. **REFINERIES** Table
- **Total Placeholders**: 0 (⚠️ **NOT CURRENTLY LINKED**)
- **Available Columns**: 17
- **Columns Available**: `id`, `name`, `location`, `capacity`, `products`, `country`, `city`, `latitude`, `longitude`, `refinery_type`, `crude_capacity`, `distillation_capacity`, `cracking_capacity`, `reforming_capacity`, `owner`, `operator`, `established_year`

---

## ❌ Missing Tables (Not Currently Linked)

### High Priority Tables:
1. **buyer_companies** - Buyer company information
2. **vessel_companies** - Vessel-related company data
3. **real_companies** - Real company information
4. **products** - Product/cargo specifications
5. **brokers** - Broker information (currently excluded but exists in DB)

### Additional Tables:
6. **deals** - Deal/transaction information
7. **contracts** - Contract details
8. **invoices** - Invoice data
9. **payments** - Payment information
10. **bank_accounts** - Banking details
11. **contacts** - Contact person information
12. **vessel_positions** - Vessel location/tracking data
13. **cargo** - Cargo details
14. **inspections** - Inspection records
15. **certificates** - Certificate information

---

## How to Add New Tables

### Step 1: Update `_UPLOAD_FIELD_MAPPINGS` in `main.py`

Add placeholder mappings for your new table. Example for `products` table:

```python
_UPLOAD_FIELD_MAPPINGS: Dict[str, Tuple[str, str]] = {
    # ... existing mappings ...
    
    # products table
    'productname': ('products', 'name'), 'product_name': ('products', 'name'),
    'producttype': ('products', 'product_type'), 'product_type': ('products', 'product_type'),
    'productcategory': ('products', 'category'), 'product_category': ('products', 'category'),
    'productspecification': ('products', 'specification'), 'product_specification': ('products', 'specification'),
    'productgrade': ('products', 'grade'), 'product_grade': ('products', 'grade'),
    'productquality': ('products', 'quality'), 'product_quality': ('products', 'quality'),
    'productprice': ('products', 'price'), 'product_price': ('products', 'price'),
    'productunit': ('products', 'unit'), 'product_unit': ('products', 'unit'),
    'productquantity': ('products', 'quantity'), 'product_quantity': ('products', 'quantity'),
}
```

### Step 2: Add Table to `get_database_tables()` Endpoint

In `main.py`, find the `get_database_tables()` function and add your table:

```python
tables = [
    {'name': 'vessels', 'label': 'Vessels', 'description': 'Vessel information and specifications'},
    {'name': 'ports', 'label': 'Ports', 'description': 'Port information and details'},
    {'name': 'refineries', 'label': 'Refineries', 'description': 'Refinery information'},
    {'name': 'companies', 'label': 'Companies', 'description': 'Company information'},
    {'name': 'products', 'label': 'Products', 'description': 'Product specifications'},  # NEW
    {'name': 'buyer_companies', 'label': 'Buyer Companies', 'description': 'Buyer company information'},  # NEW
]
```

### Step 3: Add Column Definitions

Add column definitions in `_get_predefined_table_columns()`:

```python
'products': [
    col('id', 'ID', 'integer'),
    col('name', 'Product Name'),
    col('product_type', 'Product Type'),
    col('category', 'Category'),
    col('specification', 'Specification'),
    col('grade', 'Grade'),
    col('quality', 'Quality'),
    col('price', 'Price', 'numeric'),
    col('unit', 'Unit'),
    col('quantity', 'Quantity', 'numeric'),
    # ... add all columns from your database
],
```

### Step 4: Add to Default Columns List

In `_get_default_columns()`:

```python
'products': ['name', 'product_type', 'category', 'specification', 'grade', 'quality', 'price', 'unit', 'quantity'],
```

### Step 5: Update `_build_schema_for_mapping()`

Add your table to the `priority_tables` list:

```python
priority_tables = ['vessels', 'ports', 'companies', 'refineries', 'products', 'buyer_companies']
```

### Step 6: Update Intelligent Matching Logic

In `_intelligent_field_match_multi_table()`, add logic to fetch from your new table:

```python
# Example: Fetch product data if vessel has product_id
if vessel.get('product_id'):
    product_data = get_data_from_table('products', 'id', vessel['product_id'])
    if product_data:
        for k, v in product_data.items():
            if v is not None and str(v).strip():
                merged[f"product_{k}"] = v
```

### Step 7: Update Document Generation Logic

In `generate_document()`, add handling for your new table:

```python
elif database_table.lower() == 'products':
    lookup_field = 'id'
    lookup_value = vessel.get('product_id')
```

---

## Quick Reference: Placeholder Counts

| Table | Placeholders | Columns Used | Total Columns Available |
|-------|-------------|--------------|------------------------|
| **vessels** | 60 | 27 | 48 |
| **ports** | 14 | 3 | 21 |
| **companies** | 38 | 5 | 19 |
| **refineries** | 0 | 0 | 17 |
| **TOTAL** | **112** | **35** | **105** |

---

## Next Steps

1. **Identify all placeholders** in your templates that need database linking
2. **Map placeholders** to appropriate tables and columns
3. **Add missing tables** using the steps above
4. **Test** with actual templates to ensure placeholders are correctly mapped
5. **Run analysis script** again: `python analyze_placeholders.py`

---

## Example: Adding `products` Table

Here's a complete example of adding the `products` table:

```python
# 1. Add to _UPLOAD_FIELD_MAPPINGS
'productname': ('products', 'name'),
'product_name': ('products', 'name'),
'producttype': ('products', 'product_type'),
'product_type': ('products', 'product_type'),
# ... more mappings

# 2. Add to get_database_tables()
{'name': 'products', 'label': 'Products', 'description': 'Product specifications'},

# 3. Add column definitions
'products': [
    col('id', 'ID', 'integer'),
    col('name', 'Product Name'),
    # ... all columns
],

# 4. Add to default columns
'products': ['name', 'product_type', 'category', 'specification'],

# 5. Add to priority_tables
priority_tables = [..., 'products']
```

---

## Need Help?

If you need help mapping specific placeholders to tables, run:
```bash
python analyze_placeholders.py
```

This will show you the current state and help identify what needs to be added.

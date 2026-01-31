# Document Processor API

## Overview
A FastAPI-based document processing service for PetroDealHub that automatically fills Word document templates with data from Supabase database. Supports **455+ official placeholders** across 10 database tables using payload-driven architecture with explicit IDs.

## Project Structure
- `main.py` - Main FastAPI application with all endpoints and document processing logic
- `templates/` - Directory containing Word document templates
- `temp/` - Temporary directory for processing files
- `requirements.txt` - Python dependencies

## Key Features
- **455+ Official Placeholders**: Prefix-based placeholders matching database columns directly
- **Payload-Driven Data Fetching**: Explicit IDs in request (no auto-sync)
- **Prefix-Based Placeholder Mapping**: 14 prefixes for data isolation
- **Legacy Placeholder Support**: Backward compatibility for existing templates
- **Mixed ID Types**: Handles INTEGER (vessels, ports, companies) and UUID (buyers, sellers, products, etc.)
- **Bank Account Logic**: Primary bank fallback when specific bank_id not provided
- **PDF Conversion**: Optional PDF output via LibreOffice

## API Endpoints
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check (version, templates count) |
| `/` | GET | Root endpoint (returns running status) |
| `/templates` | GET | List available templates with placeholder analysis |
| `/vessels` | GET | List vessels from database |
| `/buyers` | GET | List buyers from database |
| `/sellers` | GET | List sellers from database |
| `/products` | GET | List oil products from database |
| `/refineries` | GET | List refineries from database |
| `/ports` | GET | List ports from database |
| `/brokers` | GET | List broker profiles from database |
| `/placeholder-schema` | GET | **NEW** - Get all available placeholders by entity |
| `/process-document` | POST | Process document with entity data |
| `/analyze-template` | POST | Analyze template placeholders and required IDs |
| `/upload-template` | POST | Upload new template |

## Processing Document Request Format
```json
{
  "template_name": "Commercial_Invoice_Batys_Final.docx",
  "vessel_id": 5,
  "buyer_id": "uuid-here",
  "seller_id": "uuid-here",
  "product_id": "uuid-here",
  "refinery_id": "uuid-here",
  "broker_id": "uuid-here",
  "buyer_bank_id": "uuid-here",
  "seller_bank_id": "uuid-here",
  "departure_port_id": 123,
  "destination_port_id": 456,
  "company_id": 789,
  "deal_id": "uuid-here",
  "output_format": "pdf"
}
```

## Official Placeholder Format
All official placeholders follow the format: `{{prefix_fieldname}}`

### Prefix-to-Table Mapping (14 Prefixes)
| Prefix | Table | ID Type | Placeholder Count |
|--------|-------|---------|-------------------|
| `vessel_` | vessels | INTEGER | 97 |
| `port_` | ports | INTEGER | 56 |
| `departure_port_` | ports | INTEGER | 56 |
| `destination_port_` | ports | INTEGER | 56 |
| `company_` | companies | INTEGER | 47 |
| `buyer_` | buyer_companies | UUID | 37 |
| `seller_` | seller_companies | UUID | 45 |
| `refinery_` | refineries | UUID | 56 |
| `product_` | oil_products | UUID | 55 |
| `broker_` | broker_profiles | UUID | 36 |
| `deal_` | broker_deals | UUID | - |
| `buyer_bank_` | buyer_company_bank_accounts | UUID | 13 |
| `seller_bank_` | seller_company_bank_accounts | UUID | 13 |
| `company_bank_` | company_bank_accounts | UUID | - |

### Sample Official Placeholders by Entity

**Vessel (97 placeholders)**
```
{{vessel_name}}, {{vessel_imo}}, {{vessel_mmsi}}, {{vessel_type}}, {{vessel_flag}}, 
{{vessel_built}}, {{vessel_deadweight}}, {{vessel_cargo_capacity}}, {{vessel_owner_name}}, 
{{vessel_operator_name}}, {{vessel_length}}, {{vessel_gross_tonnage}}, {{vessel_callsign}}, 
{{vessel_speed}}, {{vessel_status}}, {{vessel_eta}}, {{vessel_departure_port}}, 
{{vessel_destination_port}}, {{vessel_cargo_type}}, {{vessel_oil_type}}, {{vessel_quantity}}
```

**Buyer Companies (37 placeholders)**
```
{{buyer_name}}, {{buyer_trade_name}}, {{buyer_email}}, {{buyer_phone}}, {{buyer_address}}, 
{{buyer_country}}, {{buyer_city}}, {{buyer_representative_name}}, {{buyer_representative_title}}, 
{{buyer_passport_number}}, {{buyer_registration_number}}, {{buyer_legal_address}}, 
{{buyer_kyc_status}}, {{buyer_sanctions_status}}
```

**Seller Companies (45 placeholders)**
```
{{seller_name}}, {{seller_trade_name}}, {{seller_email}}, {{seller_phone}}, {{seller_address}}, 
{{seller_country}}, {{seller_city}}, {{seller_representative_name}}, {{seller_representative_title}}, 
{{seller_passport_number}}, {{seller_registration_number}}, {{seller_refinery_name}}, 
{{seller_products_supplied}}, {{seller_loading_ports}}
```

**Oil Products (55 placeholders)**
```
{{product_commodity_name}}, {{product_commodity_type}}, {{product_grade}}, {{product_origin}}, 
{{product_sulphur_content_ppm}}, {{product_density_kg_m3}}, {{product_viscosity_cst}}, 
{{product_flash_point_min_c}}, {{product_pour_point_c}}, {{product_cetane_number_min}}, 
{{product_price_basis}}, {{product_delivery_terms}}, {{product_payment_terms}}
```

**Ports (56 placeholders)**
```
{{port_name}}, {{port_country}}, {{port_region}}, {{port_type}}, {{port_city}}, 
{{port_operator}}, {{port_owner}}, {{port_capacity}}, {{port_max_vessel_length}}, 
{{port_max_draught}}, {{port_berth_count}}, {{port_services}}
```

**Refineries (56 placeholders)**
```
{{refinery_name}}, {{refinery_country}}, {{refinery_capacity}}, {{refinery_products}}, 
{{refinery_operator}}, {{refinery_owner}}, {{refinery_type}}, {{refinery_status}}, 
{{refinery_processing_capacity}}, {{refinery_environmental_certifications}}
```

**Broker Profiles (36 placeholders)**
```
{{broker_full_name}}, {{broker_company_name}}, {{broker_email}}, {{broker_phone}}, 
{{broker_country}}, {{broker_city}}, {{broker_license_number}}, {{broker_years_experience}}, 
{{broker_specializations}}, {{broker_commission_rate}}
```

**Bank Accounts (13 placeholders each)**
```
{{buyer_bank_name}}, {{buyer_bank_address}}, {{buyer_bank_account_name}}, 
{{buyer_bank_account_number}}, {{buyer_bank_iban}}, {{buyer_bank_swift}}, 
{{buyer_bank_beneficiary_address}}, {{buyer_bank_currency}}, {{buyer_bank_is_primary}}

{{seller_bank_name}}, {{seller_bank_address}}, {{seller_bank_account_name}}, 
{{seller_bank_account_number}}, {{seller_bank_iban}}, {{seller_bank_swift}}, 
{{seller_bank_beneficiary_address}}, {{seller_bank_currency}}, {{seller_bank_is_primary}}
```

## Legacy Placeholder Support
The system also supports legacy placeholder names from existing templates for backward compatibility:
- `imo_number` → vessel.imo
- `flag_state` → vessel.flag
- `vessel_type` → vessel.vessel_type
- `Principal_Buyer_Name` → buyer.representative_name
- `Seller_Company` → seller.name
- And 100+ more mappings in `_LEGACY_PLACEHOLDER_MAPPING_RAW`

## How Placeholder Detection Works

1. **Template Scan**: Detects placeholders in formats: `{{...}}`, `{...}`, `[[...]]`, `%...%`, `<...>`
2. **Legacy Check**: First checks if placeholder matches legacy mapping
3. **Prefix Detection**: Identifies prefix (e.g., `vessel_`, `buyer_`) 
4. **Field Extraction**: Extracts field name after prefix
5. **Data Lookup**: Looks up field in fetched entity data
6. **Value Formatting**: Formats dates, booleans, numbers appropriately

## Known Limitations
- **Product Quality Variants**: Result_/Min_/Max_ placeholder variants (e.g., `Result_Density`, `Max_Sulfur`) are not supported as the database stores single values only
- **Semantic Mapping Philosophy**: Legacy mappings use conservative matching - only verified semantic equivalents are mapped

## Running the Application
```bash
python main.py
```
Server runs on port 5000 using uvicorn.

## Recent Changes
- 2026-01-31: Added `/placeholder-schema` endpoint to show all available placeholders
- 2026-01-31: Implemented prefixed field lookup for columns like `vessel_type`, `port_type`
- 2026-01-31: Updated to support 455+ official placeholders across 10 tables
- 2026-01-31: Added FIELD_ALIASES for placeholder-to-column name mapping
- 2026-01-31: Initial Replit setup, configured to run on port 5000
- 2026-01-31: Refactored to payload-driven architecture with explicit IDs
- 2026-01-31: Implemented 14 modular fetch functions
- 2026-01-31: Added strict prefix-based placeholder mapping system
- 2026-01-31: Added legacy placeholder support for backward compatibility
- 2026-01-31: Created /analyze-template endpoint for template analysis
- 2026-01-31: Bank account logic with is_primary fallback

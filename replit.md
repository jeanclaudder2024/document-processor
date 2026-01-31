# Document Processor API

## Overview
A FastAPI-based document processing service for PetroDealHub that automatically fills Word document templates with data from Supabase database. Uses payload-driven architecture with explicit IDs for all 12 core tables.

## Project Structure
- `main.py` - Main FastAPI application with all endpoints and document processing logic
- `templates/` - Directory containing Word document templates
- `temp/` - Temporary directory for processing files
- `requirements.txt` - Python dependencies

## Key Features
- **Payload-Driven Data Fetching**: Explicit IDs in request (no auto-sync)
- **Prefix-Based Placeholder Mapping**: 12 prefixes for data isolation
- **Legacy Placeholder Support**: Backward compatibility for existing templates
- **Mixed ID Types**: Handles INTEGER (vessels, ports, companies) and UUID (buyers, sellers, products, etc.)
- **Bank Account Logic**: Primary bank fallback when specific bank_id not provided
- **PDF Conversion**: Optional PDF output via LibreOffice

## API Endpoints
- `GET /health` - Health check (version, templates count)
- `GET /` - Root endpoint (returns running status)
- `GET /templates` - List available templates
- `GET /vessels` - List vessels from database
- `GET /buyers` - List buyers from database
- `GET /sellers` - List sellers from database
- `POST /process-document` - Process document with entity data
- `POST /analyze-template` - Analyze template placeholders and required IDs
- `POST /upload-template` - Upload new template

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

## Prefix-to-Table Mapping
| Prefix | Table | ID Type |
|--------|-------|---------|
| vessel_ | vessels | INTEGER |
| buyer_ | buyers | UUID |
| seller_ | sellers | UUID |
| product_ | products | UUID |
| refinery_ | refineries | UUID |
| broker_ | brokers | UUID |
| buyer_bank_ | bank_accounts | UUID |
| seller_bank_ | bank_accounts | UUID |
| departure_port_ | ports | INTEGER |
| destination_port_ | ports | INTEGER |
| company_ | companies | INTEGER |
| deal_ | deals | UUID |

## Legacy Placeholder Support
The system supports legacy placeholder names from existing templates:
- `imo_number` → vessel.imo
- `flag_state` → vessel.flag
- `vessel_type` → vessel.vessel_type
- `Principal_Buyer_Name` → buyer.representative_name
- `Seller_Company` → seller.name
- And 60+ more mappings in `LEGACY_PLACEHOLDER_MAPPING`

## Known Limitations
- **Product Quality Variants**: Result_/Min_/Max_ placeholder variants (e.g., `Result_Density`, `Max_Sulfur`) cannot be mapped as the database stores single values only. Use base terms (density, viscosity, sulfur) instead.
- **Semantic Mapping Philosophy**: Legacy mappings use conservative matching - only verified semantic equivalents are mapped. Fields without exact DB matches remain unmapped rather than risking incorrect data placement.

## Running the Application
```bash
python main.py
```
Server runs on port 5000 using uvicorn.

## Recent Changes
- 2026-01-31: Initial Replit setup, configured to run on port 5000
- 2026-01-31: Refactored to payload-driven architecture with explicit IDs
- 2026-01-31: Implemented 12 modular fetch functions (fetch_vessel, fetch_buyer, etc.)
- 2026-01-31: Added strict prefix-based placeholder mapping system
- 2026-01-31: Added legacy placeholder support for backward compatibility
- 2026-01-31: Created /analyze-template endpoint for template analysis
- 2026-01-31: Bank account logic with is_primary fallback

# Document Processor API

## Overview
A FastAPI-based document processing service that automatically fills Word document templates with vessel data from Supabase database.

## Project Structure
- `main.py` - Main FastAPI application with all endpoints and document processing logic
- `templates/` - Directory containing Word document templates
- `temp/` - Temporary directory for processing files
- `requirements.txt` - Python dependencies

## Key Features
- Word Document Processing with placeholder replacement
- Vessel Data Integration via Supabase
- PDF Conversion support
- REST API for React frontend integration

## API Endpoints
- `GET /health` - Health check
- `GET /` - Root endpoint (returns running status)
- `GET /templates` - List available templates
- `GET /vessels` - List vessels from database
- `GET /vessel/{imo}` - Get specific vessel by IMO
- `POST /process-document` - Process document with vessel data
- `POST /upload-template` - Upload new template

## Running the Application
The server runs on port 5000 using uvicorn:
```bash
python main.py
```

## Database Table Structure & Linked Placeholders
The system is linked to a Supabase database. Here are the tables and the specific placeholders they provide:

### 1. `vessels` (The Core Table)
Provides all general vessel data.
- **Linked Placeholders**: `{{name}}`, `{{imo}}`, `{{flag}}`, `{{vessel_type}}`, `{{deadweight}}`, `{{mmsi}}`, `{{year_built}}`, `{{call_sign}}`, `{{gross_tonnage}}`.

### 2. `ports` (Loading & Destination)
Provides location and port details. The system maps these using the prefixes `loading_port_` and `destination_port_`.
- **Loading Port Placeholders**: `{{loading_port_name}}`, `{{loading_port_country}}`, `{{loading_port_code}}`.
- **Destination Port Placeholders**: `{{destination_port_name}}`, `{{destination_port_country}}`, `{{destination_port_code}}`.

### 3. `companies` (Owner & Operator)
Provides business and contact information. The system maps these using the prefixes `owner_` and `operator_`.
- **Owner Placeholders**: `{{owner_name}}`, `{{owner_address}}`, `{{owner_email}}`, `{{owner_phone}}`, `{{owner_registration}}`.
- **Operator Placeholders**: `{{operator_name}}`, `{{operator_address}}`, `{{operator_email}}`, `{{operator_phone}}`.

### 4. `refineries` (Production Site)
Provides data about the refinery where products originate.
- **Linked Placeholders**: `{{refinery_name}}`, `{{refinery_location}}`, `{{refinery_capacity}}`, `{{refinery_contact}}`.

## How to Link Other Tables
To link additional tables like `buyer_companies`, `products`, or `real_companies`, the following steps are required in the code:
1.  **Update `get_vessel_data`**: Add a new query for the table (e.g., `supabase.table('products').select('*').eq('id', ...)`).
2.  **Add Foreign Keys**: Ensure the `vessels` table has a column that links to the new table (e.g., `product_id`).
3.  **Map Fields**: Loop through the results and add them to the `vessel_data` dictionary with a clear prefix (e.g., `product_name`).

## Recent Changes
- 2026-01-31: Initial Replit setup, configured to run on port 5000
- 2026-01-31: Added detailed database table and placeholder mapping documentation
- 2026-01-31: Documented current placeholder counts and names per table

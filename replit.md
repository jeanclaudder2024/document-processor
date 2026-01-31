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

## External Services
- **Supabase**: Used for vessel, port, company, and refinery data storage.
  - **URL**: `https://ozjhdxvwqbzcvcywhwjg.supabase.co`

## Database Table Structure
The system uses the following tables to map data to your documents:
- **`vessels`**: Main table (IMO, Name, Flag, Type)
- **`ports`**: Linked via `loading_port_id` and `destination_port_id`
- **`companies`**: Linked via `owner_id` and `operator_id`
- **`refineries`**: Linked via `refinery_id`

## Recent Changes
- 2026-01-31: Initial Replit setup, configured to run on port 5000
- 2026-01-31: Added detailed database table and placeholder mapping documentation

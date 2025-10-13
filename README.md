# Document Processor API

A FastAPI-based document processing service that automatically fills Word document templates with vessel data from Supabase database.

## Features

- 📄 **Word Document Processing**: Automatically fills placeholders in .docx templates
- 🚢 **Vessel Data Integration**: Connects to Supabase database for real vessel information
- 🔄 **PDF Conversion**: Converts filled Word documents to PDF format
- 🎯 **Smart Placeholder Replacement**: Uses database data + realistic random data for missing fields
- 🌐 **REST API**: Easy integration with React frontend

## API Endpoints

- `GET /health` - Health check
- `GET /templates` - List available templates
- `GET /vessels` - List vessels from database
- `GET /vessel/{imo}` - Get specific vessel by IMO
- `POST /process-document` - Process document with vessel data
- `POST /upload-template` - Upload new template

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set environment variables:
```bash
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
```

3. Run the server:
```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

## Usage

The API processes Word documents by:
1. Extracting placeholders from templates
2. Fetching vessel data from Supabase
3. Replacing placeholders with real data
4. Generating random data for missing fields
5. Converting to PDF format

## Deployment

This project is designed to be deployed on Railway.app with full LibreOffice support for perfect PDF conversion.

## Templates

Place your .docx templates in the `templates/` folder. The system supports various placeholder formats:
- `{{placeholder}}`
- `{placeholder}`
- `[placeholder]`
- `[[placeholder]]`
- `%placeholder%`
- `<placeholder>`
- `__placeholder__`
- `##placeholder##`

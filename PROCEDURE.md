# Document Processing Procedure

## Purpose
The Document Processing API is designed to automate the generation of commercial shipping and vessel-related documents (like Invoices, ICPOs, and Proof of Product). It bridges the gap between structured vessel data stored in a database and formatted Word documents needed for maritime operations.

## How it Works

### 1. Data Sourcing (Supabase)
The system connects to a Supabase database which acts as the "Single Source of Truth" for:
- **Vessel Information**: IMO numbers, names, flags, and technical specs.
- **Port Data**: Details about loading and destination ports.
- **Company Profiles**: Information about owners and operators.
- **Refinery Details**: Locations and specific refinery data.

### 2. Template Management
- Users upload standard `.docx` Word templates to the `/templates` directory.
- These templates contain various placeholder formats like `{{vessel_name}}`, `[imo_number]`, or `<port_name>`.

### 3. Processing Pipeline (The "How")
When a document is requested for a specific vessel (identified by IMO):
1. **Fetch Real Data**: The API queries Supabase to get all available real-world data for that vessel and its associated ports/companies.
2. **Handle Missing Data**: If certain fields are missing in the database, the system uses a "Smart Replacement" logic to generate realistic placeholder data so the document remains professional.
3. **Template Filling**: Using the `python-docx` library, the system scans the Word document and replaces every recognized placeholder with the fetched/generated data.
4. **Formatting Preservation**: The logic ensures that fonts, bolding, and table structures in the original Word template are preserved during replacement.
5. **PDF Conversion**: The final processed Word document is converted into a PDF for easy sharing and printing.

## Technical Stack
- **Backend**: FastAPI (Python) - High-performance web framework.
- **Document Logic**: `python-docx` - For manipulating Word files.
- **Database**: Supabase - PostgreSQL-based backend-as-a-service.
- **Deployment**: Configured for Replit with Autoscale capabilities.

## Usage Procedure
1. **Upload**: Put your `.docx` template in the system.
2. **Request**: Call the `/process-document` endpoint with the Vessel IMO and Template Name.
3. **Download**: Receive a perfectly filled, professional PDF document ready for use.
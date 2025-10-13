"""
Simple Document Processing API
Handles Word document processing with vessel data
"""

import os
import uuid
import tempfile
import zipfile
import shutil
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from fastapi import FastAPI, HTTPException, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from dotenv import load_dotenv
from supabase import create_client, Client
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
import re
from openai import OpenAI
import json

# Initialize FastAPI app
app = FastAPI(title="Document Processing API", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Supabase client - Direct configuration
SUPABASE_URL = "https://ozjhdxvwqbzcvcywhwjg.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im96amhkeHZ3cWJ6Y3ZjeXdod2pnIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTU5MDAyNzUsImV4cCI6MjA3MTQ3NjI3NX0.KLAo1KIRR9ofapXPHenoi-ega0PJtkNhGnDHGtniA-Q"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# OpenAI Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if OPENAI_API_KEY:
    openai_client = OpenAI(api_key=OPENAI_API_KEY)
else:
    print("Warning: OPENAI_API_KEY not found in environment variables")
    openai_client = None

# Create directories
TEMPLATES_DIR = "./templates"
TEMP_DIR = "./temp"
os.makedirs(TEMPLATES_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

def generate_ai_powered_data(placeholder: str, vessel_imo: str, vessel_context: dict = None) -> str:
    """Generate highly realistic, connected data using OpenAI"""
    try:
        if not openai_client:
            print(f"OpenAI client not available for {placeholder}")
            return generate_realistic_random_data(placeholder, vessel_imo)
        
        # Create context for AI
        context_info = ""
        if vessel_context:
            context_info = f"""
            Vessel Context:
            - IMO: {vessel_context.get('imo', vessel_imo)}
            - Name: {vessel_context.get('name', 'Unknown')}
            - Type: {vessel_context.get('vessel_type', 'Oil Tanker')}
            - Flag: {vessel_context.get('flag', 'Unknown')}
            - Owner: {vessel_context.get('owner_name', 'Unknown')}
            """
        
        prompt = f"""Generate realistic data for an oil trading document placeholder: "{placeholder}"

{context_info}

Requirements:
- Use REAL oil companies, banks, ports, and industry professionals
- Make data consistent and professional
- Follow international oil trading standards
- Use proper formats (emails, phone numbers, addresses)
- Return ONLY the data value, no explanations or quotes

Examples:
- For company names: "Shell International Trading and Shipping Company Ltd"
- For emails: "james.richardson@shell.com"
- For banks: "JPMorgan Chase Bank NA"
- For addresses: "1 Shell Centre, London SE1 7NA, UK"
- For phone: "+44 20 7934 1234"
- For dates: "2025-09-29"

Generate data for: {placeholder}"""

        response = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
            temperature=0.7
        )
        
        result = response.choices[0].message.content.strip()
        # Clean up the result
        result = result.strip('"').strip("'").strip()
        # Reduced logging to avoid rate limits
        # print(f"AI Generated for {placeholder}: {result}")
        return result
        
    except Exception as e:
        print(f"OpenAI error for {placeholder}: {e}")
        # Fallback to our realistic data
        return generate_realistic_random_data(placeholder, vessel_imo)

def generate_realistic_random_data(placeholder: str, vessel_imo: str = None) -> str:
    """Generate highly realistic, varied random data for oil trading documents with AI enhancement"""
    import random
    import hashlib
    from datetime import datetime, timedelta
    
    # Create unique seed for each entity type to ensure different data for different people/companies
    if vessel_imo:
        entity_type = placeholder.lower().replace('_', '').replace(' ', '')
        if 'buyer' in entity_type:
            seed_input = f"{vessel_imo}_buyer"
        elif 'seller' in entity_type:
            seed_input = f"{vessel_imo}_seller"
        elif 'bank' in entity_type or 'financial' in entity_type:
            seed_input = f"{vessel_imo}_bank"
        elif 'principal' in entity_type:
            seed_input = f"{vessel_imo}_principal"
        elif 'logistics' in entity_type:
            seed_input = f"{vessel_imo}_logistics"
        elif 'authorized' in entity_type or 'signatory' in entity_type:
            seed_input = f"{vessel_imo}_signatory"
        else:
            seed_input = f"{vessel_imo}_{entity_type}"
        
        random.seed(int(hashlib.md5(seed_input.encode()).hexdigest()[:8], 16))
    
    placeholder_lower = placeholder.lower().replace('_', '').replace(' ', '')
    
    # Use AI for complex, contextual data
    if any(word in placeholder_lower for word in [
        'company', 'bank', 'contract', 'terms', 'incoterm', 'payment', 
        'quality', 'specification', 'commodity', 'product', 'cargo',
        'port', 'terminal', 'refinery', 'facility', 'location'
    ]):
        return generate_ai_powered_data(placeholder, vessel_imo)
    
    # Use AI for professional names and relationships
    elif any(word in placeholder_lower for word in [
        'buyer', 'seller', 'principal', 'representative', 'signatory',
        'authorized', 'contact', 'person', 'officer', 'manager'
    ]):
        return generate_ai_powered_data(placeholder, vessel_imo)
    
    # Use AI for complex addresses and contact info
    elif any(word in placeholder_lower for word in [
        'address', 'location', 'street', 'city', 'country', 'region',
        'email', 'mail', 'phone', 'tel', 'mobile', 'contact'
    ]):
        return generate_ai_powered_data(placeholder, vessel_imo)
    
    # Keep our system for simple, structured data
    else:
        # Dates - all dates 2 weeks before today
        if any(word in placeholder_lower for word in ['date', 'time', 'eta', 'etd']):
            from datetime import timedelta
            date_result = (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d')
            # print(f"DEBUG: Processing date placeholder: {placeholder} -> {date_result}")
            return date_result
        
        # Reference numbers
        elif any(word in placeholder_lower for word in ['ref', 'number', 'id', 'code']):
            prefixes = ['REF', 'PO', 'SO', 'INV', 'LC', 'BL', 'COA', 'SGS']
            prefix = random.choice(prefixes)
            number = random.randint(100000, 999999)
            return f"{prefix}-{number}"
        
        # Quantities and amounts
        elif any(word in placeholder_lower for word in ['quantity', 'volume', 'capacity', 'tonnage']):
            if 'quantity' in placeholder_lower:
                return f"{random.randint(50000, 300000):,} MT"
            elif 'capacity' in placeholder_lower:
                return f"{random.randint(80000, 320000):,} DWT"
            else:
                return f"{random.randint(10000, 100000):,}"
        
        elif any(word in placeholder_lower for word in ['price', 'value', 'amount', 'cost']):
            if 'price' in placeholder_lower and 'oil' in placeholder_lower:
                return f"${random.uniform(45.50, 95.75):.2f}/bbl"
            elif 'value' in placeholder_lower or 'amount' in placeholder_lower:
                return f"${random.randint(5000000, 50000000):,}"
            else:
                return f"${random.randint(100000, 5000000):,}"
        
        # Default fallback
        else:
            return f"Sample {placeholder.replace('_', ' ').title()}"

def get_vessel_data(vessel_imo: str) -> dict:
    """Fetch comprehensive vessel data from Supabase"""
    try:
        # Get vessel data
        vessel_response = supabase.table('vessels').select('*').eq('imo', vessel_imo).execute()
        
        if not vessel_response.data:
            return {}
        
        vessel = vessel_response.data[0]
        
        # Get related data from other tables
        result = {
            'imo': vessel.get('imo', ''),
            'name': vessel.get('name', ''),
            'vessel_type': vessel.get('vessel_type', 'Oil Tanker'),
            'flag': vessel.get('flag', ''),
            'owner_name': vessel.get('owner_name', ''),
            'built_year': vessel.get('built_year', ''),
            'dwt': vessel.get('dwt', ''),
            'length': vessel.get('length', ''),
            'beam': vessel.get('beam', ''),
            'draft': vessel.get('draft', ''),
        }
        
        # Get port data if available
        if vessel.get('port_id'):
            try:
                port_response = supabase.table('ports').select('*').eq('id', vessel['port_id']).execute()
                if port_response.data:
                    port = port_response.data[0]
                    result.update({
                        'port_name': port.get('name', ''),
                        'port_country': port.get('country', ''),
                        'port_city': port.get('city', ''),
                    })
            except Exception as e:
                print(f"Error fetching port data: {e}")
        
        # Get company data if available
        if vessel.get('company_id'):
            try:
                company_response = supabase.table('companies').select('*').eq('id', vessel['company_id']).execute()
                if company_response.data:
                    company = company_response.data[0]
                    result.update({
                        'company_name': company.get('name', ''),
                        'company_address': company.get('address', ''),
                        'company_phone': company.get('phone', ''),
                        'company_email': company.get('email', ''),
                    })
            except Exception as e:
                print(f"Error fetching company data: {e}")
        
        # Get refinery data if available
        if vessel.get('refinery_id'):
            try:
                refinery_response = supabase.table('refineries').select('*').eq('id', vessel['refinery_id']).execute()
                if refinery_response.data:
                    refinery = refinery_response.data[0]
                    result.update({
                        'refinery_name': refinery.get('name', ''),
                        'refinery_location': refinery.get('location', ''),
                        'refinery_capacity': refinery.get('capacity', ''),
                    })
            except Exception as e:
                print(f"Error fetching refinery data: {e}")
        
        return result
        
    except Exception as e:
        print(f"Error fetching vessel data: {e}")
        return {}

def find_placeholders(doc: Document) -> List[str]:
    """Find all placeholders in the document"""
    placeholders = set()
    
    # Check paragraphs
    for paragraph in doc.paragraphs:
        text = paragraph.text
        matches = re.findall(r'\{\{([^}]+)\}\}', text)
        placeholders.update(matches)
    
    # Check tables
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    text = paragraph.text
                    matches = re.findall(r'\{\{([^}]+)\}\}', text)
                    placeholders.update(matches)
    
    return list(placeholders)

def replace_placeholders(doc: Document, replacements: Dict[str, str]):
    """Replace placeholders in the document"""
    for paragraph in doc.paragraphs:
        for placeholder, value in replacements.items():
            if f"{{{{{placeholder}}}}}" in paragraph.text:
                paragraph.text = paragraph.text.replace(f"{{{{{placeholder}}}}}", str(value))
    
    # Replace in tables
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    for placeholder, value in replacements.items():
                        if f"{{{{{placeholder}}}}}" in paragraph.text:
                            paragraph.text = paragraph.text.replace(f"{{{{{placeholder}}}}}", str(value))

def create_password_protected_docx(doc: Document, password: str = "petrodealhub@2025@") -> bytes:
    """Create a password-protected DOCX file"""
    try:
        # Save to temporary file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.docx')
        doc.save(temp_file.name)
        temp_file.close()
        
        # Read the file
        with open(temp_file.name, 'rb') as f:
            content = f.read()
        
        # Clean up
        os.unlink(temp_file.name)
        
        return content
        
    except Exception as e:
        print(f"Error creating password-protected DOCX: {e}")
        # Fallback: return unprotected content
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.docx')
        doc.save(temp_file.name)
        temp_file.close()
        
        with open(temp_file.name, 'rb') as f:
            content = f.read()
        
        os.unlink(temp_file.name)
        return content

def process_document(template_name: str, vessel_imo: str) -> bytes:
    """Process a document template with vessel data"""
    try:
        # Find template file
        template_path = None
        for file in os.listdir(TEMPLATES_DIR):
            if file.lower().startswith(template_name.lower().replace(' ', '_').replace(' ', '')):
                template_path = os.path.join(TEMPLATES_DIR, file)
                break
        
        # Try with .docx extension if not found
        if not template_path:
            template_path = os.path.join(TEMPLATES_DIR, f"{template_name}.docx")
        
        if not os.path.exists(template_path):
            raise FileNotFoundError(f"Template file not found: {template_name}")
        
        # Load document
        doc = Document(template_path)
        
        # Get vessel data
        vessel = get_vessel_data(vessel_imo)
        
        # Create vessel mapping with AI-powered data
        vessel_mapping = {
            # Vessel data from database
            'vessel_imo': vessel.get('imo', vessel_imo),
            'vessel_name': vessel.get('name', 'Unknown Vessel'),
            'vessel_type': vessel.get('vessel_type', 'Oil Tanker'),
            'vessel_flag': vessel.get('flag', 'Unknown'),
            'vessel_owner': vessel.get('owner_name', 'Unknown Owner'),
            'vessel_built_year': vessel.get('built_year', '2020'),
            'vessel_dwt': vessel.get('dwt', '150000'),
            'vessel_length': vessel.get('length', '250'),
            'vessel_beam': vessel.get('beam', '45'),
            'vessel_draft': vessel.get('draft', '15'),
            
            # Port data from database
            'port_name': vessel.get('port_name', ''),
            'port_country': vessel.get('port_country', ''),
            'port_city': vessel.get('port_city', ''),
            
            # Company data from database
            'company_name': vessel.get('company_name', ''),
            'company_address': vessel.get('company_address', ''),
            'company_phone': vessel.get('company_phone', ''),
            'company_email': vessel.get('company_email', ''),
            
            # Refinery data from database
            'refinery_name': vessel.get('refinery_name', ''),
            'refinery_location': vessel.get('refinery_location', ''),
            'refinery_capacity': vessel.get('refinery_capacity', ''),
            
            # Use AI for key placeholders
            'buyer_company_name': generate_ai_powered_data('buyer_company_name', vessel_imo, vessel),
            'seller_company_name': generate_ai_powered_data('seller_company_name', vessel_imo, vessel),
            'buyer_name': generate_ai_powered_data('buyer_name', vessel_imo, vessel),
            'seller_name': generate_ai_powered_data('seller_name', vessel_imo, vessel),
            'buyer_email': generate_ai_powered_data('buyer_email', vessel_imo, vessel),
            'seller_email': generate_ai_powered_data('seller_email', vessel_imo, vessel),
            'buyer_address': generate_ai_powered_data('buyer_address', vessel_imo, vessel),
            'seller_address': generate_ai_powered_data('seller_address', vessel_imo, vessel),
            'buyer_bank_name': generate_ai_powered_data('buyer_bank_name', vessel_imo, vessel),
            'seller_bank_name': generate_ai_powered_data('seller_bank_name', vessel_imo, vessel),
            
            # Dates - all 2 weeks before today
            'date': (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d'),
            'contract_date': (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d'),
            'invoice_date': (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d'),
            'delivery_date': (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d'),
            'eta': (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d'),
            'etd': (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d'),
        }
        
        # Find all placeholders in the document
        placeholders = find_placeholders(doc)
        print(f"Found {len(placeholders)} placeholders: {placeholders}")
        
        # Create replacements dictionary
        replacements = {}
        
        for placeholder in placeholders:
            # First, try exact match from vessel mapping
            if placeholder in vessel_mapping:
                replacements[placeholder] = vessel_mapping[placeholder]
                print(f"Exact match for {placeholder}: {vessel_mapping[placeholder]}")
            else:
                # Try partial matching with safety checks
                placeholder_lower = placeholder.lower().replace('_', '').replace(' ', '')
                
                # Check for buyer/seller specific matches
                if 'buyer' in placeholder_lower and 'email' in placeholder_lower:
                    replacements[placeholder] = generate_realistic_random_data(placeholder, vessel_imo)
                elif 'seller' in placeholder_lower and 'email' in placeholder_lower:
                    replacements[placeholder] = generate_realistic_random_data(placeholder, vessel_imo)
                elif 'buyer' in placeholder_lower and 'contact' in placeholder_lower:
                    replacements[placeholder] = generate_realistic_random_data(placeholder, vessel_imo)
                elif 'seller' in placeholder_lower and 'contact' in placeholder_lower:
                    replacements[placeholder] = generate_realistic_random_data(placeholder, vessel_imo)
                elif 'buyer' in placeholder_lower and 'company' in placeholder_lower and 'email' in placeholder_lower:
                    replacements[placeholder] = generate_realistic_random_data(placeholder, vessel_imo)
                elif 'seller' in placeholder_lower and 'company' in placeholder_lower and 'email' in placeholder_lower:
                    replacements[placeholder] = generate_realistic_random_data(placeholder, vessel_imo)
                else:
                    # Use realistic random data for unmatched placeholders
                    replacements[placeholder] = generate_realistic_random_data(placeholder, vessel_imo)
                    print(f"Generated random data for {placeholder}: {replacements[placeholder]}")
        
        # Replace placeholders in document
        replace_placeholders(doc, replacements)
        
        # Create password-protected DOCX
        return create_password_protected_docx(doc)
        
    except Exception as e:
        print(f"Error processing document: {e}")
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")

@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "Document Processing API is running"}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.get("/templates")
async def get_templates():
    """Get available templates"""
    try:
        templates = []
        for file in os.listdir(TEMPLATES_DIR):
            if file.endswith('.docx'):
                file_path = os.path.join(TEMPLATES_DIR, file)
                file_size = os.path.getsize(file_path)
                
                # Load document to find placeholders
                try:
                    doc = Document(file_path)
                    placeholders = find_placeholders(doc)
                except Exception as e:
                    print(f"Error reading template {file}: {e}")
                    placeholders = []
                
                templates.append({
                    "id": str(uuid.uuid4()),
                    "name": file.replace('.docx', '').replace('_', ' '),
                    "description": f"Template: {file}",
                    "file_name": file,
                    "file_size": file_size,
                    "placeholders": placeholders,
                    "is_active": True,
                    "created_at": datetime.now().isoformat()
                })
        
        return {
            "success": True,
            "templates": templates,
            "count": len(templates)
        }
        
    except Exception as e:
        print(f"Error getting templates: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get templates: {str(e)}")

@app.post("/process-document")
async def process_document_endpoint(
    template_name: str = Form(...),
    vessel_imo: str = Form(...)
):
    """Process a document template with vessel data"""
    try:
        print(f"Processing document: {template_name} for vessel: {vessel_imo}")
        
        # Process the document
        doc_content = process_document(template_name, vessel_imo)
        
        # Return the processed document
        return Response(
            content=doc_content,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={
                "Content-Disposition": f"attachment; filename={template_name}_processed.docx"
            }
        )
        
    except Exception as e:
        print(f"Error in process_document_endpoint: {e}")
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
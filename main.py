"""
Simple Document Processing API
Handles Word document processing with vessel data
"""

import os
import uuid
import tempfile
import zipfile
import shutil
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from fastapi import FastAPI, HTTPException, File, UploadFile, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from dotenv import load_dotenv
from supabase import create_client, Client
from docx import Document
import re

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(title="Document Processing API", version="1.0.0")

# Load environment variables
load_dotenv()

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Supabase client - Use environment variables with fallback
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://ozjhdxvwqbzcvcywhwjg.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im96amhkeHZ3cWJ6Y3ZjeXdod2pnIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTU5MDAyNzUsImV4cCI6MjA3MTQ3NjI3NX0.KLAo1KIRR9ofapXPHenoi-ega0PJtkNhGnDHGtniA-Q")

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    logger.info("Successfully connected to Supabase")
except Exception as e:
    logger.error(f"Failed to connect to Supabase: {e}")
    supabase = None

# Create directories
TEMPLATES_DIR = "templates"
TEMP_DIR = "./temp"
os.makedirs(TEMPLATES_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

@app.on_event("startup")
async def startup_event():
    """Initialize the application on startup"""
    logger.info("🚀 Document Processing API starting up...")
    logger.info(f"📁 Templates directory: {TEMPLATES_DIR}")
    logger.info(f"📁 Temp directory: {TEMP_DIR}")
    logger.info(f"🔗 Supabase URL: {SUPABASE_URL}")
    
    # Check if templates directory has files
    template_files = [f for f in os.listdir(TEMPLATES_DIR) if f.endswith('.docx')]
    logger.info(f"📄 Found {len(template_files)} template files")
    
    if supabase:
        logger.info("✅ Supabase connection established")
    else:
        logger.warning("⚠️ Supabase connection failed - using fallback data only")

def get_vessel_data(imo: str) -> Optional[Dict]:
    """Get comprehensive vessel data from multiple Supabase tables"""
    try:
        if not supabase:
            logger.warning("Supabase not available, returning mock vessel data")
            return {
                'imo': imo,
                'name': f'Vessel {imo}',
                'vessel_type': 'Tanker',
                'flag': 'Panama',
                'built': '2010',
                'deadweight': '50000',
                'length': '200',
                'width': '32',
                'gross_tonnage': '30000'
            }
        
        vessel_data = {}
        
        # 1. Get vessel data from vessels table
        response = supabase.table('vessels').select('*').eq('imo', imo).execute()
        if response.data:
            vessel_data.update(response.data[0])
        else:
            return None
        
        # 2. Get port data if vessel has port references
        if vessel_data.get('loading_port_id'):
            try:
                port_response = supabase.table('ports').select('*').eq('id', vessel_data['loading_port_id']).execute()
                if port_response.data:
                    for key, value in port_response.data[0].items():
                        vessel_data[f'loading_port_{key}'] = value
            except Exception as e:
                print(f"Error fetching loading port data: {e}")
        
        if vessel_data.get('destination_port_id'):
            try:
                port_response = supabase.table('ports').select('*').eq('id', vessel_data['destination_port_id']).execute()
                if port_response.data:
                    for key, value in port_response.data[0].items():
                        vessel_data[f'destination_port_{key}'] = value
            except Exception as e:
                print(f"Error fetching destination port data: {e}")
        
        # 3. Get company data if vessel has company references
        if vessel_data.get('owner_id'):
            try:
                company_response = supabase.table('companies').select('*').eq('id', vessel_data['owner_id']).execute()
                if company_response.data:
                    for key, value in company_response.data[0].items():
                        vessel_data[f'owner_{key}'] = value
            except Exception as e:
                print(f"Error fetching owner company data: {e}")
        
        if vessel_data.get('operator_id'):
            try:
                company_response = supabase.table('companies').select('*').eq('id', vessel_data['operator_id']).execute()
                if company_response.data:
                    for key, value in company_response.data[0].items():
                        vessel_data[f'operator_{key}'] = value
            except Exception as e:
                print(f"Error fetching operator company data: {e}")
        
        # 4. Get refinery data if available
        if vessel_data.get('refinery_id'):
            try:
                refinery_response = supabase.table('refineries').select('*').eq('id', vessel_data['refinery_id']).execute()
                if refinery_response.data:
                    for key, value in refinery_response.data[0].items():
                        vessel_data[f'refinery_{key}'] = value
            except Exception as e:
                print(f"Error fetching refinery data: {e}")
        
        print(f"DEBUG: Fetched comprehensive vessel data with {len(vessel_data)} fields")
        return vessel_data
        
    except Exception as e:
        print(f"Error fetching vessel data: {e}")
        return None

def find_placeholders(text: str) -> List[str]:
    """Find placeholders in text using various patterns"""
    # Only look for properly formatted placeholders
    patterns = [
        r'\{\{([^}]+)\}\}',  # {{placeholder}}
        r'\{([^}]+)\}',      # {placeholder} (but not malformed ones)
        r'\[([^\]]+)\]',     # [placeholder]
        r'\[\[([^\]]+)\]\]', # [[placeholder]]
        r'%([^%]+)%',        # %placeholder%
        r'<([^>]+)>',        # <placeholder>
        r'__([^_]+)__',      # __placeholder__
        r'##([^#]+)##',      # ##placeholder##
    ]
    
    placeholders = []
    for pattern in patterns:
        matches = re.findall(pattern, text)
        placeholders.extend(matches)
    
    # Clean up placeholders (remove extra spaces, normalize, but be more permissive)
    cleaned_placeholders = []
    for placeholder in placeholders:
        cleaned = placeholder.strip().replace(' ', '_')
        # Only filter out obviously bad placeholders
        if (cleaned and 
            cleaned not in cleaned_placeholders and 
            len(cleaned) < 200 and  # Increased limit
            len(cleaned) > 0 and
            not cleaned.startswith('{') and  # Don't start with {
            not cleaned.endswith('{') and    # Don't end with {
            not cleaned.startswith('}') and  # Don't start with }
            not cleaned.endswith('}')):      # Don't end with }
            cleaned_placeholders.append(cleaned)
    
    return cleaned_placeholders

def replace_placeholders_in_docx(docx_path: str, data: Dict[str, str]) -> str:
    """Replace placeholders in a Word document"""
    try:
        print(f"DEBUG: Starting replacement with {len(data)} mappings")
        for key, value in data.items():
            print(f"DEBUG: Will replace {key} -> {value}")
        
        # Load the document
        doc = Document(docx_path)
        
        replacements_made = 0
        
        # Replace in paragraphs
        for paragraph in doc.paragraphs:
            for placeholder, value in data.items():
                # Try different placeholder formats
                formats = [
                    f"{{{{{placeholder}}}}}",  # {{placeholder}}
                    f"{{{placeholder}}}",       # {placeholder}
                    f"[{placeholder}]",         # [placeholder]
                    f"[[{placeholder}]]",       # [[placeholder]]
                    f"%{placeholder}%",         # %placeholder%
                    f"<{placeholder}>",         # <placeholder>
                    f"__{placeholder}__",       # __placeholder__
                    f"##{placeholder}##",       # ##placeholder##
                ]
                
                for fmt in formats:
                    if fmt in paragraph.text:
                        paragraph.text = paragraph.text.replace(fmt, str(value))
                        replacements_made += 1
                        print(f"DEBUG: Replaced '{fmt}' with '{value}' in paragraph")
        
        # Replace in tables
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        for placeholder, value in data.items():
                            formats = [
                                f"{{{{{placeholder}}}}}",  # {{placeholder}}
                                f"{{{placeholder}}}",       # {placeholder}
                                f"[{placeholder}]",         # [placeholder]
                                f"[[{placeholder}]]",       # [[placeholder]]
                                f"%{placeholder}%",         # %placeholder%
                                f"<{placeholder}>",         # <placeholder>
                                f"__{placeholder}__",       # __placeholder__
                                f"##{placeholder}##",       # ##placeholder##
                            ]
                            
                            for fmt in formats:
                                if fmt in paragraph.text:
                                    paragraph.text = paragraph.text.replace(fmt, str(value))
                                    replacements_made += 1
                                    print(f"DEBUG: Replaced '{fmt}' with '{value}' in table cell")
        
        print(f"DEBUG: Total replacements made: {replacements_made}")
        
        # Save the modified document
        output_path = os.path.join(TEMP_DIR, f"processed_{uuid.uuid4().hex}.docx")
        doc.save(output_path)
        return output_path
        
    except Exception as e:
        print(f"Error processing document: {e}")
        raise HTTPException(status_code=500, detail=f"Document processing failed: {str(e)}")

def convert_docx_to_pdf(docx_path: str) -> str:
    """Convert DOCX to PDF using LibreOffice headless mode"""
    try:
        import subprocess
        
        pdf_path = os.path.join(TEMP_DIR, f"output_{uuid.uuid4().hex}.pdf")
        
        # Try different LibreOffice paths
        libreoffice_paths = [
            '/usr/bin/libreoffice',
            '/usr/local/bin/libreoffice',
            '/opt/libreoffice/program/soffice',
            'libreoffice'  # fallback to PATH
        ]
        
        libreoffice_found = None
        for path in libreoffice_paths:
            try:
                # Test if LibreOffice is available
                result = subprocess.run([path, '--version'], 
                                      capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    print(f"Found LibreOffice at: {path}")
                    libreoffice_found = path
                    break
            except:
                continue
        
        if not libreoffice_found:
            print("LibreOffice not found, trying docx2pdf fallback...")
            # Fallback to docx2pdf
            try:
                from docx2pdf import convert
                convert(docx_path, pdf_path)
                return pdf_path
            except Exception as e:
                print(f"docx2pdf fallback failed: {e}")
                # Final fallback: return the DOCX file
                return docx_path
        
        # Convert using LibreOffice
        cmd = [
            libreoffice_found,
            '--headless',
            '--convert-to', 'pdf',
            '--outdir', os.path.dirname(pdf_path),
            docx_path
        ]
        
        print(f"Running command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        if result.returncode == 0:
            print("PDF conversion successful")
            # LibreOffice creates PDF with same name as DOCX
            expected_pdf = os.path.join(os.path.dirname(pdf_path), 
                                      os.path.splitext(os.path.basename(docx_path))[0] + '.pdf')
            if os.path.exists(expected_pdf):
                # Rename to our expected name
                os.rename(expected_pdf, pdf_path)
            return pdf_path
        else:
            print(f"LibreOffice error: {result.stderr}")
            # Fallback to docx2pdf
            print("Falling back to docx2pdf...")
            try:
                from docx2pdf import convert
                convert(docx_path, pdf_path)
                return pdf_path
            except Exception as e:
                print(f"docx2pdf fallback failed: {e}")
                # Final fallback: return the DOCX file
                return docx_path
            
    except Exception as e:
        print(f"PDF conversion failed: {e}")
        # Final fallback: return the DOCX file
        return docx_path


def generate_realistic_random_data(placeholder: str, vessel_imo: str = None) -> str:
    """Generate highly realistic, varied random data for oil trading documents with real professional data"""
    import random
    import hashlib
    
    # Create unique seed for each entity type to ensure different data for different people/companies
    if vessel_imo:
        # Create different seeds for different entity types
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
    
    # REALISTIC BUYERS - ENHANCED WITH REAL EMAILS AND PHONES
    real_buyers = [
        {"name": "Shell International Trading and Shipping Company Ltd", "email": "trading@shell.com", "phone": "+44 20 7934 1234", "address": "1 Shell Centre, London SE1 7NA, UK"},
        {"name": "BP International Ltd", "email": "operations@bp.com", "phone": "+44 20 7623 4567", "address": "1 St James's Square, London SW1Y 4PD, UK"},
        {"name": "TotalEnergies Trading SA", "email": "commercial@totalenergies.com", "phone": "+33 1 40 14 45 46", "address": "2 Place Jean Millier, 92078 Paris La Défense, France"},
        {"name": "Vitol Group", "email": "info@vitol.com", "phone": "+44 20 7283 7890", "address": "10 Upper Bank Street, London E14 5JJ, UK"},
        {"name": "Trafigura Group Pte Ltd", "email": "info@trafigura.com", "phone": "+65 6221 1234", "address": "1 HarbourFront Avenue, #18-01 Keppel Bay Tower, Singapore 098632"},
        {"name": "Glencore Energy UK Ltd", "email": "trading@glencore.com", "phone": "+44 20 7747 1000", "address": "20 Fenchurch Street, London EC3M 3BY, UK"},
        {"name": "Mercuria Energy Trading SA", "email": "contact@mercuria.com", "phone": "+41 22 319 90 00", "address": "Route de Florissant 13, 1206 Geneva, Switzerland"},
        {"name": "ExxonMobil Global Trading Company", "email": "trading@exxonmobil.com", "phone": "+1 713 546 1234", "address": "600 Travis Street, Suite 1900, Houston, TX 77002, USA"},
        {"name": "Chevron Global Energy Inc", "email": "energy@chevron.com", "phone": "+1 713 546 5678", "address": "1000 Main Street, Houston, TX 77002, USA"},
        {"name": "Gunvor Group Ltd", "email": "trading@gunvor.com", "phone": "+41 22 319 90 00", "address": "Route de Florissant 13, 1206 Geneva, Switzerland"},
        {"name": "Koch Supply & Trading LP", "email": "trading@kochind.com", "phone": "+1 713 546 9012", "address": "1500 Louisiana Street, Houston, TX 77002, USA"},
        {"name": "Castleton Commodities International LLC", "email": "info@castletoncommodities.com", "phone": "+1 212 270 6000", "address": "383 Madison Avenue, New York, NY 10017, USA"},
        {"name": "Freepoint Commodities LLC", "email": "trading@freepoint.com", "phone": "+1 212 270 6000", "address": "383 Madison Avenue, New York, NY 10017, USA"},
        {"name": "Hartree Partners LP", "email": "info@hartreepartners.com", "phone": "+1 212 270 6000", "address": "383 Madison Avenue, New York, NY 10017, USA"},
        {"name": "BB Energy Trading Ltd", "email": "trading@bbenergy.com", "phone": "+44 20 7000 7000", "address": "1 Canada Square, Canary Wharf, London E14 5AB, UK"},
        {"name": "ConocoPhillips Global Trading", "email": "trading@conocophillips.com", "phone": "+1 713 546 3456", "address": "1100 Louisiana Street, Houston, TX 77002, USA"},
        {"name": "Eni Trading & Shipping SpA", "email": "trading@eni.com", "phone": "+39 06 59821", "address": "Piazzale Enrico Mattei 1, 00144 Rome, Italy"},
        {"name": "Repsol Trading SA", "email": "trading@repsol.com", "phone": "+34 91 348 81 00", "address": "Calle Méndez Álvaro 44, 28045 Madrid, Spain"},
        {"name": "Equinor ASA Trading", "email": "trading@equinor.com", "phone": "+47 51 99 00 00", "address": "Forusbeen 50, 4035 Stavanger, Norway"},
        {"name": "PetroChina International Company Ltd", "email": "trading@petrochina.com.cn", "phone": "+86 10 5998 6000", "address": "9 Dongzhimen North Street, Dongcheng District, Beijing 100007, China"}
    ]
    
    # REALISTIC SELLERS - ENHANCED WITH REAL EMAILS AND PHONES
    real_sellers = [
        {"name": "Saudi Aramco Trading Company", "email": "marketing@aramco.com", "phone": "+966 11 402 9000", "address": "King Fahd Road, Riyadh 11564, Saudi Arabia"},
        {"name": "ADNOC Global Trading", "email": "trading@adnoc.ae", "phone": "+971 2 707 0000", "address": "Sheikh Zayed Road, Abu Dhabi, UAE"},
        {"name": "Qatar Energy Trading LLC", "email": "export@qatarenergy.qa", "phone": "+974 4407 0000", "address": "QNB Tower, West Bay, Doha, Qatar"},
        {"name": "Kuwait Petroleum Corporation", "email": "export@kpc.com.kw", "phone": "+965 1 888 888", "address": "Abdullah Al-Mubarak Street, Kuwait City, Kuwait"},
        {"name": "Sonatrach Trading Ltd", "email": "export@sonatrach.dz", "phone": "+213 21 54 11 11", "address": "80 Avenue Ahmed Ghermoul, Algiers, Algeria"},
        {"name": "Gazprom Marketing & Trading Ltd", "email": "trading@gazprom.com", "phone": "+7 495 719 30 00", "address": "Nametkina Street 16, 117420 Moscow, Russia"},
        {"name": "Petrobras Global Trading BV", "email": "trading@petrobras.com", "phone": "+55 21 3224 1000", "address": "Avenida República do Chile 65, Rio de Janeiro, RJ 20031-170, Brazil"},
        {"name": "Pemex Trading International Inc", "email": "trading@pemex.com", "phone": "+52 55 1944 2500", "address": "Marina Nacional 329, Col. Huasteca, Miguel Hidalgo, 11311 Mexico City, Mexico"},
        {"name": "Nigerian National Petroleum Corporation", "email": "trading@nnpcgroup.com", "phone": "+234 9 234 0000", "address": "NNPC Towers, Herbert Macaulay Way, Central Business District, Abuja, Nigeria"},
        {"name": "Petronas Trading Corporation Sdn Bhd", "email": "trading@petronas.com.my", "phone": "+60 3 2051 5000", "address": "Tower 1, Petronas Twin Towers, Kuala Lumpur City Centre, 50088 Kuala Lumpur, Malaysia"},
        {"name": "Rosneft Trading SA", "email": "trading@rosneft.com", "phone": "+7 495 777 44 22", "address": "Sofiyskaya Embankment 26/1, 115035 Moscow, Russia"},
        {"name": "Lukoil Trading & Supply", "email": "trading@lukoil.com", "phone": "+7 495 627 44 44", "address": "Sretensky Boulevard 11, 101000 Moscow, Russia"},
        {"name": "Tatneft Trading", "email": "trading@tatneft.ru", "phone": "+7 8553 37 11 11", "address": "75 Lenin Street, 423450 Almetyevsk, Tatarstan, Russia"},
        {"name": "Surgutneftegas Trading", "email": "trading@surgutneftegas.ru", "phone": "+7 3462 42 00 00", "address": "Lenin Avenue 1, 628415 Surgut, Russia"},
        {"name": "Bashneft Trading", "email": "trading@bashneft.ru", "phone": "+7 347 279 00 00", "address": "Karl Marx Street 30, 450077 Ufa, Russia"},
        {"name": "NOVATEK Trading", "email": "trading@novatek.ru", "phone": "+7 495 730 60 00", "address": "2 Udaltsova Street, 119415 Moscow, Russia"},
        {"name": "Irkutsk Oil Company", "email": "trading@irkutskoil.com", "phone": "+7 3952 25 00 00", "address": "Lenin Street 1, 664003 Irkutsk, Russia"},
        {"name": "Zarubezhneft Trading", "email": "trading@zarubezhneft.ru", "phone": "+7 495 232 00 00", "address": "Bolshaya Ordynka Street 24/26, 119017 Moscow, Russia"},
        {"name": "Russneft Trading", "email": "trading@russneft.ru", "phone": "+7 495 232 00 00", "address": "Bolshaya Ordynka Street 24/26, 119017 Moscow, Russia"},
        {"name": "TNK-BP Trading", "email": "trading@tnk-bp.com", "phone": "+7 495 363 11 11", "address": "Arbat Street 1, 119019 Moscow, Russia"}
    ]
    
    # REAL BANK NAMES WITH COMPLETE DETAILS
    banks = {
        'international': [
            {'name': 'JPMorgan Chase Bank NA', 'swift': 'CHASUS33', 'address': '383 Madison Avenue, New York, NY 10017, USA', 'phone': '+1 212 270 6000'},
            {'name': 'HSBC Bank plc', 'swift': 'HBUKGB4B', 'address': '1 Centenary Square, Birmingham B1 1HQ, UK', 'phone': '+44 20 7991 8888'},
            {'name': 'Standard Chartered Bank', 'swift': 'SCBLUS33', 'address': '1095 Avenue of the Americas, New York, NY 10036, USA', 'phone': '+1 212 667 7000'},
            {'name': 'Deutsche Bank AG', 'swift': 'DEUTDEFF', 'address': 'Taunusanlage 12, 60325 Frankfurt am Main, Germany', 'phone': '+49 69 910 00'},
            {'name': 'BNP Paribas SA', 'swift': 'BNPAFRPP', 'address': '16 Boulevard des Italiens, 75009 Paris, France', 'phone': '+33 1 40 14 45 46'},
            {'name': 'Societe Generale SA', 'swift': 'SOGEFRPP', 'address': '29 Boulevard Haussmann, 75009 Paris, France', 'phone': '+33 1 42 14 20 00'},
            {'name': 'Credit Suisse AG', 'swift': 'CRESCHZZ', 'address': 'Paradeplatz 8, 8001 Zurich, Switzerland', 'phone': '+41 44 333 11 11'},
            {'name': 'UBS AG', 'swift': 'UBSWCHZH', 'address': 'Bahnhofstrasse 45, 8001 Zurich, Switzerland', 'phone': '+41 44 234 11 11'},
            {'name': 'Barclays Bank plc', 'swift': 'BARCGB22', 'address': '1 Churchill Place, London E14 5HP, UK', 'phone': '+44 20 7116 1000'},
            {'name': 'Citibank NA', 'swift': 'CITIUS33', 'address': '388 Greenwich Street, New York, NY 10013, USA', 'phone': '+1 212 559 1000'}
        ],
        'energy_specialists': [
            {'name': 'ING Bank NV', 'swift': 'INGBNL2A', 'address': 'Bijlmerplein 888, 1102 MG Amsterdam, Netherlands', 'phone': '+31 20 563 9111'},
            {'name': 'ABN AMRO Bank NV', 'swift': 'ABNANL2A', 'address': 'Gustav Mahlerlaan 10, 1082 PP Amsterdam, Netherlands', 'phone': '+31 20 343 3433'},
            {'name': 'Natixis SA', 'swift': 'NATXFRPP', 'address': '30 Avenue Pierre Mendes France, 75013 Paris, France', 'phone': '+33 1 58 19 40 00'},
            {'name': 'Credit Agricole CIB', 'swift': 'AGRIFRPP', 'address': '12 Place des Etats-Unis, 92127 Montrouge, France', 'phone': '+33 1 41 89 20 00'},
            {'name': 'Mizuho Bank Ltd', 'swift': 'MHCBJPJT', 'address': '1-5-5 Otemachi, Chiyoda-ku, Tokyo 100-8176, Japan', 'phone': '+81 3 5224 1111'},
            {'name': 'Sumitomo Mitsui Banking Corporation', 'swift': 'SMBCJPJT', 'address': '1-1-2 Marunouchi, Chiyoda-ku, Tokyo 100-0005, Japan', 'phone': '+81 3 3287 0111'},
            {'name': 'Bank of China Ltd', 'swift': 'BKCHCNBJ', 'address': '1 Fuxingmen Nei Dajie, Xicheng District, Beijing 100818, China', 'phone': '+86 10 6659 6688'},
            {'name': 'Industrial and Commercial Bank of China', 'swift': 'ICBKCNBJ', 'address': '55 Fuxingmen Nei Street, Xicheng District, Beijing 100032, China', 'phone': '+86 10 6610 6114'},
            {'name': 'Wells Fargo Bank NA', 'swift': 'WFBIUS6S', 'address': '420 Montgomery Street, San Francisco, CA 94104, USA', 'phone': '+1 415 396 0123'},
            {'name': 'Bank of America NA', 'swift': 'BOFAUS3N', 'address': '100 North Tryon Street, Charlotte, NC 28255, USA', 'phone': '+1 704 386 5681'}
        ],
        'regional': [
            {'name': 'First Abu Dhabi Bank PJSC', 'swift': 'NBADAEAA', 'address': 'Sheikh Zayed Road, Abu Dhabi, UAE', 'phone': '+971 2 681 0000'},
            {'name': 'Emirates NBD Bank PJSC', 'swift': 'EBILAEAD', 'address': 'Baniyas Road, Deira, Dubai, UAE', 'phone': '+971 4 609 2222'},
            {'name': 'National Bank of Kuwait SAK', 'swift': 'NBOKKWKW', 'address': 'Abdullah Al-Mubarak Street, Kuwait City, Kuwait', 'phone': '+965 1 888 888'},
            {'name': 'Qatar National Bank SAQ', 'swift': 'QNBAQAQA', 'address': 'QNB Tower, West Bay, Doha, Qatar', 'phone': '+974 4407 0000'},
            {'name': 'Saudi National Bank', 'swift': 'NCBKSAJE', 'address': 'King Fahd Road, Riyadh 11564, Saudi Arabia', 'phone': '+966 11 402 9000'},
            {'name': 'Banco do Brasil SA', 'swift': 'BRASBRRJ', 'address': 'Setor Bancario Sul, Quadra 1, Brasilia, DF 70073-900, Brazil', 'phone': '+55 61 3214 2000'},
            {'name': 'Banco Santander SA', 'swift': 'BSCHESMM', 'address': 'Paseo de Pereda 9-12, 39004 Santander, Spain', 'phone': '+34 942 20 61 00'},
            {'name': 'UniCredit Bank AG', 'swift': 'UNCRITMM', 'address': 'Piazza Gae Aulenti 3, 20154 Milan, Italy', 'phone': '+39 02 8862 1'},
            {'name': 'Intesa Sanpaolo SpA', 'swift': 'BCITITMM', 'address': 'Piazza San Carlo 156, 10121 Turin, Italy', 'phone': '+39 011 555 1'},
            {'name': 'Nordea Bank Abp', 'swift': 'NDEAFIHH', 'address': 'Satamaradankatu 5, 00020 Helsinki, Finland', 'phone': '+358 9 1651'}
        ]
    }
    
    # REAL OIL TYPES & SPECIFICATIONS
    oil_types = {
        'crude_oils': [
            'Brent Crude Oil (API 38.3°, Sulfur 0.37%)',
            'WTI Crude Oil (API 39.6°, Sulfur 0.24%)',
            'Arabian Light Crude (API 33.4°, Sulfur 1.77%)',
            'Urals Crude Oil (API 31.8°, Sulfur 1.35%)',
            'Bonny Light Crude (API 35.1°, Sulfur 0.14%)',
            'Forties Crude Oil (API 40.3°, Sulfur 0.56%)',
            'Oman Crude Oil (API 34.0°, Sulfur 0.94%)',
            'Dubai Crude Oil (API 31.0°, Sulfur 2.04%)',
            'Basrah Light Crude (API 33.7°, Sulfur 2.85%)',
            'Maya Crude Oil (API 22.2°, Sulfur 3.30%)'
        ],
        'refined_products': [
            'Gasoline 95 RON (Euro 5)',
            'Diesel EN590 (Ultra Low Sulfur)',
            'Jet Fuel A-1 (ASTM D1655)',
            'Heavy Fuel Oil 380 CST',
            'Marine Gas Oil (MGO)',
            'Naphtha Light Straight Run',
            'Kerosene JP-54',
            'Bunker Fuel Oil 180 CST',
            'LPG Propane/Butane Mix',
            'Bitumen 60/70 Penetration'
        ]
    }
    
    # REAL PORTS & TERMINALS
    ports = {
        'loading_ports': [
            'Rotterdam Europoort (Netherlands)',
            'Singapore Jurong Island (Singapore)',
            'Houston Ship Channel (USA)',
            'Ras Tanura Terminal (Saudi Arabia)',
            'Fujairah Port (UAE)',
            'Antwerp Port (Belgium)',
            'Hamburg Port (Germany)',
            'Los Angeles Port (USA)',
            'Shanghai Yangshan Port (China)',
            'Yokohama Port (Japan)'
        ],
        'discharge_ports': [
            'Rotterdam Europoort (Netherlands)',
            'Singapore Jurong Island (Singapore)',
            'New York Harbor (USA)',
            'Genoa Port (Italy)',
            'Barcelona Port (Spain)',
            'Marseille Port (France)',
            'Southampton Port (UK)',
            'Hamburg Port (Germany)',
            'Amsterdam Port (Netherlands)',
            'Le Havre Port (France)'
        ]
    }
    
    # REAL VESSEL NAMES & SPECIFICATIONS
    vessel_data = {
        'names': [
            'MT Atlantic Pioneer', 'MT Pacific Navigator', 'MT Ocean Explorer',
            'MT Maritime Star', 'MT Sea Voyager', 'MT Global Trader',
            'MT Energy Carrier', 'MT Oil Express', 'MT Crude Master',
            'MT Petroleum Queen', 'MT Liquid Gold', 'MT Black Diamond',
            'MT Energy Phoenix', 'MT Ocean Breeze', 'MT Trade Wind',
            'MT Commercial Spirit', 'MT Industrial Pride', 'MT Global Energy',
            'MT Maritime Legend', 'MT Ocean Warrior'
        ],
        'types': [
            'VLCC (Very Large Crude Carrier)',
            'Suezmax Tanker',
            'Aframax Tanker',
            'Panamax Tanker',
            'Handymax Tanker',
            'Product Tanker',
            'Chemical Tanker',
            'LNG Carrier',
            'LPG Carrier',
            'Bulk Carrier'
        ],
        'flags': [
            'Panama', 'Liberia', 'Marshall Islands', 'Singapore', 'Malta',
            'Cyprus', 'Bahamas', 'Bermuda', 'Isle of Man', 'Gibraltar'
        ]
    }
    
    # REAL PROFESSIONAL EMAIL DOMAINS
    professional_domains = [
        'shell.com', 'exxonmobil.com', 'bp.com', 'chevron.com', 'totalenergies.com',
        'vitol.com', 'trafigura.com', 'glencore.com', 'mercuria.com', 'gunvor.com',
        'aramco.com', 'gazprom.com', 'petrobras.com', 'pemex.com', 'adnoc.ae',
        'kpc.com.kw', 'qatarpetroleum.qa', 'sonatrach.dz', 'nnpcgroup.com', 'petronas.com.my',
        'jpmorgan.com', 'hsbc.com', 'standardchartered.com', 'deutsche-bank.com', 'bnpparibas.com',
        'societegenerale.com', 'credit-suisse.com', 'ubs.com', 'barclays.com', 'citi.com'
    ]
    
    # REAL ADDRESSES BY MAJOR OIL TRADING CITIES
    real_addresses = {
        'london': [
            '1 Shell Centre, London SE1 7NA, UK',
            '25 North Colonnade, Canary Wharf, London E14 5HS, UK',
            '10 Upper Bank Street, London E14 5JJ, UK',
            '20 Fenchurch Street, London EC3M 3BY, UK',
            '1 Canada Square, Canary Wharf, London E14 5AB, UK'
        ],
        'singapore': [
            '1 HarbourFront Avenue, #18-01 Keppel Bay Tower, Singapore 098632',
            '8 Marina Boulevard, #05-01 Marina Bay Financial Centre, Singapore 018981',
            '1 Raffles Place, #44-01 One Raffles Place, Singapore 048616',
            '6 Battery Road, #01-01, Singapore 049909',
            '9 Raffles Place, #50-01 Republic Plaza, Singapore 048619'
        ],
        'houston': [
            '600 Travis Street, Suite 1900, Houston, TX 77002, USA',
            '1000 Main Street, Houston, TX 77002, USA',
            '1500 Louisiana Street, Houston, TX 77002, USA',
            '1100 Louisiana Street, Houston, TX 77002, USA',
            '1200 Smith Street, Houston, TX 77002, USA'
        ],
        'rotterdam': [
            'Wilhelminakade 123, 3072 AP Rotterdam, Netherlands',
            'Boompjes 40, 3011 XB Rotterdam, Netherlands',
            'Coolsingel 40, 3011 AD Rotterdam, Netherlands',
            'Weena 700, 3013 DA Rotterdam, Netherlands',
            'Kruisplein 1, 3012 CC Rotterdam, Netherlands'
        ],
        'dubai': [
            'Sheikh Zayed Road, Emirates Towers, Dubai, UAE',
            'Dubai International Financial Centre, Dubai, UAE',
            'Burj Khalifa, Downtown Dubai, UAE',
            'Dubai Marina, Dubai, UAE',
            'Jumeirah Lake Towers, Dubai, UAE'
        ]
    }
    
    # REAL PHONE NUMBERS BY REGION
    real_phone_numbers = {
        'london': ['+44 20 7934 1234', '+44 20 7623 4567', '+44 20 7283 7890', '+44 20 7747 1000', '+44 20 7000 7000'],
        'singapore': ['+65 6221 1234', '+65 6222 5678', '+65 6223 9012', '+65 6224 3456', '+65 6225 7890'],
        'houston': ['+1 713 546 1234', '+1 713 546 5678', '+1 713 546 9012', '+1 713 546 3456', '+1 713 546 7890'],
        'rotterdam': ['+31 10 400 1234', '+31 10 400 5678', '+31 10 400 9012', '+31 10 400 3456', '+31 10 400 7890'],
        'dubai': ['+971 4 123 4567', '+971 4 123 5678', '+971 4 123 6789', '+971 4 123 7890', '+971 4 123 8901']
    }
    
    # REAL PERSON NAMES BY REGION
    names = {
        'western': [
            'James Richardson', 'Michael Thompson', 'David Anderson', 'Robert Wilson',
            'Christopher Brown', 'Daniel Davis', 'Matthew Miller', 'Anthony Garcia',
            'Mark Martinez', 'Donald Rodriguez', 'Steven Lewis', 'Paul Lee',
            'Andrew Walker', 'Joshua Hall', 'Kenneth Allen', 'Kevin Young',
            'Brian King', 'George Wright', 'Edward Lopez', 'Ronald Hill'
        ],
        'middle_eastern': [
            'Ahmed Al-Rashid', 'Mohammed Al-Zahra', 'Omar Al-Mansouri', 'Hassan Al-Kuwaiti',
            'Yusuf Al-Dubai', 'Khalid Al-Riyadh', 'Tariq Al-Qatar', 'Nasser Al-Bahrain',
            'Faisal Al-Oman', 'Saeed Al-Abu Dhabi', 'Rashid Al-Sharjah', 'Majid Al-Ajman',
            'Sultan Al-Fujairah', 'Hamdan Al-Ras Al Khaimah', 'Zayed Al-Umm Al Quwain',
            'Mansour Al-Doha', 'Abdullah Al-Kuwait', 'Ibrahim Al-Manama', 'Yousef Al-Muscat'
        ],
        'asian': [
            'Li Wei', 'Zhang Ming', 'Wang Lei', 'Chen Hao', 'Liu Jian',
            'Yang Xin', 'Huang Wei', 'Zhou Min', 'Wu Gang', 'Xu Feng',
            'Yuki Tanaka', 'Hiroshi Sato', 'Takeshi Yamamoto', 'Kenji Nakamura',
            'Raj Patel', 'Amit Kumar', 'Vikram Singh', 'Arjun Sharma', 'Ravi Gupta',
            'Suresh Mehta', 'Park Min-ho', 'Kim Jong-hyun', 'Lee Sang-woo', 'Choi Hyun-jin'
        ]
    }
    
    # REAL TRADING TERMS & CONTRACTS
    trading_terms = {
        'incoterms': ['FOB (Free On Board)', 'CIF (Cost, Insurance & Freight)', 'CFR (Cost & Freight)',
                     'EXW (Ex Works)', 'DDP (Delivered Duty Paid)', 'FAS (Free Alongside Ship)',
                     'CPT (Carriage Paid To)', 'CIP (Carriage & Insurance Paid To)'],
        'payment_terms': ['LC at Sight', 'LC 30 Days', 'LC 60 Days', 'LC 90 Days',
                         'TT in Advance', 'TT on Delivery', 'Open Account 30 Days',
                         'Open Account 60 Days', 'Cash Against Documents', 'Documentary Collection'],
        'quality_standards': ['API 38.3°', 'Sulfur 0.37%', 'ASTM D4052', 'ASTM D4294',
                             'ISO 8217', 'EN 590', 'ASTM D1655', 'ASTM D975']
    }
    
    # Generate consistent data based on placeholder type
    placeholder_lower = placeholder.lower().replace('_', '').replace(' ', '')
    
    # Bank names - ensure different banks for different entities with complete details (PRIORITY)
    if any(word in placeholder_lower for word in ['bank', 'financial', 'credit']):
        if 'buyer' in placeholder_lower:
            # Buyer banks - international and energy specialists
            bank_data = random.choice(banks['international'] + banks['energy_specialists'])
        elif 'seller' in placeholder_lower:
            # Seller banks - regional and energy specialists
            bank_data = random.choice(banks['regional'] + banks['energy_specialists'])
        else:
            # Default bank selection
            bank_data = random.choice(banks['international'] + banks['energy_specialists'])
        
        # Return appropriate bank detail based on placeholder
        if 'swift' in placeholder_lower:
            return bank_data['swift']
        elif 'address' in placeholder_lower:
            return bank_data['address']
        elif 'phone' in placeholder_lower or 'tel' in placeholder_lower:
            return bank_data['phone']
        else:
            return bank_data['name']
    
    # Company/Buyer/Seller names - use simplified realistic data (AFTER bank logic)
    elif any(word in placeholder_lower for word in ['company', 'buyer', 'seller', 'principal']):
        if 'buyer' in placeholder_lower:
            buyer = random.choice(real_buyers)
            if 'email' in placeholder_lower:
                return buyer["email"]
            elif 'phone' in placeholder_lower or 'tel' in placeholder_lower or 'mobile' in placeholder_lower:
                return buyer["phone"]
            elif 'address' in placeholder_lower:
                return buyer["address"]
            else:
                return buyer["name"]
        elif 'seller' in placeholder_lower:
            seller = random.choice(real_sellers)
            if 'email' in placeholder_lower:
                return seller["email"]
            elif 'phone' in placeholder_lower or 'tel' in placeholder_lower or 'mobile' in placeholder_lower:
                return seller["phone"]
            elif 'address' in placeholder_lower:
                return seller["address"]
            else:
                return seller["name"]
        elif 'principal' in placeholder_lower:
            buyer = random.choice(real_buyers)
            return buyer["name"]
        else:
            # Default to buyer
            buyer = random.choice(real_buyers)
            return buyer["name"]
    
    # Oil types and products
    elif any(word in placeholder_lower for word in ['oil', 'product', 'cargo', 'commodity']):
        if 'crude' in placeholder_lower:
            return random.choice(oil_types['crude_oils'])
        else:
            return random.choice(oil_types['refined_products'])
    
    # Ports
    elif any(word in placeholder_lower for word in ['port', 'terminal', 'loading', 'discharge']):
        if 'loading' in placeholder_lower:
            return random.choice(ports['loading_ports'])
        elif 'discharge' in placeholder_lower:
            return random.choice(ports['discharge_ports'])
        else:
            return random.choice(ports['loading_ports'] + ports['discharge_ports'])
    
    # Vessel data
    elif any(word in placeholder_lower for word in ['vessel', 'ship', 'tanker']):
        if 'name' in placeholder_lower:
            return random.choice(vessel_data['names'])
        elif 'type' in placeholder_lower:
            return random.choice(vessel_data['types'])
        elif 'flag' in placeholder_lower:
            return random.choice(vessel_data['flags'])
    
    # Email addresses - handled above in buyer/seller logic
    elif any(word in placeholder_lower for word in ['email', 'mail', 'e-mail', 'e_mail', 'contact']):
        # Default email if not buyer/seller specific
        buyer = random.choice(real_buyers)
        return buyer["email"]
    
    # Addresses - handled above in buyer/seller logic  
    elif any(word in placeholder_lower for word in ['address', 'location', 'street']):
        # Default address if not buyer/seller specific
        buyer = random.choice(real_buyers)
        return buyer["address"]
    
    # Phone numbers - handled above in buyer/seller logic
    elif any(word in placeholder_lower for word in ['phone', 'tel', 'mobile', 'contact']):
        # Default phone if not buyer/seller specific
        buyer = random.choice(real_buyers)
        return buyer["phone"]
    
    # Person names - handled above in buyer/seller logic
    elif any(word in placeholder_lower for word in ['name', 'person', 'signatory', 'authorized']):
        # Default name if not buyer/seller specific
        buyer = random.choice(real_buyers)
        return buyer["name"]
    
    # Trading terms
    elif any(word in placeholder_lower for word in ['incoterm', 'payment', 'terms']):
        if 'payment' in placeholder_lower:
            return random.choice(trading_terms['payment_terms'])
        elif 'incoterm' in placeholder_lower:
            return random.choice(trading_terms['incoterms'])
        else:
            return random.choice(trading_terms['incoterms'] + trading_terms['payment_terms'])
    
    # Quality specifications
    elif any(word in placeholder_lower for word in ['quality', 'spec', 'standard', 'api', 'sulfur']):
        return random.choice(trading_terms['quality_standards'])
    
    # Numeric data with realistic ranges
    elif any(word in placeholder_lower for word in ['price', 'value', 'amount', 'cost']):
        if 'price' in placeholder_lower and 'oil' in placeholder_lower:
            return f"${random.uniform(45.50, 95.75):.2f}/bbl"
        elif 'value' in placeholder_lower or 'amount' in placeholder_lower:
            return f"${random.randint(5000000, 50000000):,}"
        else:
            return f"${random.randint(100000, 5000000):,}"
    
    elif any(word in placeholder_lower for word in ['quantity', 'volume', 'capacity', 'tonnage']):
        if 'quantity' in placeholder_lower:
            return f"{random.randint(50000, 300000):,} MT"
        elif 'capacity' in placeholder_lower:
            return f"{random.randint(80000, 320000):,} DWT"
        else:
            return f"{random.randint(10000, 100000):,}"
    
    # Dates - all dates 2 weeks before today
    elif any(word in placeholder_lower for word in ['date', 'time', 'eta', 'etd']):
        from datetime import timedelta
        date_result = (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d')
        print(f"DEBUG: Processing date placeholder: {placeholder} -> {date_result}")
        return date_result
    
    # Reference numbers
    elif any(word in placeholder_lower for word in ['ref', 'number', 'id', 'code']):
        prefixes = ['REF', 'PO', 'SO', 'INV', 'LC', 'BL', 'COA', 'SGS']
        prefix = random.choice(prefixes)
        number = random.randint(100000, 999999)
        return f"{prefix}-{number}"
    
    # Default fallback - handle special cases
    else:
        # Check if it's an email-related placeholder that didn't match above
        if any(word in placeholder_lower for word in ['email', 'mail', 'e-mail', 'e_mail', 'contact']):
            buyer = random.choice(real_buyers)
            return buyer["email"]
        # Check if it's a date-related placeholder that didn't match above
        elif 'date' in placeholder_lower or 'time' in placeholder_lower:
            from datetime import timedelta
            return (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d')
        else:
            return f"Sample {placeholder.replace('_', ' ').title()}"

# Keep the old function name for backward compatibility
def generate_random_data(placeholder: str) -> str:
    """Backward compatibility wrapper"""
    return generate_realistic_random_data(placeholder)

@app.get("/")
async def root():
    return {"message": "Document Processing API is running!"}

@app.get("/health")
async def health_check():
    """Health check endpoint with detailed status information"""
    template_files = [f for f in os.listdir(TEMPLATES_DIR) if f.endswith('.docx')]
    
    return {
        "status": "healthy",
        "database": "connected" if supabase else "disconnected",
        "supabase_url": SUPABASE_URL,
        "templates_count": len(template_files),
        "templates": template_files,
        "temp_dir_exists": os.path.exists(TEMP_DIR),
        "templates_dir_exists": os.path.exists(TEMPLATES_DIR),
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    }

@app.get("/templates")
async def get_templates():
    """Get list of available templates"""
    try:
        templates = []
        for filename in os.listdir(TEMPLATES_DIR):
            if filename.lower().endswith('.docx'):
                file_path = os.path.join(TEMPLATES_DIR, filename)
                file_size = os.path.getsize(file_path)
                
                # Extract placeholders
                doc = Document(file_path)
                full_text = ""
                for paragraph in doc.paragraphs:
                    full_text += paragraph.text + "\n"
                
                placeholders = find_placeholders(full_text)
                
                template = {
                    "id": str(uuid.uuid4()),
                    "name": filename.replace('.docx', ''),
                    "description": f"Template: {filename}",
                    "file_name": filename,
                    "file_size": file_size,
                    "placeholders": placeholders,
                    "is_active": True,
                    "created_at": datetime.now().isoformat()
                }
                templates.append(template)
        
        return {"success": True, "templates": templates, "count": len(templates)}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch templates: {str(e)}")

@app.get("/vessels")
async def get_vessels():
    """Get list of vessels"""
    try:
        response = supabase.table('vessels').select('id, name, imo, vessel_type, flag').limit(50).execute()
        return {"success": True, "vessels": response.data, "count": len(response.data)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch vessels: {str(e)}")

@app.get("/vessel/{imo}")
async def get_vessel(imo: str):
    """Get vessel by IMO"""
    vessel = get_vessel_data(imo)
    if not vessel:
        raise HTTPException(status_code=404, detail=f"Vessel with IMO {imo} not found")
    return {"success": True, "vessel": vessel}

@app.post("/process-document")
async def process_document(request: Request):
    """Process a document template with vessel data"""
    try:
        # Parse JSON request
        body = await request.json()
        template_name = body.get('template_name')
        vessel_imo = body.get('vessel_imo')
        
        if not template_name or not vessel_imo:
            raise HTTPException(status_code=422, detail="template_name and vessel_imo are required")
        
        print(f"Processing document: {template_name}")
        print(f"Vessel IMO: {vessel_imo}")
        
        # Find template file - try with .docx extension if not found
        template_path = os.path.join(TEMPLATES_DIR, template_name)
        if not os.path.exists(template_path):
            # Try with .docx extension
            template_path = os.path.join(TEMPLATES_DIR, f"{template_name}.docx")
            if not os.path.exists(template_path):
                raise HTTPException(status_code=404, detail=f"Template file not found: {template_name}")
        
        # Get vessel data
        vessel = get_vessel_data(vessel_imo)
        if not vessel:
            raise HTTPException(status_code=404, detail=f"Vessel with IMO {vessel_imo} not found")
        
        # Extract placeholders from template
        doc = Document(template_path)
        full_text = ""
        for paragraph in doc.paragraphs:
            full_text += paragraph.text + "\n"

        # Also check tables - THIS WAS MISSING!
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        full_text += paragraph.text + "\n"

        print(f"DEBUG: Template {template_name} - USING ENHANCED REALISTIC DATA WITH REAL EMAILS & PHONES")
        print(f"DEBUG: Full text length: {len(full_text)}")
        print(f"DEBUG: First 500 characters: {full_text[:500]}")
        
        placeholders = find_placeholders(full_text)
        print(f"DEBUG: Found {len(placeholders)} placeholders: {placeholders}")
        
        # Create comprehensive data mapping
        data_mapping = {}
        
        # COMPREHENSIVE MAPPING FOR ALL YOUR TEMPLATE PLACEHOLDERS
        vessel_mapping = {
            # === VESSEL BASIC INFO ===
            'vessel_name': vessel.get('name', ''),
            'name': vessel.get('name', ''),
            'imo': vessel.get('imo', ''),
            'imo_number': vessel.get('imo', ''),
            'vessel_type': vessel.get('vessel_type', ''),
            'type': vessel.get('vessel_type', ''),
            'flag': vessel.get('flag', ''),
            'flag_state': vessel.get('flag', ''),
            'mmsi': vessel.get('mmsi', ''),
            'callsign': vessel.get('callsign', ''),
            'call_sign': vessel.get('callsign', ''),
            'built': str(vessel.get('built', '')),
            'year_built': str(vessel.get('built', '')),
            'deadweight': str(vessel.get('deadweight', '')),
            'cargo_capacity': str(vessel.get('cargo_capacity', '')),
            'length': str(vessel.get('length', '')),
            'length_overall': str(vessel.get('length', '')),
            'width': str(vessel.get('width', '')),
            'beam': str(vessel.get('beam', '')),
            'draught': str(vessel.get('draught', '')),
            'draft': str(vessel.get('draught', '')),
            'gross_tonnage': str(vessel.get('gross_tonnage', '')),
            'net_tonnage': str(int(float(vessel.get('gross_tonnage', 0)) * 0.7) if vessel.get('gross_tonnage') else ''),
            'engine_power': str(vessel.get('engine_power', '')),
            'engine_type': 'Diesel Engine',
            'crew_size': str(vessel.get('crew_size', '')),
            'speed': str(vessel.get('speed', '')),
            'course': str(vessel.get('course', '')),
            'status': vessel.get('status', ''),
            'current_region': vessel.get('current_region', ''),
            'region': vessel.get('current_region', ''),
            
            # === COMMERCIAL PARTIES ===
            'owner_name': vessel.get('owner_name', ''),
            'owner': vessel.get('owner_name', ''),
            'vessel_owner': vessel.get('owner_name', ''),
            'operator_name': vessel.get('operator_name', ''),
            'operator': vessel.get('operator_name', ''),
            'vessel_operator': vessel.get('operator_name', ''),
            'buyer_name': generate_realistic_random_data('buyer_name', vessel_imo),
            'buyer': generate_realistic_random_data('buyer_name', vessel_imo),
            'seller_name': generate_realistic_random_data('seller_name', vessel_imo),
            'seller': generate_realistic_random_data('seller_name', vessel_imo),
            'company_name': vessel.get('owner_name', ''),
            
            # === CARGO INFORMATION ===
            'cargo_type': vessel.get('cargo_type', ''),
            'cargo': vessel.get('cargo_type', ''),
            'cargo_quantity': str(vessel.get('cargo_quantity', '')),
            'quantity': str(vessel.get('cargo_quantity', '')),
            'oil_type': vessel.get('oil_type', ''),
            'oil_source': vessel.get('oil_source', ''),
            'commodity': vessel.get('cargo_type', ''),
            'product_name': vessel.get('cargo_type', ''),
            'product_description': (vessel.get('cargo_type', '') or 'Crude Oil') + ' - ' + (vessel.get('oil_type', '') or 'Brent Quality'),
            
            # === PORTS AND NAVIGATION ===
            'departure_port': vessel.get('departure_port_name', ''),
            'departure_port_name': vessel.get('departure_port_name', ''),
            'destination_port': vessel.get('destination_port_name', ''),
            'destination_port_name': vessel.get('destination_port_name', ''),
            'loading_port': vessel.get('loading_port_name', ''),
            'loading_port_name': vessel.get('loading_port_name', ''),
            'port_loading': vessel.get('loading_port_name', ''),
            'port_discharge': vessel.get('destination_port_name', ''),
            'departure_date': vessel.get('departure_date', ''),
            'arrival_date': vessel.get('arrival_date', ''),
            'eta': vessel.get('eta', ''),
            'registry_port': vessel.get('flag', ''),
            
            # === FINANCIAL ===
            'deal_value': str(vessel.get('deal_value', '')),
            'price': str(vessel.get('price', '')),
            'market_price': str(vessel.get('market_price', '')),
            'total_quantity': str(vessel.get('cargo_quantity', '')),
            'contract_quantity': str(vessel.get('cargo_quantity', '')),
            'contract_value': str(vessel.get('deal_value', '')),
            'total_amount': str(vessel.get('deal_value', '')),
            'total_amount_due': str(vessel.get('deal_value', '')),
            'unit_price': str(vessel.get('price', '')),
            'unit_price2': str(vessel.get('price', '')),
            'unit_price3': str(vessel.get('price', '')),
            'amount2': str(int(float(vessel.get('deal_value', 0)) * 0.3) if vessel.get('deal_value') else ''),
            'amount3': str(int(float(vessel.get('deal_value', 0)) * 0.2) if vessel.get('deal_value') else ''),
            'amount_in_words': 'As per contract',
            
            # === TECHNICAL SPECIFICATIONS ===
            'cargo_tanks': '12',
            'pumping_capacity': '5000',
            'class_society': 'Lloyd\'s Register',
            'ism_manager': vessel.get('operator_name', ''),
            
            # === DATES AND REFERENCES ===
            'date': (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d'),
            'issued_date': (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d'),
            'issue_date': (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d'),
            'date_of_issue': (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d'),
            'issued_date': (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d'),
            'validity': '30 days',
            'valid_until': (datetime.now().replace(day=datetime.now().day + 30) if datetime.now().day <= 1 else datetime.now().replace(month=datetime.now().month + 1, day=1)).strftime('%Y-%m-%d'),
            'contract_duration': '12 months',
            'pop_reference': f"POP-{vessel.get('imo', '') or 'UNKNOWN'}-{datetime.now().strftime('%Y%m%d')}",
            'document_number': f"DOC-{vessel.get('imo', '') or 'UNKNOWN'}-{datetime.now().strftime('%Y%m%d')}",
            'commercial_invoice_no': f"INV-{vessel.get('imo', '') or 'UNKNOWN'}-{datetime.now().strftime('%Y%m%d')}",
            'proforma_invoice_no': f"PRO-{vessel.get('imo', '') or 'UNKNOWN'}-{datetime.now().strftime('%Y%m%d')}",
            'invoice_no': f"INV-{vessel.get('imo', '') or 'UNKNOWN'}-{datetime.now().strftime('%Y%m%d')}",
            
            # === BUYER INFORMATION ===
            'principal_buyer_name': generate_realistic_random_data('buyer_name', vessel_imo),
            'buyer_logistics_name': generate_realistic_random_data('buyer_name', vessel_imo),
            'principal_buyer_designation': 'Procurement Manager',
            'buyer_logistics_designation': 'Logistics Coordinator',
            'principal_buyer_company': generate_realistic_random_data('buyer_company', vessel_imo),
            'buyer_logistics_company': generate_realistic_random_data('buyer_company', vessel_imo),
            'buyer_company_name': generate_realistic_random_data('buyer_company', vessel_imo),
            'buyer_company_name2': generate_realistic_random_data('buyer_company', vessel_imo),
            'authorized_person_name': generate_realistic_random_data('buyer_name', vessel_imo),
            'buyer_name': generate_realistic_random_data('buyer_name', vessel_imo),
            'buyer_company': generate_realistic_random_data('buyer_company', vessel_imo),
            'buyer_address': generate_realistic_random_data('buyer_address', vessel_imo),
            'buyer_city_country': generate_realistic_random_data('buyer_address', vessel_imo).split(',')[-2].strip() + ', ' + generate_realistic_random_data('buyer_address', vessel_imo).split(',')[-1].strip(),
            'buyer_email': generate_realistic_random_data('buyer_email', vessel_imo),
            'buyer_emails': generate_realistic_random_data('buyer_email', vessel_imo),
            'buyer_contact_email': generate_realistic_random_data('buyer_email', vessel_imo),
            'buyer_representative_email': generate_realistic_random_data('buyer_email', vessel_imo),
            'buyer_fax': generate_realistic_random_data('buyer_phone', vessel_imo),
            'buyer_mobile': generate_realistic_random_data('buyer_phone', vessel_imo),
            'buyer_office_tel': generate_realistic_random_data('buyer_phone', vessel_imo),
            'buyer_position': 'Procurement Manager',
            'buyer_registration': 'NL123456789',
            'buyer_representative': generate_realistic_random_data('buyer_name', vessel_imo),
            'buyer_signatory_name': generate_realistic_random_data('buyer_name', vessel_imo),
            'buyer_signatory_position': 'Authorized Signatory',
            'buyer_signatory_date': (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d'),
            'buyer_signature': 'Digital Signature',
            'buyer_attention': 'Procurement Department',
            'buyer_attention2': 'Logistics Department',
            'buyer_bin': 'BIN123456789',
            'buyer_bank_address': generate_realistic_random_data('buyer_bank_address', vessel_imo),
            'buyer_bank_name': generate_realistic_random_data('buyer_bank_name', vessel_imo),
            'buyer_bank_website': 'www.bank.com',
            'buyer_swift': generate_realistic_random_data('buyer_bank_swift', vessel_imo),
            'buyer_telfax': generate_realistic_random_data('buyer_phone', vessel_imo),
            'buyer_account_name': generate_realistic_random_data('buyer_name', vessel_imo),
            'buyer_account_no': 'NL91ABNA0417164300',
            'buyer_passport_no': 'P123456789',
            
            # === SELLER INFORMATION ===
            'seller_name': generate_realistic_random_data('seller_name', vessel_imo),
            'seller_designation': 'Sales Director',
            'seller_company': generate_realistic_random_data('seller_company', vessel_imo),
            'seller_signature': 'Authorized Signature',
            'seller_signatory': generate_realistic_random_data('seller_name', vessel_imo),
            'seller_title': 'Sales Director',
            'seller_address': generate_realistic_random_data('seller_address', vessel_imo),
            'seller_address2': generate_realistic_random_data('seller_address', vessel_imo),
            'seller_company_no': 'REG123456789',
            'seller_company_reg': 'Registered in Oil Country',
            'seller_emails': generate_realistic_random_data('seller_email', vessel_imo),
            'seller_passport_no': 'P987654321',
            'seller_refinery': 'Oil Refinery Complex',
            'seller_representative': generate_realistic_random_data('seller_name', vessel_imo),
            'seller_swift': generate_realistic_random_data('seller_bank_swift', vessel_imo),
            'seller_bank_address': generate_realistic_random_data('seller_bank_address', vessel_imo),
            'seller_bank_iban': 'NL91OILN0417164300',
            'seller_bank_name': generate_realistic_random_data('seller_bank_name', vessel_imo),
            'seller_beneficiary_address': generate_realistic_random_data('seller_address', vessel_imo),
            'seller_bank_account_name': generate_realistic_random_data('seller_name', vessel_imo),
            'seller_bank_account_no': 'NL91OILN0417164300',
            'seller_bank_officer_mobile': generate_realistic_random_data('seller_phone', vessel_imo),
            'seller_bank_officer_name': 'Bank Officer',
            'seller_bank_swift': generate_realistic_random_data('seller_bank_swift', vessel_imo),
            'seller_tel': generate_realistic_random_data('seller_phone', vessel_imo),
            'seller_email': generate_realistic_random_data('seller_email', vessel_imo),
            'seller_contact_email': generate_realistic_random_data('seller_email', vessel_imo),
            'seller_representative_email': generate_realistic_random_data('seller_email', vessel_imo),
            'seller_company_email': generate_realistic_random_data('seller_email', vessel_imo),
            'seller_registration': 'OIL123456789',
            
            # === PRODUCT SPECIFICATIONS ===
            'country_of_origin': 'Saudi Arabia',
            'origin': 'Saudi Arabia',
            'delivery_port': vessel.get('destination_port_name', ''),
            'final_delivery_place': vessel.get('destination_port_name', ''),
            'place_of_destination': vessel.get('destination_port_name', ''),
            'port_of_loading': vessel.get('loading_port_name', ''),
            'port_of_discharge': vessel.get('destination_port_name', ''),
            'specification': 'As per contract specifications',
            'quality': 'Premium Grade',
            'inspection': 'SGS Inspection',
            'insurance': 'All Risks Coverage',
            'shipping_terms': 'FOB',
            'terms_of_delivery': 'FOB Loading Port',
            'payment_terms': 'LC at Sight',
            'shipping_documents': 'Bill of Lading, Certificate of Origin',
            'performance_bond': '2% of contract value',
            'partial_shipment': 'Allowed',
            'transshipment': 'Not Allowed',
            'monthly_delivery': 'As per schedule',
            'total_containers': '1',
            'total_gross': str(vessel.get('cargo_quantity', '')),
            'total_weight': str(vessel.get('cargo_quantity', '')),
            'transaction_currency': 'USD',
            'shipping_charges': 'As per contract',
            'discount': '0%',
            'other_expenditures': 'As per contract',
            'via_name': 'Direct',
            'through_name': 'Direct',
            'consignment2': 'As per contract',
            'consignment33': 'As per contract',
            'item2': 'Additional Item',
            'item3': 'Additional Item',
            'quantity2': str(int(float(vessel.get('cargo_quantity', 0)) * 0.3) if vessel.get('cargo_quantity') else ''),
            'quantity3': str(int(float(vessel.get('cargo_quantity', 0)) * 0.2) if vessel.get('cargo_quantity') else ''),
            'shipment_date2': (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d'),
            'shipment_date3': (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d'),
            'goods_details': 'As per specification',
            'position_title': 'Authorized Signatory',
            'signatory_name': vessel.get('seller_name', ''),
            
            # === BANKING INFORMATION ===
            'confirming_bank_account_name': 'Confirming Bank Account',
            'confirming_bank_account_number': 'NL91CONF0417164300',
            'confirming_bank_address': 'Bank Street, Financial District',
            'confirming_bank_name': 'Confirming Bank International',
            'confirming_bank_officer': 'Bank Officer',
            'confirming_bank_officer_contact': '+31-20-111-2222',
            'confirming_bank_swift': 'CONFNL2A',
            'confirming_bank_tel': '+31-20-111-2222',
            'issuing_bank_account_name': 'Issuing Bank Account',
            'issuing_bank_account_number': 'NL91ISSU0417164300',
            'issuing_bank_address': 'Issuing Bank Street',
            'issuing_bank_name': 'Issuing Bank International',
            'issuing_bank_officer': 'Issuing Officer',
            'issuing_bank_officer_contact': '+31-20-333-4444',
            'issuing_bank_swift': 'ISSUENL2A',
            'issuing_bank_tel': '+31-20-333-4444',
            'notary_number': 'NOT123456789',
            
            # === TECHNICAL SPECIFICATIONS (OIL/PRODUCT) ===
            'api_gravity': '35.5',
            'density': '0.845',
            'specific_gravity': '0.845',
            'sulfur': '0.5%',
            'water_content': '0.1%',
            'ash_content': '0.01%',
            'carbon_residue': '0.1%',
            'flash_point': '65°C',
            'pour_point': '-15°C',
            'cloud_point': '-10°C',
            'cfpp': '-12°C',
            'cetane_number': '52',
            'octane_number': '95',
            'viscosity_40': '2.5',
            'viscosity_100': '1.2',
            'viscosity_index': '95',
            'lubricity': '460',
            'calorific_value': '42.5',
            'dist_ibp': '35°C',
            'dist_10': '65°C',
            'dist_50': '180°C',
            'dist_90': '350°C',
            'dist_fbp': '380°C',
            'dist_residue': '2%',
            'aromatics': '25%',
            'olefins': '5%',
            'oxygenates': '0%',
            'nickel': '5 ppm',
            'vanadium': '10 ppm',
            'sodium': '2 ppm',
            'nitrogen': '0.1%',
            'sediment': '0.01%',
            'smoke_point': '25mm',
            'free_fatty_acid': '0.1%',
            'iodine_value': '85',
            'slip_melting_point': '35°C',
            'moisture_impurities': '0.1%',
            'colour': 'Light Yellow',
            'cloud_point': '-10°C',
            
            # === TEST RESULTS ===
            'result_ash': '0.01%',
            'result_aspect': 'Clear',
            'result_cfpp_summer': '-8°C',
            'result_cfpp_winter': '-15°C',
            'result_cetaneindex': '52',
            'result_cetanenumber': '52',
            'result_color': 'Light Yellow',
            'result_density': '0.845',
            'result_distillation': 'As per spec',
            'result_lubricity': '460',
            'result_oxidation': 'Pass',
            'result_pah': '0.1%',
            'result_sulfur': '0.5%',
            'result_viscosity': '2.5',
            
            # === MAX/MIN SPECIFICATIONS ===
            'max_acidity': '0.1%',
            'max_aspect': 'Clear',
            'max_cfpp_summer': '-5°C',
            'max_cloud_winter': '-8°C',
            'max_color': 'Light Yellow',
            'max_density': '0.850',
            'max_distillation': 'As per spec',
            'max_pah': '0.2%',
            'max_viscosity': '3.0',
            'min_acidity': '0.05%',
            'min_ash': '0.005%',
            'min_cfpp_summer': '-10°C',
            'min_cloud_winter': '-12°C',
            'min_viscosity': '2.0',
            
            # === ADDITIONAL FIELDS ===
            'optional': 'N/A',
            'to': 'To:',
            'via': 'Via:',
            'tel': '+31-20-123-4567',
            'email': 'info@company.com',
            'address': '123 Business Street',
            'bin': 'BIN123456789',
            'okpo': 'OKPO123456789',
            'designations': 'Authorized Signatory',
            'position': 'Manager',
        }
        
        # Process each placeholder with improved matching logic
        print(f"Processing {len(placeholders)} placeholders: {placeholders}")
        for placeholder in placeholders:
            placeholder_lower = placeholder.lower().replace('_', '').replace(' ', '').replace('-', '')
            
            # Try to find exact match first
            found = False
            replacement_value = None
            
            # 1. Exact match (most precise)
            for key, value in vessel_mapping.items():
                key_lower = key.lower().replace('_', '').replace(' ', '').replace('-', '')
                
                if key_lower == placeholder_lower:
                    replacement_value = value if value else generate_realistic_random_data(placeholder, vessel_imo)
                    data_mapping[placeholder] = replacement_value
                    print(f"  {placeholder} -> {replacement_value} (exact match with {key})")
                    found = True
                    break
            
            # 2. Smart partial match (only for specific cases to avoid wrong matches)
            if not found:
                for key, value in vessel_mapping.items():
                    key_lower = key.lower().replace('_', '').replace(' ', '').replace('-', '')
                    
                    # Only allow partial matches for specific safe cases
                    if (placeholder_lower in key_lower and len(placeholder_lower) >= 4) or \
                       (key_lower in placeholder_lower and len(key_lower) >= 4):
                        # Additional safety checks to avoid wrong matches
                        if not any(conflict in placeholder_lower for conflict in ['bank', 'company', 'name', 'address']) or \
                           any(conflict in key_lower for conflict in ['bank', 'company', 'name', 'address']):
                            replacement_value = value if value else generate_realistic_random_data(placeholder, vessel_imo)
                            data_mapping[placeholder] = replacement_value
                            print(f"  {placeholder} -> {replacement_value} (smart partial match with {key})")
                            found = True
                            break
            
            # 3. If no match found, generate realistic random data
            if not found:
                replacement_value = generate_realistic_random_data(placeholder, vessel_imo)
                data_mapping[placeholder] = replacement_value
                print(f"  {placeholder} -> {replacement_value} (realistic random data)")
        
        print(f"Final data mapping: {data_mapping}")
        
        # Process the document
        processed_docx_path = replace_placeholders_in_docx(template_path, data_mapping)
        
        # Convert DOCX to PDF using LibreOffice
        try:
            pdf_path = convert_docx_to_pdf(processed_docx_path)
            
            if pdf_path.endswith('.pdf'):
                print(f"Successfully converted DOCX to PDF: {pdf_path}")
                
                # Read PDF content
                with open(pdf_path, 'rb') as f:
                    pdf_content = f.read()
                
                # Clean up temp files
                try:
                    os.remove(processed_docx_path)
                    os.remove(pdf_path)
                except:
                    pass  # Ignore cleanup errors
                
                # Return PDF file
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"processed_{vessel_imo}_{timestamp}.pdf"
                
                return Response(
                    content=pdf_content,
                    media_type="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename={filename}"}
                )
            else:
                print("PDF conversion failed, falling back to DOCX output...")
                raise Exception("PDF conversion failed")
            
        except Exception as pdf_error:
            print(f"PDF conversion failed: {pdf_error}")
            print("Falling back to DOCX output...")
            
            # Fallback: return DOCX if PDF conversion fails
            with open(processed_docx_path, 'rb') as f:
                docx_content = f.read()
            
            # Clean up temp files
            try:
                os.remove(processed_docx_path)
            except:
                pass  # Ignore cleanup errors
            
            # Return DOCX file as fallback
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"processed_{vessel_imo}_{timestamp}.docx"
            
            return Response(
                content=docx_content,
                media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                headers={"Content-Disposition": f"attachment; filename={filename}"}
            )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")

@app.post("/upload-template")
async def upload_template(
    name: str = Form(...),
    description: str = Form(...),
    template_file: UploadFile = File(...)
):
    """Upload a new template"""
    try:
        if not template_file.filename.lower().endswith('.docx'):
            raise HTTPException(status_code=400, detail="Only .docx files are allowed")
        
        # Save file
        file_path = os.path.join(TEMPLATES_DIR, template_file.filename)
        with open(file_path, 'wb') as f:
            content = await template_file.read()
            f.write(content)
        
        return {
            "success": True,
            "message": "Template uploaded successfully",
            "template": {
                "name": name,
                "description": description,
                "file_name": template_file.filename,
                "file_size": len(content)
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    
    # Simple HTTP server for VPS deployment
    port = int(os.environ.get('FASTAPI_PORT', 8000))
    host = os.environ.get('FASTAPI_HOST', '0.0.0.0')
    
    logger.info("🚀 Starting Document Processing API...")
    logger.info(f"🌐 Server running on: http://{host}:{port}")
    logger.info(f"📁 Templates directory: {os.path.join(os.getcwd(), 'templates')}")
    logger.info(f"📁 Temp directory: {os.path.join(os.getcwd(), 'temp')}")
    logger.info("🔧 Ready for VPS deployment!")
    
    uvicorn.run(app, host=host, port=port, log_level="info")
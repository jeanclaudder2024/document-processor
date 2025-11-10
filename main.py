"""
Document Processing API - Clean Rebuild
Handles Word document processing with vessel data from Supabase
"""

import os
import json
import hashlib
import uuid
import tempfile
import logging
import csv
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from fastapi import FastAPI, HTTPException, File, UploadFile, Form, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from supabase import create_client, Client
from docx import Document
import re

# ============================================================================
# CONFIGURATION
# ============================================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Document Processing API", version="2.0.0")

# Load environment variables
try:
    load_dotenv()
except Exception as e:
    logger.warning(f"Could not load .env file: {e}")

# CORS middleware
ALLOWED_ORIGINS = [
    "http://127.0.0.1:8080",
    "http://localhost:8080",
    "http://127.0.0.1:8081",
    "http://localhost:8081",
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "http://127.0.0.1:5500",
    "http://localhost:5500",
    "http://127.0.0.1:3000",
    "http://localhost:3000",
    # Allow network IP addresses for development
    "http://10.193.191.72:5173",
    "http://10.193.191.72:8081",
    "http://10.193.191.72:3000",
    # Allow any local network IP (for development flexibility)
    "http://0.0.0.0:5173",
    "http://0.0.0.0:8081",
    "http://0.0.0.0:3000",
    "http://10.237.133.72:5173",
    "http://10.237.133.72:8080",
    "http://10.237.133.72:8081",
    "http://10.237.133.72:3000",
    "https://petrodealhub.com",
    "https://www.petrodealhub.com",
    "https://control.petrodealhub.com",
]

ALLOWED_ORIGIN_REGEX = r"http://(localhost|127\\.0\\.0\\.1|0\\.0\\.0\\.0|10\\.\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}|192\\.168\\.\\d{1,3}\\.\\d{1,3}|172\\.(1[6-9]|2[0-9]|3[0-1])\\.\\d{1,3}\\.\\d{1,3}):\\d+"

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH", "HEAD"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=600,
)

# Directories
BASE_DIR = os.getcwd()
TEMPLATES_DIR = os.path.join(BASE_DIR, 'templates')
TEMP_DIR = os.path.join(BASE_DIR, 'temp')
DATA_DIR = os.path.join(BASE_DIR, 'data')
STORAGE_DIR = os.path.join(BASE_DIR, 'storage')
CMS_DIR = os.path.join(BASE_DIR, 'cms')

os.makedirs(TEMPLATES_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(STORAGE_DIR, exist_ok=True)
if os.path.isdir(CMS_DIR):
    app.mount("/cms", StaticFiles(directory=CMS_DIR, html=True), name="cms")

# Storage paths
PLACEHOLDER_SETTINGS_PATH = os.path.join(STORAGE_DIR, 'placeholder_settings.json')
PLANS_PATH = os.path.join(STORAGE_DIR, 'plans.json')
USERS_PATH = os.path.join(STORAGE_DIR, 'users.json')

# Supabase client
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://ozjhdxvwqbzcvcywhwjg.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im96amhkeHZ3cWJ6Y3ZjeXdod2pnIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTU5MDAyNzUsImV4cCI6MjA3MTQ3NjI3NX0.KLAo1KIRR9ofapXPHenoi-ega0PJtkNhGnDHGtniA-Q")

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    logger.info("Successfully connected to Supabase")
except Exception as e:
    logger.error(f"Failed to connect to Supabase: {e}")
    supabase = None

SUPABASE_ENABLED = supabase is not None

def encode_bytea(data: bytes) -> str:
    """Encode raw bytes into Postgres bytea hex format"""
    if data is None:
        return None
    return "\\x" + data.hex()

def decode_bytea(value) -> Optional[bytes]:
    """Decode Postgres bytea (hex) or raw bytes to bytes"""
    if value is None:
        return None
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        if value.startswith('\\x'):
            return bytes.fromhex(value[2:])
        return value.encode('utf-8')
    # Fallback: try to convert via bytes constructor
    try:
        return bytes(value)
    except Exception:
        return None

def resolve_template_record(template_name: str) -> Optional[Dict]:
    """Find a template row in Supabase by various name permutations"""
    if not SUPABASE_ENABLED:
        return None

    # Allow direct lookup by UUID string
    try:
        template_uuid = uuid.UUID(str(template_name))
    except (ValueError, TypeError):
        template_uuid = None

    if template_uuid:
        try:
            response = supabase.table('document_templates') \
                .select('id, title, description, file_name, placeholders, is_active, created_at, updated_at') \
                .eq('id', str(template_uuid)) \
                .limit(1) \
                .execute()
            if response.data:
                return response.data[0]
        except Exception as exc:
            logger.error(f"Failed to resolve template by ID '{template_name}': {exc}")

    name_with_ext = template_name if template_name.endswith('.docx') else f"{template_name}.docx"
    name_without_ext = template_name[:-5] if template_name.endswith('.docx') else template_name

    candidates = list({name_with_ext, name_without_ext})

    try:
        response = supabase.table('document_templates') \
            .select('id, title, description, file_name, placeholders, is_active, created_at, updated_at') \
            .in_('file_name', candidates) \
            .limit(1) \
            .execute()
        if response.data:
            return response.data[0]

        response = supabase.table('document_templates') \
            .select('id, title, description, file_name, placeholders, is_active, created_at, updated_at') \
            .in_('title', [name_without_ext, name_with_ext]) \
            .limit(1) \
            .execute()
        if response.data:
            return response.data[0]
    except Exception as exc:
        logger.error(f"Failed to resolve template '{template_name}': {exc}")

    return None

def fetch_template_placeholders(template_id: str) -> Dict[str, Dict[str, Optional[str]]]:
    """Fetch placeholder configuration for a template"""
    if not SUPABASE_ENABLED:
        return {}

    try:
        response = supabase.table('template_placeholders').select(
            'placeholder, source, custom_value, database_field, csv_id, csv_field, csv_row, random_option'
        ).eq('template_id', template_id).execute()
        settings: Dict[str, Dict[str, Optional[str]]] = {}
        for row in response.data or []:
            settings[row['placeholder']] = {
                'source': row.get('source', 'random'),
                'customValue': row.get('custom_value') or '',
                'databaseField': row.get('database_field') or '',
                'csvId': row.get('csv_id') or '',
                'csvField': row.get('csv_field') or '',
                'csvRow': row['csv_row'] if row.get('csv_row') is not None else 0,
                'randomOption': row.get('random_option', 'auto') or 'auto'
            }
        return settings
    except Exception as exc:
        logger.error(f"Failed to fetch template placeholders for {template_id}: {exc}")
        return {}

def upsert_template_placeholders(template_id: str, settings: Dict[str, Dict]) -> None:
    """Upsert placeholder settings into Supabase"""
    if not SUPABASE_ENABLED or not settings:
        return

    rows = []
    for placeholder, cfg in settings.items():
        rows.append({
            'template_id': template_id,
            'placeholder': placeholder,
            'source': cfg.get('source', 'random'),
            'custom_value': cfg.get('customValue'),
            'database_field': cfg.get('databaseField'),
            'csv_id': cfg.get('csvId'),
            'csv_field': cfg.get('csvField'),
            'csv_row': cfg.get('csvRow'),
            'random_option': cfg.get('randomOption', 'auto')
        })

    try:
        supabase.table('template_placeholders').upsert(rows, on_conflict='template_id,placeholder').execute()
    except Exception as exc:
        logger.error(f"Failed to upsert placeholder settings: {exc}")

def fetch_template_file_record(template_id: str, include_data: bool = False) -> Optional[Dict]:
    """Get the latest template file record from Supabase"""
    if not SUPABASE_ENABLED:
        return None
    try:
        select_fields = 'filename, mime_type, file_size, sha256, uploaded_at'
        if include_data:
            select_fields += ', file_data'

        response = supabase.table('template_files') \
            .select(select_fields) \
            .eq('template_id', template_id) \
            .order('uploaded_at', desc=True) \
            .limit(1) \
            .execute()
        if response.data:
            return response.data[0]
    except Exception as exc:
        logger.error(f"Failed to fetch template file for {template_id}: {exc}")
        return None

def write_temp_docx_from_record(file_record: Dict) -> str:
    """Persist a template file from Supabase to a temporary DOCX path"""
    doc_bytes = decode_bytea(file_record.get('file_data'))
    if not doc_bytes:
        raise HTTPException(status_code=500, detail="Template file data is empty")

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.docx')
    tmp.write(doc_bytes)
    tmp.flush()
    tmp.close()
    return tmp.name

# ============================================================================
# STEP 1: STORAGE HELPERS (JSON on disk with atomic writes)
# ============================================================================

def read_json_file(path: str, default=None):
    """Read JSON file with default fallback"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Error reading {path}: {e}")
        return default if default is not None else {}

def write_json_atomic(path: str, data) -> None:
    """Write JSON file atomically (write to temp, then rename)"""
    tmp_path = path + ".tmp"
    try:
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except Exception as e:
        logger.error(f"Error writing {path}: {e}")
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise

def ensure_storage():
    """Initialize storage files with defaults"""
    if not os.path.exists(PLANS_PATH):
        write_json_atomic(PLANS_PATH, {
            "basic": {
                "name": "Basic Plan",
                "can_view_all": True,
                "can_download": ["ANALYSIS SGS.docx", "ICPO TEMPLATE.docx"],
                "max_downloads_per_month": 10,
                "features": ["View all documents", "Download selected templates"]
            },
            "premium": {
                "name": "Premium Plan",
                "can_view_all": True,
                "can_download": ["ANALYSIS SGS.docx", "ICPO TEMPLATE.docx", "Commercial_Invoice_Batys_Final.docx", "PERFORMA INVOICE.docx"],
                "max_downloads_per_month": 100,
                "features": ["All downloads", "Priority generation"]
            },
            "enterprise": {
                "name": "Enterprise Plan",
                "can_view_all": True,
                "can_download": ["*"],
                "max_downloads_per_month": -1,
                "features": ["Unlimited", "SLA"]
            }
        })
    
    if not os.path.exists(USERS_PATH):
        pwd_hash = hashlib.sha256("admin123".encode()).hexdigest()
        write_json_atomic(USERS_PATH, {
            "users": [{"username": "admin", "password_hash": pwd_hash}],
            "sessions": {}
        })

# Initialize storage on startup
ensure_storage()

# ============================================================================
# STEP 2: AUTHENTICATION (Simple login with HttpOnly cookies)
# ============================================================================

def get_current_user(request: Request):
    """Dependency to check if user is authenticated"""
    token = request.cookies.get('session')
    if not token:
        logger.warning(f"Auth failed: No session cookie. Available cookies: {list(request.cookies.keys())}")
        raise HTTPException(status_code=401, detail="Not authenticated - Please login")
    
    users_data = read_json_file(USERS_PATH, {"users": [], "sessions": {}})
    username = users_data.get("sessions", {}).get(token)
    if not username:
        logger.warning(f"Auth failed: Invalid token {token[:10]}... Sessions: {len(users_data.get('sessions', {}))}")
        raise HTTPException(status_code=401, detail="Invalid session - Please login again")
    
    logger.info(f"Authenticated user: {username}")
    return username

@app.post("/auth/login")
async def auth_login(request: Request):
    """Login endpoint - sets HttpOnly session cookie"""
    try:
        data = await request.json()
        username = data.get('username')
        password = data.get('password', '')
        
        users_data = read_json_file(USERS_PATH, {"users": [], "sessions": {}})
        pwd_hash = hashlib.sha256(password.encode()).hexdigest()
        
        user_found = any(
            u.get('username') == username and u.get('password_hash') == pwd_hash
            for u in users_data.get('users', [])
        )
        
        if not user_found:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        # Create session token
        token = uuid.uuid4().hex
        users_data['sessions'][token] = username
        write_json_atomic(USERS_PATH, users_data)
        
        # Set HttpOnly cookie with SameSite=None and Secure for cross-origin, or Lax for same-site
        response = Response(content=json.dumps({"success": True, "user": username}), media_type="application/json")
        # Use SameSite='None' and Secure=True if running on different ports, but check origin first
        origin = request.headers.get('origin', '')
        if origin and origin.startswith('http://127.0.0.1') or origin.startswith('http://localhost'):
            # Same-site cookies work with Lax for same-origin requests
            response.set_cookie(key='session', value=token, httponly=True, samesite='Lax', max_age=86400)
        else:
            # For true cross-origin, use None with Secure (requires HTTPS)
            response.set_cookie(key='session', value=token, httponly=True, samesite='Lax', max_age=86400)
        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")

@app.post("/auth/logout")
async def auth_logout(request: Request):
    """Logout endpoint - removes session"""
    try:
        token = request.cookies.get('session')
        if token:
            users_data = read_json_file(USERS_PATH, {"users": [], "sessions": {}})
            users_data.get("sessions", {}).pop(token, None)
            write_json_atomic(USERS_PATH, users_data)
        
        response = Response(content=json.dumps({"success": True}), media_type="application/json")
        response.delete_cookie('session')
        return response
    except Exception as e:
        logger.error(f"Logout error: {e}")
        raise HTTPException(status_code=500, detail=f"Logout failed: {str(e)}")

@app.get("/auth/me")
async def auth_me(request: Request):
    """Get current user info"""
    token = request.cookies.get('session')
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    users_data = read_json_file(USERS_PATH, {"users": [], "sessions": {}})
    username = users_data.get("sessions", {}).get(token)
    if not username:
        raise HTTPException(status_code=401, detail="Invalid session")
    
    return {"success": True, "user": username}

# ============================================================================
# BASIC HEALTH & ROOT ENDPOINTS
# ============================================================================

@app.get("/")
async def root():
    return {"message": "Document Processing API v2.0", "status": "running"}

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "supabase": "connected" if supabase else "disconnected",
        "templates_dir": TEMPLATES_DIR,
        "storage_dir": STORAGE_DIR
    }

# ============================================================================
# VESSELS API (from Supabase)
# ============================================================================

@app.get("/vessels")
async def get_vessels():
    """Get list of vessels from Supabase"""
    try:
        if not supabase:
            # Return mock data if Supabase not available
            return {
                "success": True,
                "vessels": [
                    {"id": 1, "imo": "IMO1234567", "name": "Test Vessel 1", "vessel_type": "Tanker", "flag": "Panama"},
                    {"id": 2, "imo": "IMO9876543", "name": "Test Vessel 2", "vessel_type": "Cargo", "flag": "Singapore"}
                ],
                "count": 2
            }
        
        response = supabase.table('vessels').select('id, name, imo, vessel_type, flag').limit(50).execute()
        return {
            "success": True,
            "vessels": response.data or [],
            "count": len(response.data) if response.data else 0
        }
    except Exception as e:
        logger.error(f"Error fetching vessels: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch vessels: {str(e)}")

@app.get("/vessel/{imo}")
async def get_vessel(imo: str):
    """Get vessel by IMO"""
    try:
        if not supabase:
            raise HTTPException(status_code=503, detail="Supabase not available")
        
        response = supabase.table('vessels').select('*').eq('imo', imo).execute()
        if not response.data or len(response.data) == 0:
            raise HTTPException(status_code=404, detail=f"Vessel with IMO {imo} not found")
        
        return {"success": True, "vessel": response.data[0]}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching vessel {imo}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/vessel-fields")
async def get_vessel_fields():
    """Get list of all available fields in vessels table"""
    try:
        # Common vessel fields that might be used in documents
        # This is a comprehensive list based on the database schema
        fields = [
            {'name': 'name', 'label': 'Vessel Name'},
            {'name': 'imo', 'label': 'IMO Number'},
            {'name': 'mmsi', 'label': 'MMSI'},
            {'name': 'vessel_type', 'label': 'Vessel Type'},
            {'name': 'flag', 'label': 'Flag'},
            {'name': 'built', 'label': 'Year Built'},
            {'name': 'deadweight', 'label': 'Deadweight'},
            {'name': 'cargo_capacity', 'label': 'Cargo Capacity'},
            {'name': 'length', 'label': 'Length'},
            {'name': 'width', 'label': 'Width'},
            {'name': 'beam', 'label': 'Beam'},
            {'name': 'draft', 'label': 'Draft'},
            {'name': 'draught', 'label': 'Draught'},
            {'name': 'gross_tonnage', 'label': 'Gross Tonnage'},
            {'name': 'engine_power', 'label': 'Engine Power'},
            {'name': 'fuel_consumption', 'label': 'Fuel Consumption'},
            {'name': 'crew_size', 'label': 'Crew Size'},
            {'name': 'speed', 'label': 'Speed'},
            {'name': 'callsign', 'label': 'Call Sign'},
            {'name': 'nav_status', 'label': 'Navigation Status'},
            {'name': 'current_lat', 'label': 'Current Latitude'},
            {'name': 'current_lng', 'label': 'Current Longitude'},
            {'name': 'current_region', 'label': 'Current Region'},
            {'name': 'currentport', 'label': 'Current Port'},
            {'name': 'departure_port', 'label': 'Departure Port'},
            {'name': 'destination_port', 'label': 'Destination Port'},
            {'name': 'loading_port', 'label': 'Loading Port'},
            {'name': 'departure_date', 'label': 'Departure Date'},
            {'name': 'arrival_date', 'label': 'Arrival Date'},
            {'name': 'eta', 'label': 'ETA'},
            {'name': 'cargo_type', 'label': 'Cargo Type'},
            {'name': 'cargo_quantity', 'label': 'Cargo Quantity'},
            {'name': 'oil_type', 'label': 'Oil Type'},
            {'name': 'oil_source', 'label': 'Oil Source'},
            {'name': 'quantity', 'label': 'Quantity'},
            {'name': 'price', 'label': 'Price'},
            {'name': 'market_price', 'label': 'Market Price'},
            {'name': 'deal_value', 'label': 'Deal Value'},
            {'name': 'owner_name', 'label': 'Owner Name'},
            {'name': 'operator_name', 'label': 'Operator Name'},
            {'name': 'buyer_name', 'label': 'Buyer Name'},
            {'name': 'seller_name', 'label': 'Seller Name'},
            {'name': 'source_company', 'label': 'Source Company'},
            {'name': 'target_refinery', 'label': 'Target Refinery'},
            {'name': 'shipping_type', 'label': 'Shipping Type'},
            {'name': 'route_distance', 'label': 'Route Distance'},
            {'name': 'route_info', 'label': 'Route Info'},
        ]
        
        return {"success": True, "fields": fields}
    except Exception as e:
        logger.error(f"Error getting vessel fields: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# STEP 3: PLACEHOLDER EXTRACTION (from DOCX files)
# ============================================================================

def find_placeholders(text: str) -> List[str]:
    """Extract placeholders from text using multiple formats"""
    patterns = [
        r'\{\{([^}]+)\}\}',      # {{placeholder}}
        r'\{([^}]+)\}',          # {placeholder}
        r'\[\[([^\]]+)\]\]',     # [[placeholder]]
        r'\[([^\]]+)\]',         # [placeholder]
        r'%([^%]+)%',            # %placeholder%
        r'<([^>]+)>',            # <placeholder>
        r'__([^_]+)__',          # __placeholder__
        r'##([^#]+)##',          # ##placeholder##
    ]
    
    placeholders = set()
    for pattern in patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            # Clean up match - replace newlines with spaces, remove extra whitespace
            cleaned = match.strip().replace('\n', ' ').replace('\r', ' ')
            cleaned = ' '.join(cleaned.split())  # Remove extra spaces
            if cleaned:
                placeholders.add(cleaned)
    
    return sorted(list(placeholders))

def extract_placeholders_from_docx(file_path: str) -> List[str]:
    """Extract all placeholders from a DOCX file"""
    try:
        doc = Document(file_path)
        all_placeholders = set()
        
        # Extract from paragraphs
        for paragraph in doc.paragraphs:
            placeholders = find_placeholders(paragraph.text)
            all_placeholders.update(placeholders)
        
        # Extract from tables
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        placeholders = find_placeholders(paragraph.text)
                        all_placeholders.update(placeholders)
        
        return sorted(list(all_placeholders))
    except Exception as e:
        logger.error(f"Error extracting placeholders from {file_path}: {e}")
        return []

# ============================================================================
# STEP 4: TEMPLATES API (upload, list, get, delete)
# ============================================================================

def _cors_preflight_headers(request: Request, allowed_methods: str) -> Dict[str, str]:
    origin = request.headers.get("origin", "")
    headers: Dict[str, str] = {
        "Access-Control-Allow-Methods": allowed_methods,
        "Access-Control-Allow-Headers": request.headers.get("access-control-request-headers", "*"),
        "Access-Control-Allow-Credentials": "true",
        "Access-Control-Max-Age": "600",
        "Vary": "Origin",
    }
    if origin:
        headers["Access-Control-Allow-Origin"] = origin
    elif ALLOWED_ORIGINS:
        headers["Access-Control-Allow-Origin"] = ALLOWED_ORIGINS[0]
    else:
        headers["Access-Control-Allow-Origin"] = "*"
    return headers


@app.options("/templates")
async def options_templates(request: Request):
    """Handle CORS preflight for templates endpoint"""
    return Response(status_code=200, headers=_cors_preflight_headers(request, "GET, POST, OPTIONS"))

@app.get("/templates")
async def get_templates():
    """List all available templates with placeholders"""
    try:
        templates = []

        if SUPABASE_ENABLED:
            try:
                db_templates = supabase.table('document_templates').select(
                    'id, title, description, file_name, placeholders, is_active, created_at'
                ).eq('is_active', True).execute()

                for record in db_templates.data or []:
                    template_id = record.get('id')
                    placeholders = record.get('placeholders') or []

                    file_meta = fetch_template_file_record(template_id)
                    size = file_meta.get('file_size') if file_meta else 0
                    created_at = (file_meta or {}).get('uploaded_at') or record.get('created_at')

                    # Normalise names for the frontend
                    file_name = record.get('file_name') or (record.get('title') or 'template')
                    if not file_name.endswith('.docx'):
                        file_name = f"{file_name}.docx"

                    display_name = record.get('title') or file_name.replace('.docx', '')

                    templates.append({
                        "id": str(template_id),
                        "name": file_name,
                        "title": display_name,
                        "file_name": file_name.replace('.docx', ''),
                        "file_with_extension": file_name,
                        "description": record.get('description') or '',
                        "size": size or 0,
                        "created_at": created_at,
                        "placeholders": placeholders,
                        "placeholder_count": len(placeholders),
                        "is_active": record.get('is_active', True)
                    })
            except Exception as exc:
                logger.error(f"Failed to load templates from Supabase: {exc}")

        if not templates and not SUPABASE_ENABLED:
            # Fallback to legacy file-system templates if Supabase is unavailable
            for filename in os.listdir(TEMPLATES_DIR):
                if filename.endswith('.docx'):
                    file_path = os.path.join(TEMPLATES_DIR, filename)
                    file_size = os.path.getsize(file_path)
                    created_at = datetime.fromtimestamp(os.path.getctime(file_path)).isoformat()
                    placeholders = extract_placeholders_from_docx(file_path)

                    template_id = hashlib.md5(filename.encode()).hexdigest()[:12]

                    templates.append({
                        "id": template_id,
                        "name": filename,
                        "title": filename.replace('.docx', ''),
                        "file_name": filename.replace('.docx', ''),
                        "file_with_extension": filename,
                        "description": f"Template: {filename.replace('.docx', '')}",
                        "size": file_size,
                        "created_at": created_at,
                        "placeholders": placeholders,
                        "placeholder_count": len(placeholders),
                        "is_active": True
                    })

        return {"templates": templates}
    except Exception as e:
        logger.error(f"Error listing templates: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/plans-db")
async def get_plans_db():
    """Get all plans from database with template permissions"""
    try:
        if not supabase:
            # Fallback to JSON
            plans = read_json_file(PLANS_PATH, {})
            return {"success": True, "plans": plans, "source": "json"}
        
        try:
            # Get plans from database
            plans_res = supabase.table('subscription_plans').select('*').eq('is_active', True).order('sort_order').execute()
            
            if not plans_res.data:
                # Fallback to JSON if no database plans
                plans = read_json_file(PLANS_PATH, {})
                return {"success": True, "plans": plans, "source": "json_fallback"}
            
            # Get all templates (may not exist yet, so handle gracefully)
            template_map = {}
            try:
                templates_res = supabase.table('document_templates').select('id, file_name, title').eq('is_active', True).execute()
                template_map = {t['id']: t for t in (templates_res.data or [])}
            except Exception as e:
                logger.warning(f"Could not fetch templates from database: {e}")
            
            # Get permissions for each plan
            plans_dict = {}
            for plan in plans_res.data:
                plan_tier = plan['plan_tier']
                
                # Get permissions for this plan (may not exist yet)
                allowed_templates = []
                try:
                    permissions_res = supabase.table('plan_template_permissions').select('template_id, can_download').eq('plan_id', plan['id']).execute()
                    
                    if permissions_res.data:
                        for perm in permissions_res.data:
                            if perm['can_download']:
                                template_id = perm['template_id']
                                template_info = template_map.get(template_id)
                                if template_info:
                                    allowed_templates.append(template_info.get('file_name', ''))
                except Exception as e:
                    logger.warning(f"Could not fetch permissions for plan {plan_tier}: {e}")
                    # Default to all templates if permissions table doesn't exist
                    allowed_templates = ['*']
                
                # If no permissions set, default to all templates
                if not allowed_templates:
                    allowed_templates = ['*']
                
                # Normalize template names (remove .docx if present)
                normalized_templates = []
                if allowed_templates:
                    for t in allowed_templates:
                        if isinstance(t, str):
                            normalized_templates.append(t.replace('.docx', '').strip())
                        else:
                            normalized_templates.append(str(t))
                
                plans_dict[plan_tier] = {
                    "id": str(plan['id']),
                    "name": plan['plan_name'],
                    "plan_tier": plan_tier,
                    "description": plan.get('description', ''),
                    "monthly_price": float(plan.get('monthly_price', 0)),
                    "annual_price": float(plan.get('annual_price', 0)),
                    "max_downloads_per_month": plan.get('max_downloads_per_month', 10),
                    "can_download": normalized_templates if normalized_templates else ['*'],
                    "features": list(plan.get('features', [])) if isinstance(plan.get('features'), (list, tuple)) else (plan.get('features', []) if plan.get('features') else []),
                    "is_active": plan.get('is_active', True)
                }
            
            return {"success": True, "plans": plans_dict, "source": "database"}
        except Exception as db_error:
            logger.warning(f"Database query failed, falling back to JSON: {db_error}")
            # Fallback to JSON
            plans = read_json_file(PLANS_PATH, {})
            return {"success": True, "plans": plans, "source": "json_fallback"}
    except Exception as e:
        logger.error(f"Error getting plans: {e}")
        # Final fallback
        try:
            plans = read_json_file(PLANS_PATH, {})
            return {"success": True, "plans": plans, "source": "json_error_fallback"}
        except Exception as final_exc:
            raise HTTPException(status_code=500, detail=str(final_exc))

@app.get("/templates/{template_name}")
async def get_template(template_name: str):
    """Get details for a specific template"""
    try:
        if SUPABASE_ENABLED:
            template_record = resolve_template_record(template_name)
            if not template_record:
                raise HTTPException(status_code=404, detail="Template not found in Supabase")

            placeholders = template_record.get('placeholders') or []
            placeholder_settings = fetch_template_placeholders(template_record['id'])

            file_meta = fetch_template_file_record(template_record['id']) or {}

            file_name = template_record.get('file_name') or template_name
            if not file_name.endswith('.docx'):
                file_name = f"{file_name}.docx"

            return {
                "id": str(template_record['id']),
                "name": file_name,
                "title": template_record.get('title') or file_name.replace('.docx', ''),
                "file_name": file_name.replace('.docx', ''),
                "file_with_extension": file_name,
                "size": file_meta.get('file_size', 0),
                "created_at": file_meta.get('uploaded_at') or template_record.get('created_at'),
                "placeholders": placeholders,
                "placeholder_count": len(placeholders),
                "settings": placeholder_settings
            }

        if not SUPABASE_ENABLED:
            # Legacy file-system fallback
            if not template_name.endswith('.docx'):
                template_name += '.docx'

            file_path = os.path.join(TEMPLATES_DIR, template_name)
            if not os.path.exists(file_path):
                raise HTTPException(status_code=404, detail="Template not found")

            file_size = os.path.getsize(file_path)
            created_at = datetime.fromtimestamp(os.path.getctime(file_path)).isoformat()
            placeholders = extract_placeholders_from_docx(file_path)

            return {
                "name": template_name,
                "title": template_name.replace('.docx', ''),
                "file_name": template_name.replace('.docx', ''),
                "file_with_extension": template_name,
                "size": file_size,
                "created_at": created_at,
                "placeholders": placeholders,
                "placeholder_count": len(placeholders)
            }

        raise HTTPException(status_code=404, detail="Template not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting template: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/upload-template")
async def upload_template(
    file: UploadFile = File(...),
    name: Optional[str] = Form(None),
    description: Optional[str] = Form(None)
    # current_user: str = Depends(get_current_user)  # Disabled for now
):
    """Upload a new template"""
    try:
        if not file.filename.endswith('.docx'):
            raise HTTPException(status_code=400, detail="Only .docx files are allowed")
        
        file_bytes = await file.read()
        if not file_bytes:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")

        # Write to temp file to extract placeholders
        with tempfile.NamedTemporaryFile(delete=False, suffix='.docx') as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        placeholders = extract_placeholders_from_docx(tmp_path)
        placeholders = list(dict.fromkeys(placeholders))
        os.remove(tmp_path)

        logger.info(f"Template uploaded: {file.filename} ({len(placeholders)} placeholders)")

        if SUPABASE_ENABLED:
            base_name = file.filename
            inferred_title = base_name[:-5] if base_name.endswith('.docx') else base_name
            existing_record = resolve_template_record(base_name)

            title_value = name.strip() if name else (existing_record.get('title') if existing_record and existing_record.get('title') else inferred_title)
            description_value = (description.strip() if description and description.strip() else (existing_record.get('description') if existing_record and existing_record.get('description') else f"Template: {title_value}"))

            template_payload = {
                'title': title_value,
                'description': description_value,
                'file_name': base_name,
                'placeholders': placeholders,
                'is_active': True,
                'updated_at': datetime.utcnow().isoformat()
            }

            try:
                upsert_response = supabase.table('document_templates').upsert(
                    template_payload,
                    on_conflict='file_name',
                    returning='representation'
                ).execute()

                if upsert_response.data:
                    template_record = upsert_response.data[0]
                else:
                    template_record = resolve_template_record(base_name)

                if not template_record:
                    raise HTTPException(status_code=500, detail="Failed to persist template metadata")

                template_id = template_record['id']

                file_payload = {
                    'template_id': template_id,
                    'filename': base_name,
                    'mime_type': file.content_type or 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    'file_size': len(file_bytes),
                    'file_data': encode_bytea(file_bytes),
                    'sha256': hashlib.sha256(file_bytes).hexdigest(),
                    'uploaded_at': datetime.utcnow().isoformat()
                }

                supabase.table('template_files').upsert(
                    file_payload,
                    on_conflict='template_id'
                ).execute()

                # Ensure placeholder settings rows exist (defaults to random)
                existing_settings = fetch_template_placeholders(template_id)
                new_rows = []
                for placeholder in placeholders:
                    if placeholder not in existing_settings:
                        new_rows.append({
                            'template_id': template_id,
                            'placeholder': placeholder,
                            'source': 'random',
                            'random_option': 'auto'
                        })
                if new_rows:
                    supabase.table('template_placeholders').insert(new_rows).execute()

                return {
                    "success": True,
                    "template_id": str(template_id),
                    "filename": base_name,
                    "placeholders": placeholders,
                    "placeholder_count": len(placeholders)
                }
            except HTTPException:
                raise
            except Exception as exc:
                logger.error(f"Failed to store template in Supabase: {exc}")
                raise HTTPException(status_code=500, detail="Failed to store template in Supabase")
        
        # Legacy behaviour (no Supabase available)
        file_path = os.path.join(TEMPLATES_DIR, file.filename)
        with open(file_path, 'wb') as f:
            f.write(file_bytes)

        return {
            "success": True,
            "filename": file.filename,
            "placeholders": placeholders,
            "placeholder_count": len(placeholders)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading template: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/templates/{template_name}")
async def delete_template(
    template_name: str
    # current_user: str = Depends(get_current_user)  # Disabled for now
):
    """Delete a template"""
    try:
        if SUPABASE_ENABLED:
            template_record = resolve_template_record(template_name)
            if not template_record:
                raise HTTPException(status_code=404, detail="Template not found")

            template_id = template_record['id']

            try:
                supabase.table('template_files').delete().eq('template_id', template_id).execute()
                supabase.table('template_placeholders').delete().eq('template_id', template_id).execute()
                supabase.table('document_templates').delete().eq('id', template_id).execute()
            except Exception as exc:
                logger.error(f"Failed to delete template from Supabase: {exc}")
                raise HTTPException(status_code=500, detail="Failed to delete template")

            return {"success": True, "message": f"Template {template_name} deleted"}

        if not template_name.endswith('.docx'):
            template_name += '.docx'

        file_path = os.path.join(TEMPLATES_DIR, template_name)
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="Template not found")

        os.remove(file_path)
        logger.info(f"Template deleted: {template_name}")

        return {"success": True, "message": f"Template {template_name} deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting template: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# STEP 5: PLACEHOLDER SETTINGS API (JSON-backed)
# ============================================================================

@app.get("/placeholder-settings")
async def get_placeholder_settings(template_name: Optional[str] = None, template_id: Optional[str] = None):
    """Get placeholder settings (all or per-template)"""
    try:
        if SUPABASE_ENABLED and (template_name or template_id):
            template_record = None
            if template_id:
                template_record = resolve_template_record(template_id)
            if not template_record and template_name:
                template_record = resolve_template_record(template_name)
            if not template_record:
                raise HTTPException(status_code=404, detail="Template not found")
            settings = fetch_template_placeholders(template_record['id'])
            return {
                "template": template_record.get('file_name') or template_name,
                "settings": settings,
                "template_id": str(template_record['id'])
            }

        if SUPABASE_ENABLED and not template_name:
            response = supabase.table('template_placeholders').select(
                'template_id, placeholder, source, custom_value, database_field, csv_id, csv_field, csv_row, random_option'
            ).execute()

            aggregated: Dict[str, Dict[str, Dict]] = {}
            for row in response.data or []:
                template_id = str(row['template_id'])
                aggregated.setdefault(template_id, {})[row['placeholder']] = {
                    'source': row.get('source', 'random'),
                    'customValue': row.get('custom_value') or '',
                    'databaseField': row.get('database_field') or '',
                    'csvId': row.get('csv_id') or '',
                    'csvField': row.get('csv_field') or '',
                    'csvRow': row['csv_row'] if row.get('csv_row') is not None else 0,
                    'randomOption': row.get('random_option', 'auto') or 'auto'
                }
            return {"settings": aggregated}

        if not SUPABASE_ENABLED:
            settings = read_json_file(PLACEHOLDER_SETTINGS_PATH, {})
            if template_name:
                template_settings = settings.get(template_name, {})
                return {"template": template_name, "settings": template_settings}
            return {"settings": settings}

        raise HTTPException(status_code=404, detail="Template not found")
    except Exception as e:
        logger.error(f"Error getting placeholder settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/placeholder-settings")
async def save_placeholder_settings(
    request: Request
    # current_user: str = Depends(get_current_user)  # Disabled for now
):
    """Save placeholder settings for a template"""
    try:
        data = await request.json()
        template_name = data.get('template_name')
        template_id_override = data.get('template_id')
        new_settings = data.get('settings', {})
        
        if not template_name and not template_id_override:
            raise HTTPException(status_code=400, detail="template_name or template_id is required")

        if SUPABASE_ENABLED:
            template_record = None
            if template_id_override:
                template_record = resolve_template_record(template_id_override)
            if not template_record and template_name:
                template_record = resolve_template_record(template_name)
            if not template_record:
                raise HTTPException(status_code=404, detail="Template not found")

            template_id = template_record['id']

            # Normalise payload to Supabase schema then upsert
            sanitised_settings: Dict[str, Dict] = {}
            for placeholder, cfg in new_settings.items():
                if not placeholder:
                    continue
                sanitised_settings[placeholder] = {
                    'source': cfg.get('source', 'random'),
                    'customValue': cfg.get('customValue'),
                    'databaseField': cfg.get('databaseField'),
                    'csvId': cfg.get('csvId'),
                    'csvField': cfg.get('csvField'),
                    'csvRow': cfg.get('csvRow', 0),
                    'randomOption': cfg.get('randomOption', 'auto')
                }

            upsert_template_placeholders(template_id, sanitised_settings)

            # Return latest snapshot
            refreshed = fetch_template_placeholders(template_id)
            return {"success": True, "template": template_name, "template_id": str(template_id), "settings": refreshed}

        if not SUPABASE_ENABLED and template_name:
            all_settings = read_json_file(PLACEHOLDER_SETTINGS_PATH, {})
            if template_name not in all_settings:
                all_settings[template_name] = {}
            all_settings[template_name].update(new_settings)
            write_json_atomic(PLACEHOLDER_SETTINGS_PATH, all_settings)
            logger.info(f"Saved placeholder settings for {template_name}")
            return {"success": True, "template": template_name, "settings": all_settings[template_name]}

        raise HTTPException(status_code=503, detail="Supabase not available")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving placeholder settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# STEP 6: PLANS API (JSON-backed)
# ============================================================================

@app.get("/plans")
async def get_plans():
    """Get all subscription plans"""
    try:
        plans = read_json_file(PLANS_PATH, {})
        return {"success": True, "plans": plans}
    except Exception as e:
        logger.error(f"Error getting plans: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/user-plan/{user_id}")
async def get_user_plan(user_id: str):
    """Get plan for a specific user (mock - can be extended)"""
    try:
        plans_data = read_json_file(PLANS_PATH, {})
        # For now, return basic plan as default
        # In production, this would look up user's actual plan
        return {
            "success": True,
            "user_id": user_id,
            "plan": "basic",  # Default
            "plan_data": plans_data.get("basic", {})
        }
    except Exception as e:
        logger.error(f"Error getting user plan: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/check-download-permission")
async def check_download_permission(request: Request):
    """Check if a user can download a specific template"""
    try:
        data = await request.json()
        user_id = data.get('user_id', 'basic')  # Default to basic
        template_name = data.get('template_name')
        
        if not template_name:
            raise HTTPException(status_code=400, detail="template_name is required")
        
        plans_data = read_json_file(PLANS_PATH, {})
        user_plan_data = plans_data.get(user_id, plans_data.get("basic", {}))
        
        can_download = user_plan_data.get("can_download", [])
        
        # Check if user can download all templates
        if "*" in can_download:
            return {"can_download": True, "reason": "unlimited"}
        
        # Check if specific template is allowed
        can_download_bool = template_name in can_download or any(
            template_name.startswith(t.replace("*", "")) for t in can_download if "*" in t
        )
        
        return {
            "can_download": can_download_bool,
            "user_id": user_id,
            "template_name": template_name,
            "plan": user_plan_data.get("name", "Unknown")
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking permission: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/update-plan")
async def update_plan(request: Request):
    """Update a subscription plan"""
    try:
        body = await request.json()
        plan_id = body.get('plan_id')
        plan_data = body.get('plan_data')
        
        if not plan_id or not plan_data:
            raise HTTPException(status_code=400, detail="plan_id and plan_data are required")
        
        # If Supabase is available, update in database
        if supabase:
            try:
                # Get plan by tier
                plan_res = supabase.table('subscription_plans').select('id').eq('plan_tier', plan_id).limit(1).execute()
                if plan_res.data:
                    db_plan_id = plan_res.data[0]['id']
                    
                    # Update max_downloads_per_month
                    update_data = {}
                    if 'max_downloads_per_month' in plan_data:
                        update_data['max_downloads_per_month'] = plan_data['max_downloads_per_month']
                    
                    if update_data:
                        supabase.table('subscription_plans').update(update_data).eq('id', db_plan_id).execute()
                    
                    # Update template permissions if provided
                    # Check both 'allowed_templates' and 'can_download' for compatibility
                    allowed = plan_data.get('allowed_templates') or plan_data.get('can_download')
                    
                    if allowed:
                        # Get all templates
                        templates_res = supabase.table('document_templates').select('id, file_name').eq('is_active', True).execute()
                        
                        if templates_res.data:
                            # Delete existing permissions
                            supabase.table('plan_template_permissions').delete().eq('plan_id', db_plan_id).execute()
                            
                            # Create new permissions
                            if allowed == '*' or allowed == ['*'] or (isinstance(allowed, list) and '*' in allowed):
                                # Allow all templates
                                for template in templates_res.data:
                                    supabase.table('plan_template_permissions').insert({
                                        'plan_id': db_plan_id,
                                        'template_id': template['id'],
                                        'can_download': True
                                    }).execute()
                                logger.info(f"Set all templates permission for plan {plan_id}")
                            elif isinstance(allowed, list):
                                # Allow specific templates - normalize names (remove .docx if present)
                                template_names = {t.replace('.docx', '').strip() for t in allowed if t != '*'}
                                
                                for template in templates_res.data:
                                    template_name = template.get('file_name', '').strip()
                                    # Match by file_name (without extension)
                                    if template_name in template_names:
                                        supabase.table('plan_template_permissions').insert({
                                            'plan_id': db_plan_id,
                                            'template_id': template['id'],
                                            'can_download': True
                                        }).execute()
                                logger.info(f"Set {len(template_names)} template permissions for plan {plan_id}")
                    
                    logger.info(f"Updated plan in database: {plan_id}")
            except Exception as e:
                logger.warning(f"Failed to update plan in database: {e}, using JSON fallback")
        
        # Also update JSON file as fallback/primary storage
        plans = read_json_file(PLANS_PATH, {})
        if plan_id not in plans:
            raise HTTPException(status_code=404, detail=f"Plan '{plan_id}' not found")
        
        # Get existing plan data
        existing_plan = plans.get(plan_id, {})
        
        # Merge with existing plan data to preserve other fields
        # Only update fields that are provided in plan_data
        updated_plan = existing_plan.copy()
        
        # Update specific fields if provided
        if 'can_download' in plan_data:
            can_download = plan_data['can_download']
            # Normalize: ensure it's a list and remove .docx extensions for consistency
            if isinstance(can_download, str):
                updated_plan['can_download'] = [can_download]
            elif isinstance(can_download, list):
                # Remove .docx extension from template names for consistency
                updated_plan['can_download'] = [t.replace('.docx', '').strip() if isinstance(t, str) else t for t in can_download if t]
            else:
                updated_plan['can_download'] = can_download
        
        if 'max_downloads_per_month' in plan_data:
            updated_plan['max_downloads_per_month'] = plan_data['max_downloads_per_month']
        
        if 'features' in plan_data:
            updated_plan['features'] = plan_data['features'] if isinstance(plan_data['features'], list) else []
        
        # Preserve other fields from plan_data if they exist
        for key in ['name', 'description', 'monthly_price', 'annual_price', 'plan_tier', 'is_active']:
            if key in plan_data:
                updated_plan[key] = plan_data[key]
        
        plans[plan_id] = updated_plan
        write_json_atomic(PLANS_PATH, plans)
        
        logger.info(f"Updated plan: {plan_id}")
        logger.info(f"  - can_download: {updated_plan.get('can_download')}")
        logger.info(f"  - max_downloads_per_month: {updated_plan.get('max_downloads_per_month')}")
        logger.info(f"  - features: {updated_plan.get('features')}")
        
        return {"success": True, "plan_id": plan_id, "plan_data": updated_plan}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating plan: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/check-download-permission-db")
async def check_download_permission_db(request: Request):
    """Check if a user can download a specific template from database"""
    try:
        body = await request.json()
        user_id = body.get('user_id')
        template_name = body.get('template_name')
        
        if not user_id or not template_name:
            raise HTTPException(status_code=400, detail="user_id and template_name are required")
        
        if not supabase:
            # Fallback to JSON-based check
            return await check_download_permission(request)
        
        # Get template ID
        template_file_name = template_name.replace('.docx', '')
        template_res = supabase.table('document_templates').select('id').eq('file_name', template_file_name).eq('is_active', True).limit(1).execute()
        
        if not template_res.data:
            raise HTTPException(status_code=404, detail="Template not found")
        
        template_id = template_res.data[0]['id']
        
        # Call database function to check permissions
        permission_res = supabase.rpc('can_user_download_template', {
            'p_user_id': user_id,
            'p_template_id': template_id
        }).execute()
        
        if permission_res.data:
            return {
                "success": True,
                **permission_res.data
            }
        else:
            return {
                "success": False,
                "can_download": False,
                "reason": "No permission data returned"
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking download permission: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.options("/user-downloadable-templates")
async def options_user_downloadable_templates(request: Request):
    """Handle CORS preflight for user-downloadable-templates endpoint"""
    return Response(status_code=200, headers=_cors_preflight_headers(request, "POST, OPTIONS"))

@app.post("/user-downloadable-templates")
async def get_user_downloadable_templates(request: Request):
    """Get list of templates user can download with download counts"""
    try:
        body = await request.json()
        user_id = body.get('user_id')
        
        if not user_id:
            raise HTTPException(status_code=400, detail="user_id is required")
        
        if not supabase:
            # Fallback to JSON-based templates
            templates = []
            for filename in os.listdir(TEMPLATES_DIR):
                if filename.endswith('.docx'):
                    file_path = os.path.join(TEMPLATES_DIR, filename)
                    file_size = os.path.getsize(file_path)
                    created_at = datetime.fromtimestamp(os.path.getctime(file_path)).isoformat()
                    placeholders = extract_placeholders_from_docx(file_path)
                    
                    templates.append({
                        "name": filename,
                        "file_name": filename.replace('.docx', ''),
                        "size": file_size,
                        "created_at": created_at,
                        "placeholders": placeholders,
                        "can_download": True,  # Default to true for JSON fallback
                        "max_downloads": 10,
                        "current_downloads": 0,
                        "remaining_downloads": 10
                    })
            
            return {
                "success": True,
                "templates": templates,
                "source": "json"
            }
        
        # Call database function
        templates_res = supabase.rpc('get_user_downloadable_templates', {
            'p_user_id': user_id
        }).execute()
        
        if templates_res.data:
            # Enhance with template details
            template_ids = [t['template_id'] for t in templates_res.data]
            details_res = supabase.table('document_templates').select('id, title, description, file_name, placeholders').in_('id', template_ids).execute()
            
            details_map = {d['id']: d for d in (details_res.data or [])}
            
            enhanced_templates = []
            for t in templates_res.data:
                template_id = t['template_id']
                details = details_map.get(template_id, {})
                enhanced_templates.append({
                    "id": str(template_id),
                    "name": details.get('title', 'Unknown'),
                    "file_name": details.get('file_name', ''),
                    "description": details.get('description', ''),
                    "placeholders": details.get('placeholders', []),
                    "can_download": t['can_download'],
                    "max_downloads": t['max_downloads'],
                    "current_downloads": t['current_downloads'],
                    "remaining_downloads": t['remaining_downloads']
                })
            
            return {
                "success": True,
                "templates": enhanced_templates,
                "source": "database"
            }
        else:
            return {
                "success": True,
                "templates": [],
                "source": "database"
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user downloadable templates: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# CSV DATA ENDPOINTS
# ============================================================================

@app.post("/upload-csv")
async def upload_csv(
    file: UploadFile = File(...),
    data_type: str = Form(...)
    # current_user: str = Depends(get_current_user)  # Disabled for now
):
    """Upload CSV data file"""
    try:
        if not file.filename.endswith('.csv'):
            raise HTTPException(status_code=400, detail="Only .csv files are allowed")
        
        # Map data_type to filename
        filename_map = {
            "buyers_sellers": "buyers_sellers_data_220.csv",
            "bank_accounts": "bank_accounts.csv",
            "icpo": "icpo_section4_6_data_230.csv"
        }
        
        filename = filename_map.get(data_type, f"{data_type}.csv")
        file_path = os.path.join(DATA_DIR, filename)
        
        # Save file
        with open(file_path, 'wb') as f:
            content = await file.read()
            f.write(content)
        
        logger.info(f"CSV uploaded: {filename}")
        return {"success": True, "filename": filename, "data_type": data_type}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading CSV: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/data/all")
async def get_all_data():
    """Get status of all CSV data sources"""
    try:
        data_sources = {}
        csv_files = {
            "buyers_sellers": "buyers_sellers_data_220.csv",
            "bank_accounts": "bank_accounts.csv",
            "icpo": "icpo_section4_6_data_230.csv"
        }
        
        for name, filename in csv_files.items():
            file_path = os.path.join(DATA_DIR, filename)
            exists = os.path.exists(file_path)
            size = os.path.getsize(file_path) if exists else 0
            
            if exists:
                # Count rows
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        row_count = sum(1 for _ in reader)
                except:
                    row_count = 0
            else:
                row_count = 0
            
            data_sources[name] = {
                "filename": filename,
                "exists": exists,
                "size": size,
                "row_count": row_count
            }
        
        return {"success": True, "data_sources": data_sources}
    except Exception as e:
        logger.error(f"Error getting data sources: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/csv-files")
async def get_csv_files():
    """Get list of available CSV files"""
    try:
        csv_files = []
        csv_mapping = {
            "buyers_sellers": "buyers_sellers_data_220.csv",
            "bank_accounts": "bank_accounts.csv",
            "icpo": "icpo_section4_6_data_230.csv"
        }
        
        for name, filename in csv_mapping.items():
            file_path = os.path.join(DATA_DIR, filename)
            if os.path.exists(file_path):
                csv_files.append({
                    "id": name,
                    "filename": filename,
                    "display_name": name.replace('_', ' ').title()
                })
        
        return {"success": True, "csv_files": csv_files}
    except Exception as e:
        logger.error(f"Error getting CSV files: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/csv-fields/{csv_id}")
async def get_csv_fields(csv_id: str):
    """Get columns/fields from a CSV file"""
    try:
        csv_mapping = {
            "buyers_sellers": "buyers_sellers_data_220.csv",
            "bank_accounts": "bank_accounts.csv",
            "icpo": "icpo_section4_6_data_230.csv"
        }
        
        filename = csv_mapping.get(csv_id)
        if not filename:
            raise HTTPException(status_code=404, detail="CSV file not found")
        
        file_path = os.path.join(DATA_DIR, filename)
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail=f"CSV file not found: {filename}")
        
        # Read CSV headers
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            fields = [{"name": field, "label": field.replace('_', ' ').title()} for field in reader.fieldnames]
        
        return {"success": True, "fields": fields}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting CSV fields: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/csv-rows/{csv_id}/{field_name}")
async def get_csv_rows(csv_id: str, field_name: str):
    """Get all unique rows for a specific field in a CSV file"""
    try:
        csv_mapping = {
            "buyers_sellers": "buyers_sellers_data_220.csv",
            "bank_accounts": "bank_accounts.csv",
            "icpo": "icpo_section4_6_data_230.csv"
        }
        
        filename = csv_mapping.get(csv_id)
        if not filename:
            raise HTTPException(status_code=404, detail="CSV file not found")
        
        file_path = os.path.join(DATA_DIR, filename)
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail=f"CSV file not found: {filename}")
        
        # Read CSV rows for the specific field
        rows_data = []
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for idx, row in enumerate(reader):
                if field_name in row and row[field_name]:
                    rows_data.append({
                        "row_index": idx,
                        "value": row[field_name],
                        "preview": row[field_name][:100] + "..." if len(str(row[field_name])) > 100 else row[field_name]
                    })
        
        return {"success": True, "rows": rows_data[:100]}  # Limit to 100 rows
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting CSV rows: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def get_csv_data(csv_id: str, row_index: int = 0) -> Optional[Dict]:
    """Get data from a CSV file by row index"""
    try:
        csv_mapping = {
            "buyers_sellers": "buyers_sellers_data_220.csv",
            "bank_accounts": "bank_accounts.csv",
            "icpo": "icpo_section4_6_data_230.csv"
        }
        
        filename = csv_mapping.get(csv_id)
        if not filename:
            return None
        
        file_path = os.path.join(DATA_DIR, filename)
        if not os.path.exists(file_path):
            return None
        
        # Read CSV data
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            
            if row_index < len(rows):
                return rows[row_index]
        
        return None
    except Exception as e:
        logger.error(f"Error reading CSV data: {e}")
        return None

# ============================================================================
# STEP 7: DOCUMENT GENERATION (with PDF export)
# ============================================================================

def get_vessel_data(imo: str) -> Optional[Dict]:
    """Get vessel data from Supabase database using IMO number"""
    if not imo:
        logger.error("Vessel IMO is required but not provided")
        raise ValueError("Vessel IMO is required")
    
    try:
        if not supabase:
            logger.warning(f"Supabase not available, returning minimal data for IMO: {imo}")
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
        
        logger.info(f"Fetching vessel data from database for IMO: {imo}")
        response = supabase.table('vessels').select('*').eq('imo', imo).execute()
        
        if response.data and len(response.data) > 0:
            vessel_data = response.data[0]
            logger.info(f"Found vessel in database: {vessel_data.get('name', 'Unknown')} (IMO: {imo})")
            # Ensure IMO is always in the returned data
            vessel_data['imo'] = imo
            return vessel_data
        else:
            logger.warning(f"Vessel with IMO {imo} not found in database, using fallback data")
            # Return minimal data structure but log the issue
            return {
                'imo': imo,
                'name': f'Vessel {imo}',
                'vessel_type': 'Tanker',
                'flag': 'Panama',
            }
    except Exception as e:
        logger.error(f"Error fetching vessel data for IMO {imo}: {e}")
        # Return minimal data on error but always include the IMO
        return {
            'imo': imo,
            'name': f'Vessel {imo}',
            'vessel_type': 'Tanker',
            'flag': 'Panama',
        }

def _calculate_similarity(str1: str, str2: str) -> float:
    """
    Calculate similarity ratio between two strings using Levenshtein distance.
    Returns a value between 0.0 (completely different) and 1.0 (identical).
    """
    if not str1 or not str2:
        return 0.0
    
    if str1 == str2:
        return 1.0
    
    # Simple Levenshtein distance implementation
    len1, len2 = len(str1), len(str2)
    if len1 == 0:
        return 0.0 if len2 > 0 else 1.0
    if len2 == 0:
        return 0.0
    
    # Create matrix
    matrix = [[0] * (len2 + 1) for _ in range(len1 + 1)]
    
    # Initialize first row and column
    for i in range(len1 + 1):
        matrix[i][0] = i
    for j in range(len2 + 1):
        matrix[0][j] = j
    
    # Fill matrix
    for i in range(1, len1 + 1):
        for j in range(1, len2 + 1):
            cost = 0 if str1[i-1] == str2[j-1] else 1
            matrix[i][j] = min(
                matrix[i-1][j] + 1,      # deletion
                matrix[i][j-1] + 1,      # insertion
                matrix[i-1][j-1] + cost  # substitution
            )
    
    # Calculate similarity ratio
    max_len = max(len1, len2)
    distance = matrix[len1][len2]
    similarity = 1.0 - (distance / max_len) if max_len > 0 else 1.0
    return similarity

def _intelligent_field_match(placeholder: str, vessel: Dict) -> tuple:
    """
    Intelligently match a placeholder name to a vessel database field with priority scoring.
    Returns (matched_field_name, matched_value) or (None, None) if no match.
    Uses multiple strategies with confidence scoring to find the best match.
    """
    if not vessel:
        return (None, None)
    
    # Normalize placeholder name for matching
    placeholder_clean = placeholder.strip()
    placeholder_normalized = placeholder_clean.lower().replace('_', '').replace('-', '').replace(' ', '')
    placeholder_words = set(re.findall(r'[a-z]+', placeholder_normalized))
    
    # Comprehensive field name mappings with priority
    # Format: {normalized_placeholder: database_field}
    field_mappings = {
        # IMO related
        'imonumber': 'imo', 'imo_number': 'imo', 'imono': 'imo', 'imo': 'imo',
        
        # Vessel identification
        'vesselname': 'name', 'vessel_name': 'name', 'shipname': 'name',
        'vesseltype': 'vessel_type', 'vessel_type': 'vessel_type', 'shiptype': 'vessel_type',
        'flagstate': 'flag', 'flag_state': 'flag', 'flag': 'flag',
        'mmsi': 'mmsi', 'mmsinumber': 'mmsi',
        
        # Dimensions
        'lengthoverall': 'length', 'length_overall': 'length', 'loa': 'length',
        'length': 'length', 'vessellength': 'length',
        'width': 'width', 'beam': 'beam', 'breadth': 'beam',
        'draft': 'draft', 'draught': 'draught', 'maxdraft': 'draft',
        
        # Tonnage
        'deadweight': 'deadweight', 'dwt': 'deadweight', 'deadweighttonnage': 'deadweight',
        'grosstonnage': 'gross_tonnage', 'gross_tonnage': 'gross_tonnage', 'grt': 'gross_tonnage',
        'nettonnage': 'net_tonnage', 'net_tonnage': 'net_tonnage', 'nrt': 'net_tonnage',
        
        # Capacity
        'cargocapacity': 'cargo_capacity', 'cargo_capacity': 'cargo_capacity',
        'cargotanks': 'cargo_tanks', 'cargo_tanks': 'cargo_tanks',
        'pumpingcapacity': 'pumping_capacity', 'pumping_capacity': 'pumping_capacity',
        
        # Performance
        'speed': 'speed', 'cruisingspeed': 'speed', 'maxspeed': 'speed',
        'enginetype': 'engine_power', 'engine_type': 'engine_power',
        'enginepower': 'engine_power', 'engine_power': 'engine_power',
        'fuelconsumption': 'fuel_consumption', 'fuel_consumption': 'fuel_consumption',
        
        # Ownership & Operations
        'vesselowner': 'owner_name', 'vessel_owner': 'owner_name', 'owner': 'owner_name',
        'ownername': 'owner_name', 'owner_name': 'owner_name',
        'vesseloperator': 'operator_name', 'vessel_operator': 'operator_name',
        'operator': 'operator_name', 'operatorname': 'operator_name', 'operator_name': 'operator_name',
        'ismmanager': 'ism_manager', 'ism_manager': 'ism_manager',
        'classsociety': 'class_society', 'class_society': 'class_society',
        
        # Communication
        'callsign': 'callsign', 'call_sign': 'callsign', 'callsignnumber': 'callsign',
        
        # Dates
        'yearbuilt': 'built', 'year_built': 'built', 'built': 'built',
        'buildyear': 'built', 'constructionyear': 'built',
        
        # Location & Navigation
        'registryport': 'registry_port', 'registry_port': 'registry_port',
        'currentport': 'currentport', 'current_port': 'currentport',
        'departureport': 'departure_port', 'departure_port': 'departure_port',
        'destinationport': 'destination_port', 'destination_port': 'destination_port',
        'loadingport': 'loading_port', 'loading_port': 'loading_port',
        'currentregion': 'current_region', 'current_region': 'current_region',
        'navstatus': 'nav_status', 'nav_status': 'nav_status', 'status': 'status',
        'course': 'course',
        
        # Cargo
        'cargotype': 'cargo_type', 'cargo_type': 'cargo_type',
        'cargoquantity': 'cargo_quantity', 'cargo_quantity': 'cargo_quantity',
        'quantity': 'quantity',
        'oiltype': 'oil_type', 'oil_type': 'oil_type',
        'oilsource': 'oil_source', 'oil_source': 'oil_source',
        
        # Commercial
        'buyername': 'buyer_name', 'buyer_name': 'buyer_name',
        'sellername': 'seller_name', 'seller_name': 'seller_name',
        'price': 'price', 'marketprice': 'market_price', 'market_price': 'market_price',
        'dealvalue': 'deal_value', 'deal_value': 'deal_value',
        'sourcecompany': 'source_company', 'source_company': 'source_company',
        'targetrefinery': 'target_refinery', 'target_refinery': 'target_refinery',
        'shippingtype': 'shipping_type', 'shipping_type': 'shipping_type',
        'routedistance': 'route_distance', 'route_distance': 'route_distance',
        'routeinfo': 'route_info', 'route_info': 'route_info',
        
        # Crew
        'crewsize': 'crew_size', 'crew_size': 'crew_size',
    }
    
    # Strategy 1: Direct mapping (highest priority)
    if placeholder_normalized in field_mappings:
        mapped_field = field_mappings[placeholder_normalized]
        if mapped_field in vessel:
            value = vessel[mapped_field]
            if value is not None and str(value).strip() != '':
                logger.debug(f"  ✅ Direct mapping: '{placeholder}' -> '{mapped_field}'")
                return (mapped_field, str(value).strip())
    
    # Strategy 2: Exact match after normalization (high priority)
    best_match = None
    best_score = 0.0
    best_field = None
    
    for field_name, field_value in vessel.items():
        if field_value is None or str(field_value).strip() == '':
            continue
        
        field_normalized = field_name.lower().replace('_', '').replace('-', '').replace(' ', '')
        
        # Exact match after normalization
        if placeholder_normalized == field_normalized:
            logger.debug(f"  ✅ Exact normalized match: '{placeholder}' -> '{field_name}'")
            return (field_name, str(field_value).strip())
        
        # Calculate similarity score
        similarity = _calculate_similarity(placeholder_normalized, field_normalized)
        
        # Boost score for substring matches
        if placeholder_normalized in field_normalized or field_normalized in placeholder_normalized:
            similarity = max(similarity, 0.85)  # Boost substring matches
        
        # Word overlap bonus
        field_words = set(re.findall(r'[a-z]+', field_normalized))
        if placeholder_words and field_words:
            common_words = placeholder_words.intersection(field_words)
            if common_words:
                meaningful_common = [w for w in common_words if len(w) >= 3]
                if meaningful_common:
                    # Calculate word overlap ratio
                    overlap_ratio = len(meaningful_common) / max(len(placeholder_words), len(field_words))
                    similarity = max(similarity, 0.7 + (overlap_ratio * 0.2))  # Boost by overlap
        
        # Track best match
        if similarity > best_score:
            best_score = similarity
            best_field = field_name
            best_match = str(field_value).strip()
    
    # Strategy 3: Use best match if confidence is high enough
    if best_match and best_score >= 0.75:  # 75% similarity threshold
        logger.debug(f"  ✅ High confidence match: '{placeholder}' -> '{best_field}' (similarity: {best_score:.2f})")
        return (best_field, best_match)
    
    # Strategy 4: Try partial word matching with lower threshold
    if best_match and best_score >= 0.60:  # 60% similarity threshold
        # Additional validation: check if key words match
        key_words_placeholder = {w for w in placeholder_words if len(w) >= 4}
        if key_words_placeholder:
            best_field_words = set(re.findall(r'[a-z]+', best_field.lower().replace('_', '').replace('-', '')))
            key_words_field = {w for w in best_field_words if len(w) >= 4}
            if key_words_placeholder.intersection(key_words_field):
                logger.debug(f"  ✅ Medium confidence match: '{placeholder}' -> '{best_field}' (similarity: {best_score:.2f})")
                return (best_field, best_match)
    
    # No match found
    return (None, None)

def generate_realistic_random_data(placeholder: str, vessel_imo: str = None) -> str:
    """Generate realistic random data for placeholders"""
    import random
    import hashlib
    
    # Create unique seed for consistent data
    if vessel_imo:
        seed_input = f"{vessel_imo}_{placeholder.lower()}"
        random.seed(int(hashlib.md5(seed_input.encode()).hexdigest()[:8], 16))
    
    placeholder_lower = placeholder.lower().replace('_', '').replace(' ', '').replace('-', '')
    
    # Simple fallback data generation
    if 'date' in placeholder_lower:
        from datetime import timedelta
        return (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d')
    elif 'result' in placeholder_lower:
        # Generate varied results
        results = ['0.01%', '0.15%', '0.23%', '0.45%', '0.67%', '1.20%', '2.34%', '0.89%', '0.12%']
        return random.choice(results)
    elif 'email' in placeholder_lower:
        return f"test{random.randint(100,999)}@example.com"
    elif 'phone' in placeholder_lower or 'tel' in placeholder_lower:
        return f"+{random.randint(1,99)} {random.randint(100,999)} {random.randint(100000,999999)}"
    elif 'name' in placeholder_lower:
        return f"Test Company {random.randint(1,100)}"
    elif 'ref' in placeholder_lower or 'number' in placeholder_lower:
        return f"REF-{random.randint(100000,999999)}"
    else:
        return f"Test_{placeholder}"

def replace_placeholders_in_docx(docx_path: str, data: Dict[str, str]) -> str:
    """Replace placeholders in a DOCX file"""
    try:
        logger.info(f"Starting replacement with {len(data)} mappings")
        for key, value in data.items():
            logger.debug(f"Will replace {key} -> {value}")
        
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
                        logger.debug(f"Replaced '{fmt}' with '{value}' in paragraph")
        
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
                                    logger.debug(f"Replaced '{fmt}' with '{value}' in table cell")
        
        logger.info(f"Total replacements made: {replacements_made}")
        
        # Save the modified document
        output_path = os.path.join(TEMP_DIR, f"processed_{uuid.uuid4().hex}.docx")
        doc.save(output_path)
        return output_path
        
    except Exception as e:
        logger.error(f"Error processing document: {e}")
        raise HTTPException(status_code=500, detail=f"Document processing failed: {str(e)}")

def convert_docx_to_pdf(docx_path: str) -> str:
    """Convert DOCX to PDF using docx2pdf"""
    try:
        pdf_path = os.path.join(TEMP_DIR, f"output_{uuid.uuid4().hex}.pdf")
        
        # Try docx2pdf first (pure Python, no external dependencies on Windows)
        try:
            from docx2pdf import convert
            logger.info(f"Converting DOCX to PDF using docx2pdf: {docx_path}")
            convert(docx_path, pdf_path)
            
            if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
                logger.info(f"Successfully converted to PDF: {pdf_path}")
                return pdf_path
            else:
                logger.warning("docx2pdf created empty PDF")
        except ImportError:
            logger.warning("docx2pdf not installed, trying LibreOffice fallback")
        except Exception as e:
            logger.warning(f"docx2pdf failed: {e}, trying LibreOffice fallback")
        
        # Fallback: Try LibreOffice on Windows
        import subprocess
        libreoffice_paths = [
            r'C:\Program Files\LibreOffice\program\soffice.exe',
            r'C:\Program Files (x86)\LibreOffice\program\soffice.exe',
            'soffice',  # fallback
        ]
        
        for path in libreoffice_paths:
            try:
                result = subprocess.run([path, '--version'], 
                                      capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    libreoffice_found = path
                    cmd = [
                        libreoffice_found,
                        '--headless',
                        '--convert-to', 'pdf',
                        '--outdir', TEMP_DIR,
                        docx_path
                    ]
                    subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                    
                    # Get generated PDF
                    expected_pdf = os.path.join(
                        TEMP_DIR, 
                        os.path.splitext(os.path.basename(docx_path))[0] + '.pdf'
                    )
                    if os.path.exists(expected_pdf):
                        os.rename(expected_pdf, pdf_path)
                        return pdf_path
            except:
                continue
        
        # If no PDF conversion, return DOCX
        logger.warning("All PDF conversion methods failed, returning DOCX")
        return docx_path
    except Exception as e:
        logger.warning(f"PDF conversion failed: {e}, returning DOCX")
        return docx_path

@app.options("/generate-document")
async def options_generate_document(request: Request):
    """Handle CORS preflight for generate-document endpoint"""
    return Response(status_code=200, headers=_cors_preflight_headers(request, "POST, OPTIONS"))

@app.post("/generate-document")
async def generate_document(request: Request):
    """Generate a document from template"""
    template_temp_path: Optional[str] = None
    template_record: Optional[Dict] = None
    try:
        body = await request.json()
        template_name = body.get('template_name')
        vessel_imo = body.get('vessel_imo')
        user_id = body.get('user_id')  # Optional: for permission checking
        
        # Validate required fields
        if not template_name:
            raise HTTPException(status_code=422, detail="template_name is required")
        
        if not vessel_imo:
            raise HTTPException(status_code=422, detail="vessel_imo is required. Please provide the IMO number of the vessel.")
        
        # Log the vessel IMO being used - CRITICAL for debugging
        logger.info("=" * 80)
        logger.info(f"🚢 GENERATING DOCUMENT")
        logger.info(f"   Template: {template_name}")
        logger.info(f"   Vessel IMO: {vessel_imo} (from vessel detail page)")
        logger.info(f"   User ID: {user_id}")
        logger.info("=" * 80)
        
        effective_template_name = template_name
        template_settings: Dict[str, Dict] = {}
        template_temp_path: Optional[str] = None
        template_record: Optional[Dict] = None

        if SUPABASE_ENABLED:
            template_record = resolve_template_record(template_name)
            if not template_record:
                raise HTTPException(status_code=404, detail=f"Template not found: {template_name}")

            template_settings = fetch_template_placeholders(template_record['id'])

            file_record = fetch_template_file_record(template_record['id'], include_data=True)
            if not file_record:
                raise HTTPException(status_code=404, detail=f"Template file missing for: {template_name}")

            file_data = file_record.get("file_data")
            if not file_data:
                logger.error(f"Template file missing data for template_id={template_record['id']}")
                raise HTTPException(status_code=404, detail="Template file not found")

            template_temp_path = write_temp_docx_from_record(file_record)
            template_path = template_temp_path
            effective_template_name = template_record.get('file_name') or template_name
        else:
            # Handle template name with/without extension for legacy file storage
            if not effective_template_name.endswith('.docx'):
                effective_template_name += '.docx'
            
            template_path = os.path.join(TEMPLATES_DIR, effective_template_name)
            if not os.path.exists(template_path):
                raise HTTPException(status_code=404, detail=f"Template not found: {effective_template_name}")
            
            placeholder_settings = read_json_file(PLACEHOLDER_SETTINGS_PATH, {})
            template_settings = placeholder_settings.get(effective_template_name, {})
            
            if not template_settings:
                template_name_no_ext = effective_template_name.replace('.docx', '')
                template_settings = placeholder_settings.get(template_name_no_ext, {})
                if template_settings:
                    logger.info(f"Found settings using template name without extension: {template_name_no_ext}")
            
            if not template_settings and not effective_template_name.endswith('.docx'):
                template_settings = placeholder_settings.get(effective_template_name + '.docx', {})
                if template_settings:
                    logger.info(f"Found settings using template name with extension: {effective_template_name + '.docx'}")

        logger.info(f"Loaded {len(template_settings)} placeholder settings for {effective_template_name}")
        if template_settings:
            logger.info(f"Template settings keys: {list(template_settings.keys())[:5]}...")  # Show first 5 placeholders
        
        # Get vessel data from database using the provided IMO
        logger.info(f"📊 Fetching vessel data from database for IMO: {vessel_imo}")
        vessel = get_vessel_data(vessel_imo)
        
        if vessel:
            vessel_name = vessel.get('name', 'Unknown')
            logger.info(f"✅ Vessel found: {vessel_name} (IMO: {vessel_imo})")
            logger.info(f"   Vessel data fields: {list(vessel.keys())}")
        else:
            logger.error(f"❌ Vessel NOT FOUND in database for IMO: {vessel_imo}")
            vessel = {'imo': vessel_imo, 'name': f'Vessel {vessel_imo}'}
        
        # CRITICAL: Always ensure the vessel IMO from the page is in the vessel data
        # This ensures IMO placeholders always get the correct IMO from the vessel page
        vessel['imo'] = vessel_imo
        logger.info(f"🔑 Set vessel['imo'] = '{vessel_imo}' (from vessel detail page)")
        logger.info(f"   Final vessel data: {dict(list(vessel.items())[:10])}...")  # Show first 10 fields
        
        # Extract placeholders
        placeholders = extract_placeholders_from_docx(template_path)
        
        # Generate data for each placeholder
        data_mapping = {}
        logger.info(f"📝 Processing {len(placeholders)} placeholders from document")
        logger.info(f"⚙️  Template has {len(template_settings)} configured placeholders in CMS")
        
        if template_settings:
            logger.info(f"   Configured placeholders: {list(template_settings.keys())[:10]}...")
        
        for placeholder in placeholders:
            found = False
            
            # IMPORTANT: Only use database data if explicitly configured in CMS
            # Priority 1: Check if placeholder has custom settings configured in CMS
            if placeholder in template_settings:
                logger.info(f"\n🔍 Processing placeholder: '{placeholder}'")
                setting = template_settings[placeholder]
                source = setting.get('source', 'random')
                logger.info(f"Processing placeholder '{placeholder}': source={source}, full setting={setting}")
                
                if source == 'custom':
                    # Use custom value from CMS
                    custom_value = setting.get('customValue', '')
                    if custom_value:
                        data_mapping[placeholder] = custom_value
                        logger.info(f"{placeholder} -> {custom_value} (CMS custom value)")
                    found = True
                elif source == 'database':
                    # Use database field - try explicit field first, then intelligent matching
                    # This uses the vessel data from the vessel detail page (vessel_imo)
                    database_field = setting.get('databaseField', '').strip()
                    logger.info(f"  🗄️  DATABASE source configured for '{placeholder}'")
                    logger.info(f"     databaseField='{database_field}'")
                    logger.info(f"     vessel_imo='{vessel_imo}' (from page)")
                    
                    # Vessel data is already fetched and vessel['imo'] is already set
                    logger.info(f"  📋 Available vessel fields: {list(vessel.keys())}")
                    
                    matched_field = None
                    matched_value = None
                    
                    # Strategy 1: If databaseField is explicitly set, use it
                    if database_field:
                        # Try exact match first
                        if database_field in vessel:
                            value = vessel[database_field]
                            if value is not None and str(value).strip() != '':
                                matched_field = database_field
                                matched_value = str(value).strip()
                                logger.info(f"  ✅ Exact match found: '{database_field}'")
                        else:
                            # Try case-insensitive matching
                            database_field_lower = database_field.lower()
                            for key, value in vessel.items():
                                if key.lower() == database_field_lower:
                                    if value is not None and str(value).strip() != '':
                                        matched_field = key
                                        matched_value = str(value).strip()
                                        logger.info(f"  ✅ Case-insensitive match: '{database_field}' -> '{key}'")
                    break
            
                    # Strategy 2: If no explicit match and databaseField is empty, try intelligent matching
                    if not matched_field and not database_field:
                        logger.info(f"  🔍 databaseField is empty, trying intelligent matching for '{placeholder}'...")
                        matched_field, matched_value = _intelligent_field_match(placeholder, vessel)
                        if matched_field:
                            logger.info(f"  ✅ Intelligent match found: '{placeholder}' -> '{matched_field}'")
                    
                    # Strategy 3: If still no match but databaseField was set, try intelligent matching as fallback
                    if not matched_field and database_field:
                        logger.info(f"  🔍 Explicit field '{database_field}' not found, trying intelligent matching...")
                        matched_field, matched_value = _intelligent_field_match(placeholder, vessel)
                        if matched_field:
                            logger.info(f"  ✅ Intelligent fallback match: '{placeholder}' -> '{matched_field}'")
                    
                    # Use the matched value if found
                    if matched_field and matched_value:
                        data_mapping[placeholder] = matched_value
                        found = True
                        logger.info(f"  ✅✅✅ SUCCESS: {placeholder} = '{matched_value}'")
                        logger.info(f"     ✓ Used database field '{matched_field}' from vessel IMO {vessel_imo}")
                    else:
                        logger.error(f"  ❌❌❌ FAILED: Could not match '{placeholder}' to any vessel field!")
                        if database_field:
                            logger.error(f"  ❌ Explicit field '{database_field}' not found in vessel data")
                        logger.error(f"  ❌ Available fields: {list(vessel.keys())}")
                        logger.error(f"  ❌ This will use RANDOM data!")
                elif source == 'csv':
                    # Use CSV data if explicitly configured in CMS
                    csv_id = setting.get('csvId', '')
                    csv_field = setting.get('csvField', '')
                    csv_row = setting.get('csvRow', 0)
                    
                    if csv_id and csv_field:
                        csv_data = get_csv_data(csv_id, csv_row)
                        if csv_data and csv_field in csv_data and csv_data[csv_field]:
                            data_mapping[placeholder] = str(csv_data[csv_field])
                            found = True
                            logger.info(f"{placeholder} -> {csv_data[csv_field]} (CMS configured CSV: {csv_id}[{csv_row}].{csv_field})")
                    else:
                        logger.warning(f"{placeholder}: CSV source selected but csvId or csvField missing in CMS")
            
            # Priority 2: Generate random data if not found or not configured in CMS
            # NOTE: We do NOT automatically match vessel data - only if CMS explicitly configures it
            if not found:
                # Check random option from settings if placeholder was configured, otherwise use default
                if placeholder in template_settings:
                    setting = template_settings[placeholder]
                    random_option = setting.get('randomOption', 'auto')
                    source = setting.get('source', 'random')
                    logger.warning(f"  ⚠⚠⚠ {placeholder}: Using RANDOM data (source in CMS: '{source}', found: {found})")
                else:
                    random_option = 'auto'  # Default for non-configured placeholders
                    logger.info(f"  {placeholder}: Not configured in CMS, using random data (mode: {random_option})")
                
                seed_imo = None if random_option == 'fixed' else vessel_imo
                data_mapping[placeholder] = generate_realistic_random_data(placeholder, seed_imo)
                logger.info(f"  {placeholder} -> '{data_mapping[placeholder]}' (RANDOM data, mode: {random_option}, vessel IMO: {vessel_imo})")
            else:
                logger.info(f"  ✓ {placeholder}: Successfully filled with configured data source")
        
        logger.info(f"Generated data mapping for {len(data_mapping)} placeholders")
        
        # Replace placeholders
        processed_docx = replace_placeholders_in_docx(template_path, data_mapping)
        
        # Convert to PDF
        pdf_path = convert_docx_to_pdf(processed_docx)
        
        # Read file content
        if pdf_path.endswith('.pdf'):
            with open(pdf_path, 'rb') as f:
                file_content = f.read()
            media_type = "application/pdf"
            filename = f"generated_{template_name.replace('.docx', '')}_{vessel_imo}.pdf"
        else:
            with open(processed_docx, 'rb') as f:
                file_content = f.read()
            media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            filename = f"generated_{template_name.replace('.docx', '')}_{vessel_imo}.docx"
        
        # Track download if user_id is provided and Supabase is available
        if user_id and supabase:
            try:
                template_id = None
                if template_record:
                    template_id = template_record.get('id')
                else:
                    lookup_names = [template_name]
                    if not template_name.endswith('.docx'):
                        lookup_names.append(f"{template_name}.docx")
                    else:
                        lookup_names.append(template_name.replace('.docx', ''))

                    template_res = supabase.table('document_templates').select('id').in_('file_name', lookup_names).eq('is_active', True).limit(1).execute()
                    if template_res.data:
                        template_id = template_res.data[0]['id']

                if template_id:
                    download_record = {
                        'user_id': user_id,
                        'template_id': template_id,
                        'vessel_imo': vessel_imo,
                        'download_type': 'pdf' if pdf_path.endswith('.pdf') else 'docx',
                        'file_size': len(file_content)
                    }
                    supabase.table('user_document_downloads').insert(download_record).execute()
                    logger.info(f"Recorded download for user {user_id}, template {template_id}")
            except Exception as e:
                logger.warning(f"Failed to record download: {e}")
        
        # Clean up temp files
        try:
            if os.path.exists(processed_docx):
                os.remove(processed_docx)
            if pdf_path.endswith('.pdf') and pdf_path != processed_docx and os.path.exists(pdf_path):
                os.remove(pdf_path)
            if template_temp_path and os.path.exists(template_temp_path):
                os.remove(template_temp_path)
        except Exception as cleanup_error:
            logger.debug(f"Cleanup warning: {cleanup_error}")
        
        # Return file
        return Response(
            content=file_content,
            media_type=media_type,
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating document: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if template_temp_path and os.path.exists(template_temp_path):
            try:
                os.remove(template_temp_path)
            except Exception as cleanup_error:
                logger.debug(f"Template temp cleanup warning: {cleanup_error}")

@app.options("/process-document")
async def options_process_document(request: Request):
    """Handle CORS preflight for legacy process-document endpoint"""
    return Response(status_code=200, headers=_cors_preflight_headers(request, "POST, OPTIONS"))

@app.post("/process-document")
async def process_document_legacy(request: Request):
    """Legacy route that proxies to generate-document for backward compatibility"""
    return await generate_document(request)

# ============================================================================
# STARTUP
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting Document Processing API v2.0...")
    logger.info(f"Templates directory: {TEMPLATES_DIR}")
    logger.info(f"Storage directory: {STORAGE_DIR}")
    uvicorn.run(app, host="0.0.0.0", port=8000)

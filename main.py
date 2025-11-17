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
from typing import List, Dict, Optional, Tuple
from fastapi import FastAPI, HTTPException, File, UploadFile, Form, Request, Depends, Body
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
PLACEHOLDER_SETTINGS_PATH = os.path.join(
    STORAGE_DIR, 'placeholder_settings.json')
PLANS_PATH = os.path.join(STORAGE_DIR, 'plans.json')
USERS_PATH = os.path.join(STORAGE_DIR, 'users.json')
TEMPLATE_METADATA_PATH = os.path.join(STORAGE_DIR, 'template_metadata.json')
DELETED_TEMPLATES_PATH = os.path.join(STORAGE_DIR, 'deleted_templates.json')
DATA_SOURCES_METADATA_PATH = os.path.join(STORAGE_DIR, 'data_sources.json')

# Supabase client
SUPABASE_URL = os.getenv(
    "SUPABASE_URL", "https://ozjhdxvwqbzcvcywhwjg.supabase.co")
SUPABASE_KEY = os.getenv(
    "SUPABASE_KEY",
     "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im96amhkeHZ3cWJ6Y3ZjeXdod2pnIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTU5MDAyNzUsImV4cCI6MjA3MTQ3NjI3NX0.KLAo1KIRR9ofapXPHenoi-ega0PJtkNhGnDHGtniA-Q")

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
            logger.error(
                f"Failed to resolve template by ID '{template_name}': {exc}")

    name_with_ext = template_name if template_name.endswith(
        '.docx') else f"{template_name}.docx"
    name_without_ext = template_name[:-
        5] if template_name.endswith('.docx') else template_name

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


def fetch_template_placeholders(template_id: str,
    template_hint: Optional[str] = None) -> Dict[str,
    Dict[str,
     Optional[str]]]:
    """Fetch placeholder configuration for a template"""
    disk_settings = read_json_file(PLACEHOLDER_SETTINGS_PATH, {})

    if not SUPABASE_ENABLED:
        return _lookup_placeholder_settings_from_disk(
            disk_settings, template_id, template_hint)

    try:
        response = supabase.table('template_placeholders').select(
            'placeholder, source, custom_value, database_field, csv_id, csv_field, csv_row, random_option'
        ).eq('template_id', template_id).execute()
        settings: Dict[str, Dict[str, Optional[str]]] = {}
        for row in response.data or []:
            placeholder_key = row.get('placeholder', '')
            if not placeholder_key:
                continue
                
            settings[placeholder_key] = {
                'source': row.get('source', 'random'),
                'customValue': str(row.get('custom_value') or '').strip(),
                'databaseField': str(row.get('database_field') or '').strip(),
                'csvId': str(row.get('csv_id') or '').strip(),
                'csvField': str(row.get('csv_field') or '').strip(),
                'csvRow': int(row['csv_row']) if row.get('csv_row') is not None else 0,
                'randomOption': row.get('random_option', 'auto') or 'auto'
            }
            logger.debug(f"Loaded placeholder setting for '{placeholder_key}': source={settings[placeholder_key]['source']}, databaseField={settings[placeholder_key]['databaseField']}, csvId={settings[placeholder_key]['csvId']}")
        
        if settings:
            logger.info(f"Loaded {len(settings)} placeholder settings from Supabase for template {template_id}")
            return settings
        else:
            logger.warning(f"No placeholder settings found in Supabase for template {template_id}, falling back to disk")
    except Exception as exc:
        logger.error(
            f"Failed to fetch template placeholders for {template_id}: {exc}")
    return _lookup_placeholder_settings_from_disk(
        disk_settings, template_id, template_hint)


def _lookup_placeholder_settings_from_disk(
    disk_settings: Dict[str, Dict], template_id: str, template_hint: Optional[str]) -> Dict[str, Dict[str, Optional[str]]]:
    """Internal helper to find placeholder config from disk storage."""
    candidates = []
    if template_hint:
        candidates.extend([
            template_hint,
            ensure_docx_filename(template_hint),
            normalise_template_key(template_hint),
        ])
    if template_id:
        candidates.append(str(template_id))

    for candidate in candidates:
        if not candidate:
            continue
        if candidate in disk_settings:
            return disk_settings[candidate]
        if ensure_docx_filename(candidate) in disk_settings:
            return disk_settings[ensure_docx_filename(candidate)]
        normalised = normalise_template_key(candidate)
        for key in disk_settings.keys():
            if normalise_template_key(key) == normalised:
                return disk_settings[key]
    return {}


def upsert_template_placeholders(template_id: str,
    settings: Dict[str,
    Dict],
     template_hint: Optional[str] = None) -> None:
    """Upsert placeholder settings into Supabase"""
    if SUPABASE_ENABLED and settings:
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
            response = supabase.table('template_placeholders').upsert(
                rows, on_conflict='template_id,placeholder').execute()
            if getattr(response, "error", None):
                logger.error(
                    f"Supabase error upserting placeholders for {template_id}: {response.error}")
            else:
                logger.info(f"Successfully saved {len(rows)} placeholder settings to Supabase for template {template_id}")
                for row in rows:
                    logger.debug(f"  Saved: {row['placeholder']} -> source={row['source']}, database_field={row.get('database_field')}, csv_id={row.get('csv_id')}")
        except Exception as exc:
            logger.error(f"Failed to upsert placeholder settings: {exc}")

    # Persist to disk as reliable fallback
    placeholder_key = ensure_docx_filename(
        template_hint) if template_hint else str(template_id)
    placeholder_settings = read_json_file(PLACEHOLDER_SETTINGS_PATH, {})
    placeholder_settings[placeholder_key] = settings
    write_json_atomic(PLACEHOLDER_SETTINGS_PATH, placeholder_settings)


def fetch_template_file_record(template_id: str,
     include_data: bool = False) -> Optional[Dict]:
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
        raise HTTPException(
            status_code=500, detail="Template file data is empty")

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.docx')
    tmp.write(doc_bytes)
    tmp.flush()
    tmp.close()
    return tmp.name

# ============================================================================
# STEP 1: STORAGE HELPERS (JSON on disk with atomic writes)
# ============================================================================


def get_deleted_templates() -> set:
    """Get set of deleted template names"""
    try:
        # Ensure file exists
        if not os.path.exists(DELETED_TEMPLATES_PATH):
            os.makedirs(os.path.dirname(DELETED_TEMPLATES_PATH), exist_ok=True)
            initial_data = {"deleted_templates": [], "last_updated": ""}
            write_json_atomic(DELETED_TEMPLATES_PATH, initial_data)
            logger.info(f"Created deleted_templates.json file at {DELETED_TEMPLATES_PATH}")
            return set()
        
        deleted_data = read_json_file(DELETED_TEMPLATES_PATH, {})
        deleted_names = deleted_data.get('deleted_templates', [])
        
        if not deleted_names:
            logger.debug(f"deleted_templates.json is empty or has no deleted_templates key")
            return set()
        
        # Normalize all names to ensure consistency
        normalized_names = set()
        for name in deleted_names:
            if not name:
                continue
            normalized = ensure_docx_filename(str(name))
            normalized_names.add(normalized)
            logger.debug(f"Loaded deleted template: {name} -> {normalized}")
        
        logger.info(f"Loaded {len(normalized_names)} deleted templates from {DELETED_TEMPLATES_PATH}")
        return normalized_names
    except Exception as e:
        logger.error(f"Could not read deleted templates from {DELETED_TEMPLATES_PATH}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return set()

def mark_template_as_deleted(template_name: str) -> None:
    """Mark a template as deleted in the deleted templates file"""
    if not template_name:
        return
        
    try:
        # Ensure file exists
        if not os.path.exists(DELETED_TEMPLATES_PATH):
            os.makedirs(os.path.dirname(DELETED_TEMPLATES_PATH), exist_ok=True)
        
        deleted_data = read_json_file(DELETED_TEMPLATES_PATH, {})
        deleted_list = deleted_data.get('deleted_templates', [])
        normalized_name = ensure_docx_filename(template_name)
        
        # Normalize existing names for comparison
        normalized_existing = {ensure_docx_filename(str(name)) for name in deleted_list if name}
        
        # Add to list if not already there
        if normalized_name and normalized_name not in normalized_existing:
            deleted_list.append(normalized_name)
            deleted_data['deleted_templates'] = deleted_list
            deleted_data['last_updated'] = datetime.now().isoformat()
            write_json_atomic(DELETED_TEMPLATES_PATH, deleted_data)
            logger.info(f"Marked template as deleted in deleted_templates.json: {normalized_name} (from original: {template_name})")
        elif normalized_name in normalized_existing:
            logger.debug(f"Template {normalized_name} already marked as deleted (from original: {template_name})")
    except Exception as e:
        logger.error(f"Failed to mark template as deleted: {e}")
        import traceback
        logger.error(traceback.format_exc())

def unmark_template_as_deleted(template_name: str) -> None:
    """Remove a template from the deleted templates file (when re-uploaded)"""
    if not template_name:
        return
        
    try:
        if not os.path.exists(DELETED_TEMPLATES_PATH):
            return  # Nothing to remove if file doesn't exist
        
        deleted_data = read_json_file(DELETED_TEMPLATES_PATH, {})
        deleted_list = deleted_data.get('deleted_templates', [])
        normalized_name = ensure_docx_filename(template_name)
        
        # Remove all variations of the template name (case-insensitive)
        original_count = len(deleted_list)
        deleted_list = [
            name for name in deleted_list 
            if name and ensure_docx_filename(str(name)).lower() != normalized_name.lower()
        ]
        
        # If we removed anything, save the updated list
        if len(deleted_list) != original_count:
            deleted_data['deleted_templates'] = deleted_list
            deleted_data['last_updated'] = datetime.now().isoformat()
            write_json_atomic(DELETED_TEMPLATES_PATH, deleted_data)
            logger.info(f"Unmarked template from deleted_templates.json: {normalized_name} (from original: {template_name}) - removed {original_count - len(deleted_list)} entry/entries")
    except Exception as e:
        logger.error(f"Failed to unmark template as deleted: {e}")
        import traceback
        logger.error(traceback.format_exc())

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

    if not os.path.exists(TEMPLATE_METADATA_PATH):
        write_json_atomic(TEMPLATE_METADATA_PATH, {})

    if not os.path.exists(DATA_SOURCES_METADATA_PATH):
        write_json_atomic(DATA_SOURCES_METADATA_PATH, {})


# Initialize storage on startup
ensure_storage()

# Metadata helpers


def load_template_metadata() -> Dict[str, Dict]:
    """Load template metadata JSON with safe fallback."""
    metadata = read_json_file(TEMPLATE_METADATA_PATH, {})
    return metadata if isinstance(metadata, dict) else {}


def save_template_metadata(metadata: Dict[str, Dict]) -> None:
    """Persist template metadata to disk."""
    write_json_atomic(TEMPLATE_METADATA_PATH, metadata)


def update_template_metadata_entry(
    template_key: str, updates: Dict) -> Dict[str, Dict]:
    """Merge updates into template metadata entry and persist."""
    metadata = load_template_metadata()
    entry = metadata.get(template_key, {})
    entry.update({k: v for k, v in updates.items() if v is not None})
    metadata[template_key] = entry
    save_template_metadata(metadata)
    return metadata


def load_data_sources_metadata() -> Dict[str, Dict]:
    metadata = read_json_file(DATA_SOURCES_METADATA_PATH, {})
    return metadata if isinstance(metadata, dict) else {}


def save_data_sources_metadata(metadata: Dict[str, Dict]) -> None:
    write_json_atomic(DATA_SOURCES_METADATA_PATH, metadata)


def upsert_data_source_metadata(dataset_id: str, display_name: Optional[str] = None) -> None:
    metadata = load_data_sources_metadata()
    entry = metadata.get(dataset_id, {})
    if display_name:
        entry['display_name'] = display_name
    entry['updated_at'] = datetime.utcnow().isoformat()
    metadata[dataset_id] = entry
    save_data_sources_metadata(metadata)


def remove_data_source_metadata(dataset_id: str) -> None:
    metadata = load_data_sources_metadata()
    if dataset_id in metadata:
        metadata.pop(dataset_id, None)
        save_data_sources_metadata(metadata)


def normalise_dataset_id(value: Optional[str]) -> str:
    if not value:
        return ""
    cleaned = value.strip().lower()
    cleaned = re.sub(r'[^a-z0-9]+', '_', cleaned)
    cleaned = re.sub(r'_+', '_', cleaned).strip('_')
    if not cleaned:
        return ""
    return cleaned[:80]


def dataset_id_to_filename(dataset_id: str) -> str:
    return f"{dataset_id}.csv"


def list_csv_datasets() -> List[Dict[str, str]]:
    datasets: List[Dict[str, str]] = []
    if not os.path.exists(DATA_DIR):
        return datasets
    metadata = load_data_sources_metadata()
    for entry in os.listdir(DATA_DIR):
        if not entry.lower().endswith('.csv'):
            continue
        dataset_id = entry[:-4]
        file_path = os.path.join(DATA_DIR, entry)
        datasets.append({
            "id": dataset_id,
            "filename": entry,
            "path": file_path,
            "display_name": metadata.get(dataset_id, {}).get('display_name')
        })
    return datasets


def normalise_template_key(value: Optional[str]) -> str:
    """Normalise template identifiers to a consistent filesystem key."""
    if not value:
        return ""
    name = value.strip()
    name = os.path.basename(name)
    if name.lower().endswith('.docx'):
        name = name[:-5]
    return name.strip().lower()


def ensure_docx_filename(value: str) -> str:
    """Ensure filename ends with .docx"""
    if not value:
        return value
    return value if value.lower().endswith('.docx') else f"{value}.docx"


# ============================================================================
# STEP 2: AUTHENTICATION (Simple login with HttpOnly cookies)
# ============================================================================

def get_current_user(request: Request):
    """Dependency to check if user is authenticated"""
    token = request.cookies.get('session')
    if not token:
        logger.warning(
            f"Auth failed: No session cookie. Available cookies: {list(request.cookies.keys())}")
        raise HTTPException(
            status_code=401, detail="Not authenticated - Please login")

    users_data = read_json_file(USERS_PATH, {"users": [], "sessions": {}})
    username = users_data.get("sessions", {}).get(token)
    if not username:
        logger.warning(
            f"Auth failed: Invalid token {token[:10]}... Sessions: {len(users_data.get('sessions', {}))}")
        raise HTTPException(
            status_code=401, detail="Invalid session - Please login again")

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
        if not users_data.get("users"):
            raise HTTPException(status_code=403, detail="No administrators defined. Please create a user in storage/users.json")
        pwd_hash = hashlib.sha256(password.encode()).hexdigest()

        user_found = any(
            u.get('username') == username and u.get(
                'password_hash') == pwd_hash
            for u in users_data.get('users', [])
        )

        if not user_found:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        # Create session token
        token = uuid.uuid4().hex
        users_data['sessions'][token] = username
        write_json_atomic(USERS_PATH, users_data)

        # Set HttpOnly cookie with SameSite=None and Secure for cross-origin,
        # or Lax for same-site
        response = Response(content=json.dumps(
            {"success": True, "user": username}), media_type="application/json")
        # Use SameSite='None' and Secure=True if running on different ports,
        # but check origin first
        origin = request.headers.get('origin', '')
        if origin and origin.startswith(
            'http://127.0.0.1') or origin.startswith('http://localhost'):
            # Same-site cookies work with Lax for same-origin requests
            response.set_cookie(key='session', value=token,
                                httponly=True, samesite='Lax', max_age=86400)
        else:
            # For true cross-origin, use None with Secure (requires HTTPS)
            response.set_cookie(key='session', value=token,
                                httponly=True, samesite='Lax', max_age=86400)
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
            users_data = read_json_file(
                USERS_PATH, {"users": [], "sessions": {}})
            users_data.get("sessions", {}).pop(token, None)
            write_json_atomic(USERS_PATH, users_data)

        response = Response(content=json.dumps(
            {"success": True}), media_type="application/json")
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
                    {"id": 1, "imo": "IMO1234567", "name": "Test Vessel 1",
                        "vessel_type": "Tanker", "flag": "Panama"},
                    {"id": 2, "imo": "IMO9876543", "name": "Test Vessel 2",
                        "vessel_type": "Cargo", "flag": "Singapore"}
                ],
                "count": 2
            }

        response = supabase.table('vessels').select(
            'id, name, imo, vessel_type, flag').limit(50).execute()
        return {
            "success": True,
            "vessels": response.data or [],
            "count": len(response.data) if response.data else 0
        }
    except Exception as e:
        logger.error(f"Error fetching vessels: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch vessels: {str(e)}")


@app.get("/vessel/{imo}")
async def get_vessel(imo: str):
    """Get vessel by IMO"""
    try:
        if not supabase:
            raise HTTPException(
                status_code=503, detail="Supabase not available")

        response = supabase.table('vessels').select(
            '*').eq('imo', imo).execute()
        if not response.data or len(response.data) == 0:
            raise HTTPException(
                status_code=404, detail=f"Vessel with IMO {imo} not found")

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
    """
    Extract placeholders from text using multiple formats.
    Only extracts COMPLETE placeholders (with both opening and closing brackets).
    """
    patterns = [
        (r'\{\{([^}]+)\}\}', '{{}}'),      # {{placeholder}}
        (r'\{([^}]+)\}', '{}'),            # {placeholder} - MOST COMMON
        (r'\[\[([^\]]+)\]\]', '[[]]'),     # [[placeholder]]
        (r'\[([^\]]+)\]', '[]'),           # [placeholder]
        (r'%([^%]+)%', '%%'),              # %placeholder%
        (r'<([^>]+)>', '<>'),              # <placeholder>
        (r'__([^_]+)__', '__'),            # __placeholder__
        (r'##([^#]+)##', '##'),            # ##placeholder##
    ]

    placeholders = set()
    for pattern, wrapper_type in patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            # Clean up match - replace newlines with spaces, remove extra whitespace
            cleaned = match.strip().replace('\n', ' ').replace('\r', ' ')
            cleaned = ' '.join(cleaned.split())  # Remove extra spaces
            
            # Only add if placeholder is not empty and doesn't contain unclosed brackets
            if cleaned and not any(char in cleaned for char in ['{', '}', '[', ']', '<', '>']):
                placeholders.add(cleaned)
                logger.debug(f"Found placeholder: '{cleaned}' (format: {wrapper_type})")

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


def normalise_placeholder_key(value: Optional[str]) -> str:
    """Normalise placeholder identifiers for matching (case and punctuation insensitive)."""
    if not value:
        return ""
    # Lowercase, replace whitespace with underscore, then strip
    # non-alphanumeric/underscore
    cleaned = value.strip().lower()
    cleaned = re.sub(r'\s+', '_', cleaned)
    cleaned = re.sub(r'[^a-z0-9_]', '', cleaned)
    return cleaned


def resolve_placeholder_setting(
    template_settings: Dict[str, Dict], placeholder: str) -> Tuple[Optional[str], Optional[Dict]]:
    """
    Resolve a placeholder setting using multiple normalisation strategies.
    Returns the matched key and the setting dict.
    """
    if not template_settings or not placeholder:
        return None, None

    # Direct match
    if placeholder in template_settings:
        return placeholder, template_settings[placeholder]

    # Common variants
    variants = [
        placeholder.lower(),
        placeholder.replace(' ', '_'),
        placeholder.replace(' ', '_').lower(),
    ]

    for variant in variants:
        if variant in template_settings:
            return variant, template_settings[variant]

    # Normalised comparison
    target_norm = normalise_placeholder_key(placeholder)
    for key, value in template_settings.items():
        if normalise_placeholder_key(key) == target_norm:
            return key, value

    return None, None

# ============================================================================
# STEP 4: TEMPLATES API (upload, list, get, delete)
# ============================================================================


def _cors_preflight_headers(
    request: Request, allowed_methods: str) -> Dict[str, str]:
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
    return Response(
    status_code=200,
    headers=_cors_preflight_headers(
        request,
         "GET, POST, OPTIONS"))


@app.get("/templates")
async def get_templates(request: Request):
    """List all available templates with placeholders"""
    # Try to get current user, but don't require authentication
    current_user = None
    try:
        current_user = get_current_user(request)
    except HTTPException:
        # Allow unauthenticated access for public template listing
        pass
    try:
        templates = []
        templates_by_key: Dict[str, Dict] = {}
        metadata_map = load_template_metadata()

        # FIRST: Get deleted templates list BEFORE loading from Supabase or filesystem
        # This ensures we don't add deleted templates back
        deleted_template_names = set()  # Track templates that were soft-deleted in Supabase
        deleted_template_names_lower = set()  # Case-insensitive lookup
        
        # Get hard-deleted templates from deleted_templates.json (for hard delete support)
        hard_deleted_templates = get_deleted_templates()
        deleted_template_names.update(hard_deleted_templates)
        deleted_template_names_lower.update({name.lower() for name in hard_deleted_templates})
        if hard_deleted_templates:
            logger.info(f"Loaded {len(hard_deleted_templates)} deleted templates from deleted_templates.json: {list(hard_deleted_templates)[:5]}")
        else:
            logger.debug(f"No deleted templates found in deleted_templates.json")
        
        if SUPABASE_ENABLED:
            try:
                # Also check for soft-deleted templates in Supabase (for backward compatibility)
                soft_deleted_templates = supabase.table('document_templates').select('file_name').eq('is_active', False).execute()
                if soft_deleted_templates.data:
                    soft_deleted_names = {ensure_docx_filename(t.get('file_name', '')) for t in soft_deleted_templates.data if t.get('file_name')}
                    deleted_template_names.update(soft_deleted_names)
                    deleted_template_names_lower.update({name.lower() for name in soft_deleted_names})
                    logger.info(f"Loaded {len(soft_deleted_names)} soft-deleted templates from Supabase")
            except Exception as exc:
                logger.warning(f"Could not check deleted templates from Supabase: {exc}")

        # Load templates from Supabase (only active templates)
        if SUPABASE_ENABLED:
            try:
                db_templates = supabase.table('document_templates').select(
                    'id, title, description, file_name, placeholders, is_active, created_at'
                ).eq('is_active', True).execute()

                for record in db_templates.data or []:
                    template_id = record.get('id')
                    placeholders = record.get('placeholders') or []

                    file_meta = fetch_template_file_record(template_id)
                    size = file_meta.get('file_size') if file_meta else None
                    created_at = (file_meta or {}).get(
                        'uploaded_at') or record.get('created_at')

                    # Normalise names for the frontend
                    file_name = ensure_docx_filename(record.get(
                        'file_name') or record.get('title') or 'template')

                    # Skip if this template is marked as deleted
                    file_name_lower = file_name.lower()
                    if file_name in deleted_template_names or file_name_lower in deleted_template_names_lower:
                        logger.info(f"Skipping deleted template from Supabase: {file_name}")
                        continue

                    # If size is not available from Supabase, try to get it from local file
                    if not size or size == 0:
                        local_file_path = os.path.join(TEMPLATES_DIR, file_name)
                        if os.path.exists(local_file_path):
                            try:
                                size = os.path.getsize(local_file_path)
                                logger.debug(f"Got file size from local file for {file_name}: {size} bytes")
                            except OSError:
                                size = 0
                                logger.warning(f"Could not get file size from local file for {file_name}")
                        else:
                            size = 0
                            logger.warning(f"File size not available for {file_name} (not in Supabase file_record and local file doesn't exist)")

                    # Get display_name from metadata first, then Supabase title, then fallback
                    metadata_entry = metadata_map.get(file_name, {})
                    display_name = (
                        metadata_entry.get('display_name') or 
                        record.get('title') or 
                        file_name.replace('.docx', '')
                    )
                    
                    # Update Supabase title if metadata has a different display_name
                    if metadata_entry.get('display_name') and metadata_entry.get('display_name') != record.get('title'):
                        try:
                            supabase.table('document_templates').update({'title': metadata_entry.get('display_name')}).eq('id', template_id).execute()
                            logger.debug(f"Synced display_name from metadata to Supabase for {file_name}")
                        except Exception as sync_exc:
                            logger.warning(f"Could not sync display_name to Supabase: {sync_exc}")

                    template_payload = {
                        "id": str(template_id),
                        "name": file_name,
                        "title": display_name,
                        "file_name": file_name.replace('.docx', ''),
                        "file_with_extension": file_name,
                        "description": metadata_entry.get('description') or record.get('description') or '',
                        "metadata": {
                            "display_name": display_name,  # Use the resolved display_name
                            "description": metadata_entry.get('description') or record.get('description') or '',
                            "font_family": metadata_entry.get('font_family'),
                            "font_size": metadata_entry.get('font_size')
                        },
                        "size": size or 0,
                        "created_at": created_at,
                        "placeholders": placeholders,
                        "placeholder_count": len(placeholders),
                        "is_active": record.get('is_active', True)
                    }
                    templates.append(template_payload)
                    templates_by_key[file_name] = template_payload
            except Exception as exc:
                logger.error(f"Failed to load templates from Supabase: {exc}")

        # Include local filesystem templates as fallback / supplement
        # But only if they don't exist in Supabase AND are not marked as deleted
        
        for filename in os.listdir(TEMPLATES_DIR):
            if not filename.lower().endswith('.docx'):
                continue
        
            file_name = ensure_docx_filename(filename)
            
            # Skip if already loaded from Supabase
            if file_name in templates_by_key:
                logger.debug(f"Template {file_name} already loaded from Supabase, skipping local file")
                continue
            
            # Skip templates that were deleted (hard delete or soft delete)
            # Check both exact match and case-insensitive match
            file_name_lower = file_name.lower()
            filename_lower = filename.lower()
            
            # Check multiple variations
            is_deleted = (
                file_name in deleted_template_names or 
                file_name_lower in deleted_template_names_lower or
                filename in deleted_template_names or
                filename_lower in deleted_template_names_lower
            )
            
            # Also check without .docx extension
            file_name_no_ext = file_name.replace('.docx', '').replace('.DOCX', '')
            filename_no_ext = filename.replace('.docx', '').replace('.DOCX', '')
            if not is_deleted:
                for deleted_name in deleted_template_names:
                    deleted_no_ext = deleted_name.replace('.docx', '').replace('.DOCX', '')
                    if (file_name_no_ext.lower() == deleted_no_ext.lower() or 
                        filename_no_ext.lower() == deleted_no_ext.lower()):
                        is_deleted = True
                        logger.debug(f"Matched deleted template by name without extension: {file_name} matches {deleted_name}")
                        break
            
            if is_deleted:
                logger.info(f"Skipping deleted template (from deleted_templates.json or Supabase): {file_name} (original: {filename})")
                # Delete the local file if it's marked as deleted
                file_path_to_delete = os.path.join(TEMPLATES_DIR, file_name)
                # Also check original filename
                original_file_path = os.path.join(TEMPLATES_DIR, filename)
                
                for path_to_check in [file_path_to_delete, original_file_path]:
                    if os.path.exists(path_to_check):
                        try:
                            os.remove(path_to_check)
                            logger.info(f"Removed orphaned local file for deleted template: {path_to_check}")
                        except Exception as delete_exc:
                            logger.warning(f"Could not remove orphaned local file {path_to_check}: {delete_exc}")
                continue

            file_path = os.path.join(TEMPLATES_DIR, file_name)
            try:
                file_size = os.path.getsize(file_path)
            except OSError:
                file_size = 0
            created_at = datetime.fromtimestamp(
                os.path.getctime(file_path)).isoformat()
            placeholders = extract_placeholders_from_docx(file_path)
            metadata_entry = metadata_map.get(file_name, {})

            template_id = hashlib.md5(file_name.encode()).hexdigest()[:12]
            template_payload = {
                "id": template_id,
                "name": file_name,
                "title": metadata_entry.get('display_name') or file_name.replace('.docx', ''),
                "file_name": file_name.replace('.docx', ''),
                "file_with_extension": file_name,
                "description": metadata_entry.get('description') or f"Template: {file_name.replace('.docx', '')}",
                "metadata": {
                    "display_name": metadata_entry.get('display_name') or file_name.replace('.docx', ''),
                    "description": metadata_entry.get('description'),
                    "font_family": metadata_entry.get('font_family'),
                    "font_size": metadata_entry.get('font_size')
                },
                "size": file_size,
                "created_at": created_at,
                "placeholders": placeholders,
                "placeholder_count": len(placeholders),
                "is_active": True
            }
            templates.append(template_payload)
            templates_by_key[file_name] = template_payload

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
            plans_res = supabase.table('subscription_plans').select(
                '*').eq('is_active', True).order('sort_order').execute()

            if not plans_res.data:
                # Fallback to JSON if no database plans
                plans = read_json_file(PLANS_PATH, {})
                return {
    "success": True,
    "plans": plans,
     "source": "json_fallback"}

            # Get all templates (may not exist yet, so handle gracefully)
            template_map = {}
            try:
                templates_res = supabase.table('document_templates').select(
                    'id, file_name, title').eq('is_active', True).execute()
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
                    permissions_res = supabase.table('plan_template_permissions').select(
                        'template_id, can_download').eq('plan_id', plan['id']).execute()

                    if permissions_res.data:
                        for perm in permissions_res.data:
                            if perm['can_download']:
                                template_id = perm['template_id']
                                template_info = template_map.get(template_id)
                                if template_info:
                                    allowed_templates.append(
                                        template_info.get('file_name', ''))
                except Exception as e:
                    logger.warning(
                        f"Could not fetch permissions for plan {plan_tier}: {e}")
                    # Default to all templates if permissions table doesn't
                    # exist
                    allowed_templates = ['*']

                # If no permissions set, default to all templates
                if not allowed_templates:
                    allowed_templates = ['*']

                # Normalize template names (remove .docx if present)
                normalized_templates = []
                if allowed_templates:
                    for t in allowed_templates:
                        if t == '*':
                            normalized_templates.append('*')
                        elif isinstance(t, str):
                            normalized_templates.append(
                                ensure_docx_filename(t))
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
async def get_template(template_name: str, current_user: str = Depends(get_current_user)):
    """Get details for a specific template"""
    try:
        metadata_map = load_template_metadata()
        docx_name = ensure_docx_filename(template_name)

        if SUPABASE_ENABLED:
            template_record = resolve_template_record(template_name)
            if template_record:
                docx_name = ensure_docx_filename(template_record.get('file_name') or template_name)
                placeholders = template_record.get('placeholders') or []
                placeholder_settings = fetch_template_placeholders(template_record['id'], docx_name)
                file_meta = fetch_template_file_record(template_record['id']) or {}
                metadata_entry = metadata_map.get(docx_name, {})

                response = {
                    "id": str(template_record['id']),
                    "name": docx_name,
                    "title": metadata_entry.get('display_name') or template_record.get('title') or docx_name.replace('.docx', ''),
                    "file_name": docx_name.replace('.docx', ''),
                    "file_with_extension": docx_name,
                    "size": file_meta.get('file_size', 0),
                    "created_at": file_meta.get('uploaded_at') or template_record.get('created_at'),
                    "placeholders": placeholders,
                    "placeholder_count": len(placeholders),
                    "settings": placeholder_settings,
                    "metadata": {
                        "display_name": metadata_entry.get('display_name') or template_record.get('title'),
                        "description": metadata_entry.get('description') or template_record.get('description'),
                        "font_family": metadata_entry.get('font_family'),
                        "font_size": metadata_entry.get('font_size')
                    }
                }
                return response

        # Filesystem fallback
        file_path = os.path.join(TEMPLATES_DIR, docx_name)
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="Template not found")

        file_size = os.path.getsize(file_path)
        created_at = datetime.fromtimestamp(os.path.getctime(file_path)).isoformat()
        placeholders = extract_placeholders_from_docx(file_path)
        metadata_entry = metadata_map.get(docx_name, {})
        placeholder_settings = read_json_file(PLACEHOLDER_SETTINGS_PATH, {}).get(docx_name, {})

        return {
            "name": docx_name,
            "title": metadata_entry.get('display_name') or docx_name.replace('.docx', ''),
            "file_name": docx_name.replace('.docx', ''),
            "file_with_extension": docx_name,
            "size": file_size,
            "created_at": created_at,
            "placeholders": placeholders,
            "placeholder_count": len(placeholders),
            "settings": placeholder_settings,
            "metadata": {
                "display_name": metadata_entry.get('display_name') or docx_name.replace('.docx', ''),
                "description": metadata_entry.get('description'),
                "font_family": metadata_entry.get('font_family'),
                "font_size": metadata_entry.get('font_size')
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting template: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/templates/{template_name}/metadata")
async def update_template_metadata(
    template_name: str,
    payload: Dict = Body(...),
    current_user: str = Depends(get_current_user)
):
    """Update template metadata (display name, description, fonts)."""
    try:
        docx_name = ensure_docx_filename(template_name)
        display_name = (payload.get('display_name') or "").strip()
        description = (payload.get('description') or "").strip()
        font_family = (payload.get('font_family') or "").strip() or None
        font_size_raw = payload.get('font_size')
        font_size = None
        if font_size_raw not in (None, ""):
            try:
                font_size = int(font_size_raw)
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="font_size must be an integer")

        # Update Supabase metadata when available
        if SUPABASE_ENABLED:
            template_record = resolve_template_record(docx_name)
            if template_record:
                update_data = {}
                if display_name:
                    update_data['title'] = display_name
                    logger.info(f"Updating Supabase title for {docx_name} to: {display_name}")
                if description:
                    update_data['description'] = description
                    logger.info(f"Updating Supabase description for {docx_name}")
                if update_data:
                    try:
                        result = supabase.table('document_templates').update(update_data).eq('id', template_record['id']).execute()
                        if result.data:
                            logger.info(f"Successfully updated Supabase metadata for {docx_name}: {update_data}")
                        else:
                            logger.warning(f"Supabase update returned no data for {docx_name}")
                    except Exception as exc:
                        logger.error(f"Failed to update template metadata in Supabase: {exc}")
                        import traceback
                        logger.error(traceback.format_exc())

        metadata_updates = {
            "display_name": display_name or None,
            "description": description or None,
            "font_family": font_family,
            "font_size": font_size,
            "updated_at": datetime.utcnow().isoformat()
        }
        update_template_metadata_entry(docx_name, {k: v for k, v in metadata_updates.items() if v is not None})

        return {
            "success": True,
            "template": docx_name,
            "metadata": {
                "display_name": display_name or None,
                "description": description or None,
                "font_family": font_family,
                "font_size": font_size
            }
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Error updating template metadata: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))

@app.post("/upload-template")
async def upload_template(
    file: UploadFile = File(...),
    name: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    font_family: Optional[str] = Form(None),
    font_size: Optional[str] = Form(None),
    current_user: str = Depends(get_current_user)
):
    """Upload a new template"""
    try:
        if not file.filename or not file.filename.lower().endswith('.docx'):
            raise HTTPException(status_code=400, detail="Only .docx files are allowed")
        
        # Read file bytes - ensure we get the full file
        file_bytes = await file.read()
        if not file_bytes or len(file_bytes) == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty or could not be read")
        
        logger.info(f"Received file: {file.filename}, size: {len(file_bytes)} bytes")

        # Write to temp file to extract placeholders
        with tempfile.NamedTemporaryFile(delete=False, suffix='.docx') as tmp:
            tmp.write(file_bytes)
            tmp.flush()  # Ensure data is written to disk
            os.fsync(tmp.fileno())  # Force write to disk
            tmp_path = tmp.name

        # Verify the temp file was written correctly
        if os.path.getsize(tmp_path) == 0:
            os.remove(tmp_path)
            raise HTTPException(status_code=400, detail="File write failed - file is empty")

        placeholders = extract_placeholders_from_docx(tmp_path)
        placeholders = list(dict.fromkeys(placeholders))
        os.remove(tmp_path)

        logger.info(f"Template uploaded: {file.filename} ({len(placeholders)} placeholders)")

        warnings: List[str] = []
        safe_filename = os.path.basename(file.filename)
        docx_filename = ensure_docx_filename(safe_filename)
        inferred_title = docx_filename[:-5]
        title_value = (name or "").strip() or inferred_title
        description_value = (description or "").strip() or f"Template: {title_value}"

        # Persist a local copy as authoritative fallback
        file_path = os.path.join(TEMPLATES_DIR, docx_filename)
        try:
            with open(file_path, 'wb') as f:
                f.write(file_bytes)
                f.flush()  # Ensure data is written
                os.fsync(f.fileno())  # Force write to disk
            
            # Verify the file was written correctly
            written_size = os.path.getsize(file_path)
            if written_size == 0 or written_size != len(file_bytes):
                logger.error(f"File size mismatch: expected {len(file_bytes)}, got {written_size}")
                raise HTTPException(status_code=500, detail=f"File write verification failed: expected {len(file_bytes)} bytes, got {written_size}")
            
            logger.info(f"Template file written successfully: {docx_filename} ({written_size} bytes)")
        except Exception as exc:
            logger.error(f"Failed to write template to disk: {exc}")
            raise HTTPException(status_code=500, detail=f"Failed to write template to disk: {str(exc)}")

        template_id = None
        template_record = None

        if SUPABASE_ENABLED:
            try:
                existing_record = resolve_template_record(docx_filename)
                template_payload = {
                    'title': title_value,
                    'description': description_value,
                    'file_name': docx_filename,
                    'placeholders': placeholders,
                    'is_active': True,
                    'updated_at': datetime.utcnow().isoformat()
                }

                upsert_response = supabase.table('document_templates').upsert(
                    template_payload,
                    on_conflict='file_name',
                    returning='representation'
                ).execute()

                if upsert_response.data:
                    template_record = upsert_response.data[0]
                elif existing_record:
                    template_record = existing_record
                else:
                    template_record = resolve_template_record(docx_filename)

                if template_record:
                    template_id = template_record['id']
                    file_payload = {
                        'template_id': template_id,
                        'filename': docx_filename,
                        'mime_type': file.content_type or 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                        'file_size': len(file_bytes),
                        'file_data': encode_bytea(file_bytes),
                        'sha256': hashlib.sha256(file_bytes).hexdigest(),
                        'uploaded_at': datetime.utcnow().isoformat()
                    }
                    file_response = supabase.table('template_files').upsert(file_payload, on_conflict='template_id').execute()
                    if getattr(file_response, "error", None):
                        warnings.append("Supabase file storage error; using local copy")
                        logger.error(f"Supabase file upsert error: {file_response.error}")

                    existing_settings = fetch_template_placeholders(template_id, template_record.get('file_name'))
                    missing_placeholders = [
                        {
                            'template_id': template_id,
                            'placeholder': placeholder,
                            'source': 'random',
                            'random_option': 'auto'
                        }
                        for placeholder in placeholders
                        if placeholder not in existing_settings
                    ]
                    if missing_placeholders:
                        placeholders_response = supabase.table('template_placeholders').insert(missing_placeholders).execute()
                        if getattr(placeholders_response, "error", None):
                            warnings.append("Supabase placeholder sync error; using local settings")
                            logger.error(f"Supabase placeholder insert error: {placeholders_response.error}")
                else:
                    warnings.append("Supabase metadata sync failed; template served from local storage")
                    logger.warning("Unable to retrieve template metadata after Supabase upsert")
            except Exception as exc:
                warnings.append("Supabase sync failed; template available locally")
                logger.error(f"Failed to store template in Supabase: {exc}")

        # Persist placeholder defaults locally (and optionally to Supabase)
        default_settings: Dict[str, Dict] = {}
        existing_local_settings = fetch_template_placeholders(template_id or docx_filename, docx_filename)
        for placeholder in placeholders:
            default_settings[placeholder] = existing_local_settings.get(placeholder, {
                'source': 'random',
                'customValue': '',
                'databaseField': '',
                'csvId': '',
                'csvField': '',
                'csvRow': 0,
                'randomOption': 'auto'
            })

        upsert_template_placeholders(template_id or docx_filename, default_settings, docx_filename)

        # Remove template from deleted list if it was previously deleted (re-upload scenario)
        unmark_template_as_deleted(docx_filename)
        unmark_template_as_deleted(safe_filename)
        if title_value and title_value != inferred_title:
            unmark_template_as_deleted(title_value)
        logger.info(f"Removed {docx_filename} from deleted templates list (if present)")

        # Persist metadata locally
        font_family_value = (font_family or "").strip() or None
        font_size_value: Optional[int] = None
        if font_size is not None and font_size != "":
            try:
                font_size_value = int(font_size)
            except ValueError:
                warnings.append("Invalid font size value; ignored")

        metadata_payload = {
            "display_name": title_value,
            "description": description_value,
            "font_family": font_family_value,
            "font_size": font_size_value,
            "updated_at": datetime.utcnow().isoformat()
        }
        update_template_metadata_entry(docx_filename, {k: v for k, v in metadata_payload.items() if v is not None})

        response_payload = {
            "success": True,
            "filename": docx_filename,
            "placeholders": placeholders,
            "placeholder_count": len(placeholders),
            "metadata": {
                "display_name": title_value,
                "description": description_value,
                "font_family": font_family_value,
                "font_size": font_size_value
            }
        }
        if template_id:
            response_payload["template_id"] = str(template_id)
        if warnings:
            response_payload["warnings"] = warnings

        return response_payload
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading template: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/templates/{template_name}")
async def delete_template(
    template_name: str,
    current_user: str = Depends(get_current_user)
):
    """Delete a template"""
    try:
        resolved_name = template_name
        warnings: List[str] = []
        template_id = None

        supabase_deleted = False
        if SUPABASE_ENABLED:
            try:
                template_record = resolve_template_record(template_name)
                if template_record:
                    template_id = template_record['id']
                    resolved_name = template_record.get('file_name') or template_name
                    logger.info(f"Found template in Supabase: ID={template_id}, file_name={resolved_name}")

                    try:
                        # Hard delete: Remove from plan permissions first (foreign key constraint)
                        try:
                            perm_result = supabase.table('plan_template_permissions').delete().eq('template_id', template_id).execute()
                            logger.info(f"Deleted plan permissions for template {template_id}: {len(perm_result.data) if perm_result.data else 0} rows")
                        except Exception as perm_exc:
                            logger.warning(f"Could not delete plan permissions: {perm_exc}")
                        
                        # Delete related records
                        try:
                            file_result = supabase.table('template_files').delete().eq('template_id', template_id).execute()
                            logger.info(f"Deleted template files for template {template_id}: {len(file_result.data) if file_result.data else 0} rows")
                        except Exception as file_exc:
                            logger.warning(f"Could not delete template files: {file_exc}")
                        
                        try:
                            placeholder_result = supabase.table('template_placeholders').delete().eq('template_id', template_id).execute()
                            logger.info(f"Deleted template placeholders for template {template_id}: {len(placeholder_result.data) if placeholder_result.data else 0} rows")
                        except Exception as placeholder_exc:
                            logger.warning(f"Could not delete template placeholders: {placeholder_exc}")
                        
                        # Finally, hard delete the template record itself
                        delete_result = supabase.table('document_templates').delete().eq('id', template_id).execute()
                        deleted_count = len(delete_result.data) if delete_result.data else 0
                        if deleted_count > 0:
                            logger.info(f"✓ Hard deleted template record {template_id} from Supabase document_templates table ({deleted_count} row(s))")
                            supabase_deleted = True
                        else:
                            logger.warning(f"Template delete query executed but no rows were deleted for ID {template_id}")
                            warnings.append("Template not found in Supabase database (may have been already deleted)")
                        
                        # Verify deletion
                        verify_result = supabase.table('document_templates').select('id').eq('id', template_id).execute()
                        if verify_result.data and len(verify_result.data) > 0:
                            logger.error(f"⚠ WARNING: Template {template_id} still exists in Supabase after deletion attempt!")
                            warnings.append("Template deletion from Supabase may have failed - please verify")
                        else:
                            logger.info(f"✓ Verified: Template {template_id} successfully deleted from Supabase")
                            
                    except Exception as exc:
                        logger.error(f"✗ Failed to delete template from Supabase: {exc}")
                        import traceback
                        logger.error(traceback.format_exc())
                        warnings.append(f"Supabase delete failed: {str(exc)}")
                else:
                    logger.warning(f"Template not found in Supabase: {template_name}, proceeding with local deletion only")
            except Exception as supabase_exc:
                logger.error(f"✗ Error checking Supabase for template: {supabase_exc}")
                import traceback
                logger.error(traceback.format_exc())
                warnings.append(f"Could not check Supabase: {str(supabase_exc)}")

        docx_name = ensure_docx_filename(resolved_name)
        file_path = os.path.join(TEMPLATES_DIR, docx_name)
        
        # Try to delete local file - check multiple possible filename variations
        deleted_local = False
        file_variations = [
            docx_name,
            docx_name.lower(),
            docx_name.upper(),
            resolved_name,
            ensure_docx_filename(resolved_name.lower()),
            ensure_docx_filename(resolved_name.upper()),
            template_name,  # Original template name
            ensure_docx_filename(template_name),  # Original with .docx
        ]
        
        # Also check without .docx extension
        if not resolved_name.endswith('.docx'):
            file_variations.append(ensure_docx_filename(resolved_name))
        if not template_name.endswith('.docx'):
            file_variations.append(ensure_docx_filename(template_name))
        
        for file_variant in set(file_variations):  # Use set to avoid duplicates
            if not file_variant:
                continue
            variant_path = os.path.join(TEMPLATES_DIR, file_variant)
            if os.path.exists(variant_path):
                try:
                    os.remove(variant_path)
                    logger.info(f"Deleted local template file: {file_variant}")
                    deleted_local = True
                except Exception as exc:
                    logger.warning(f"Failed to delete template file {file_variant}: {exc}")
        
        # If template not found in Supabase and no local file, return 404
        if not template_id and not deleted_local:
            # Check if file exists with any variation
            file_exists = any(os.path.exists(os.path.join(TEMPLATES_DIR, var)) for var in set(file_variations) if var)
            if not file_exists:
                raise HTTPException(status_code=404, detail=f"Template not found: {template_name}")
        
        if not deleted_local:
            logger.warning(f"No local template file found to delete for {docx_name} (but marked as deleted in tracking file)")

        # Clean up placeholder settings
        placeholder_settings = read_json_file(PLACEHOLDER_SETTINGS_PATH, {})
        if placeholder_settings:
            removed = False
            if docx_name in placeholder_settings:
                placeholder_settings.pop(docx_name, None)
                removed = True
            else:
                normalised_key = normalise_template_key(docx_name)
                for key in list(placeholder_settings.keys()):
                    if normalise_template_key(key) == normalised_key:
                        placeholder_settings.pop(key, None)
                        removed = True
            if removed:
                write_json_atomic(PLACEHOLDER_SETTINGS_PATH, placeholder_settings)

        # Clean up metadata
        metadata = load_template_metadata()
        if metadata:
            removed_meta = False
            if docx_name in metadata:
                metadata.pop(docx_name, None)
                removed_meta = True
            else:
                normalised_key = normalise_template_key(docx_name)
                for key in list(metadata.keys()):
                    if normalise_template_key(key) == normalised_key:
                        metadata.pop(key, None)
                        removed_meta = True
            if removed_meta:
                save_template_metadata(metadata)

        # Clean up from plans.json if template exists in any plan
        try:
            plans = read_json_file(PLANS_PATH, {})
            if plans:
                template_name_without_ext = docx_name.replace('.docx', '')
                updated = False
                for plan_tier, plan_data in plans.items():
                    if isinstance(plan_data, dict) and 'can_download' in plan_data:
                        can_download = plan_data.get('can_download', [])
                        if isinstance(can_download, list):
                            # Remove template from plan's can_download list
                            original_length = len(can_download)
                            can_download = [t for t in can_download if t and ensure_docx_filename(t) != docx_name and t != template_name_without_ext]
                            if len(can_download) != original_length:
                                plan_data['can_download'] = can_download
                                updated = True
                                logger.info(f"Removed template {docx_name} from plan {plan_tier}")
                if updated:
                    write_json_atomic(PLANS_PATH, plans)
                    logger.info(f"Updated plans.json to remove template {docx_name}")
        except Exception as plans_exc:
            logger.warning(f"Could not update plans.json: {plans_exc}")

        # Mark template as deleted in deleted templates file (to prevent re-addition from local filesystem)
        # Mark all variations to ensure we catch it regardless of how it's named
        mark_template_as_deleted(docx_name)
        if resolved_name != docx_name:
            mark_template_as_deleted(resolved_name)
        if template_name != docx_name and template_name != resolved_name:
            mark_template_as_deleted(template_name)
        
        # Also mark case variations
        mark_template_as_deleted(docx_name.lower())
        mark_template_as_deleted(docx_name.upper())

        logger.info(f"Template deletion completed: {docx_name}")
        if supabase_deleted:
            logger.info(f"✓ Template successfully deleted from Supabase and local filesystem: {docx_name}")
        elif SUPABASE_ENABLED and not supabase_deleted:
            logger.warning(f"⚠ Template deleted locally but may not have been deleted from Supabase: {docx_name}")

        response = {
            "success": True, 
            "message": f"Template {docx_name} deleted completely",
            "deleted_from_supabase": supabase_deleted if SUPABASE_ENABLED else None
        }
        if warnings:
            response["warnings"] = warnings
        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting template: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# STEP 5: PLACEHOLDER SETTINGS API (JSON-backed)
# ============================================================================

@app.get("/placeholder-settings")
async def get_placeholder_settings(
    template_name: Optional[str] = None,
    template_id: Optional[str] = None,
    current_user: str = Depends(get_current_user)
):
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
            settings = fetch_template_placeholders(template_record['id'], template_record.get('file_name'))
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
    request: Request,
    current_user: str = Depends(get_current_user)
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
                    'customValue': str(cfg.get('customValue', '')).strip() if cfg.get('customValue') else '',
                    'databaseField': str(cfg.get('databaseField', '')).strip() if cfg.get('databaseField') else '',
                    'csvId': str(cfg.get('csvId', '')).strip() if cfg.get('csvId') else '',
                    'csvField': str(cfg.get('csvField', '')).strip() if cfg.get('csvField') else '',
                    'csvRow': int(cfg.get('csvRow', 0)) if cfg.get('csvRow') is not None else 0,
                    'randomOption': cfg.get('randomOption', 'auto') or 'auto'
                }
                logger.debug(f"Sanitized setting for '{placeholder}': source={sanitised_settings[placeholder]['source']}, databaseField={sanitised_settings[placeholder]['databaseField']}, csvId={sanitised_settings[placeholder]['csvId']}")

            logger.info(f"Saving {len(sanitised_settings)} placeholder settings for template {template_id} ({template_record.get('file_name')})")
            upsert_template_placeholders(template_id, sanitised_settings, template_record.get('file_name'))

            # Return latest snapshot
            refreshed = fetch_template_placeholders(template_id, template_record.get('file_name'))
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
async def update_plan(request: Request, current_user: str = Depends(get_current_user)):
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
                                # Normalize template names from can_download list (may have .docx or not)
                                template_names_normalized = set()
                                for t in allowed:
                                    if t != '*':
                                        # Ensure .docx extension for comparison
                                        normalized = ensure_docx_filename(t)
                                        template_names_normalized.add(normalise_template_key(normalized))
                                        # Also add without extension for flexibility
                                        template_names_normalized.add(normalise_template_key(t.replace('.docx', '').replace('.DOCX', '')))
                                
                                logger.info(f"Matching templates for plan {plan_id} against normalized names: {list(template_names_normalized)[:5]}...")

                                inserted_count = 0
                                for template in templates_res.data:
                                    template_name = template.get('file_name', '').strip()
                                    if not template_name:
                                        continue
                                    
                                    # Normalize template name for comparison
                                    normalized_template_name = normalise_template_key(ensure_docx_filename(template_name))
                                    normalized_template_name_no_ext = normalise_template_key(template_name.replace('.docx', '').replace('.DOCX', ''))
                                    
                                    # Check if this template matches any in the allowed list
                                    if normalized_template_name in template_names_normalized or normalized_template_name_no_ext in template_names_normalized:
                                        try:
                                            supabase.table('plan_template_permissions').insert({
                                                'plan_id': db_plan_id,
                                                'template_id': template['id'],
                                                'can_download': True
                                            }).execute()
                                            inserted_count += 1
                                            logger.debug(f"Added permission for template {template_name} (ID: {template['id']}) to plan {plan_id}")
                                        except Exception as insert_exc:
                                            logger.warning(f"Failed to insert permission for template {template_name}: {insert_exc}")
                                
                                logger.info(f"Set {inserted_count} template permissions for plan {plan_id} (matched {len(template_names_normalized)} template names)")
                    
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
                updated_plan['can_download'] = [ensure_docx_filename(can_download) if can_download != '*' else '*']
            elif isinstance(can_download, list):
                normalized = []
                for t in can_download:
                    if not t:
                        continue
                    if t == '*':
                        normalized.append('*')
                    elif isinstance(t, str):
                        normalized.append(ensure_docx_filename(t))
                    else:
                        normalized.append(t)
                updated_plan['can_download'] = normalized
        
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

@app.get("/templates/{template_name}/plan-info")
async def get_template_plan_info(template_name: str):
    """Get plan information for a specific template (which plans can download it)"""
    try:
        if not supabase:
            return {
                "success": True,
                "template_name": template_name,
                "plans": [],
                "source": "json_fallback"
            }
        
        # Get template ID
        template_file_name = template_name.replace('.docx', '')
        template_res = supabase.table('document_templates').select('id, file_name').eq('file_name', template_file_name).eq('is_active', True).limit(1).execute()
        
        if not template_res.data:
            raise HTTPException(status_code=404, detail="Template not found")
        
        template_id = template_res.data[0]['id']
        
        # Get all plans that can download this template
        permissions_res = supabase.table('plan_template_permissions').select(
            'plan_id, can_download'
        ).eq('template_id', template_id).eq('can_download', True).execute()
        
        plan_ids = [p['plan_id'] for p in (permissions_res.data or [])]
        
        if plan_ids:
            plans_res = supabase.table('subscription_plans').select(
                'id, plan_name, plan_tier, name'
            ).in_('id', plan_ids).eq('is_active', True).execute()
            
            plans = []
            if plans_res.data:
                for plan in plans_res.data:
                    plans.append({
                        "plan_id": str(plan['id']),
                        "plan_name": plan.get('plan_name') or plan.get('name') or plan.get('plan_tier'),
                        "plan_tier": plan.get('plan_tier')
                    })
            
            # If template is available to all plans (check if any plan has * permission)
            all_plans_res = supabase.table('subscription_plans').select('id, plan_name, plan_tier, name').eq('is_active', True).execute()
            if all_plans_res.data:
                # Check if there's a plan with all templates access
                for plan in all_plans_res.data:
                    plan_permissions = supabase.table('plan_template_permissions').select('template_id').eq('plan_id', plan['id']).execute()
                    # If plan has no restrictions or has all templates, include it
                    if not plan_permissions.data or len(plan_permissions.data) == 0:
                        # Check if plan allows all by checking can_download list in plans-db
                        plan_tier = plan.get('plan_tier')
                        plan_info = supabase.table('subscription_plans').select('*').eq('plan_tier', plan_tier).limit(1).execute()
                        if plan_info.data:
                            # Check plan permissions via RPC or direct check
                            plans.append({
                                "plan_id": str(plan['id']),
                                "plan_name": plan.get('plan_name') or plan.get('name') or plan_tier,
                                "plan_tier": plan_tier
                            })
            
            # Remove duplicates
            seen = set()
            unique_plans = []
            for plan in plans:
                key = (plan.get('plan_id'), plan.get('plan_name'))
                if key not in seen:
                    seen.add(key)
                    unique_plans.append(plan)
            
            return {
                "success": True,
                "template_name": template_name,
                "plans": unique_plans,
                "plan_name": unique_plans[0]['plan_name'] if unique_plans else None,
                "plan_tier": unique_plans[0]['plan_tier'] if unique_plans else None,
                "source": "database"
            }
        else:
            return {
                "success": True,
                "template_name": template_name,
                "plans": [],
                "plan_name": None,
                "plan_tier": None,
                "source": "database"
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting template plan info: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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
        
        # Load metadata map for fallback descriptions
        metadata_map = load_template_metadata()
        
        # Call database function
        templates_res = supabase.rpc('get_user_downloadable_templates', {
            'p_user_id': user_id
        }).execute()
        
        if templates_res.data:
            # Enhance with template details
            template_ids = [t['template_id'] for t in templates_res.data]
            details_res = supabase.table('document_templates').select('id, title, description, file_name, placeholders').in_('id', template_ids).execute()
            
            details_map = {d['id']: d for d in (details_res.data or [])}
            
            # Get user's plan info
            user_plan_info = None
            try:
                user_res = supabase.table('subscribers').select('subscription_plan, plan_tier').eq('user_id', user_id).limit(1).execute()
                if user_res.data and user_res.data[0]:
                    plan_tier = user_res.data[0].get('plan_tier') or user_res.data[0].get('subscription_plan')
                    if plan_tier:
                        plan_res = supabase.table('subscription_plans').select('id, plan_name, plan_tier, name').eq('plan_tier', plan_tier).limit(1).execute()
                        if plan_res.data:
                            user_plan_info = {
                                "plan_name": plan_res.data[0].get('plan_name') or plan_res.data[0].get('name') or plan_tier,
                                "plan_tier": plan_tier
                            }
            except Exception as e:
                logger.warning(f"Could not fetch user plan info: {e}")
            
            enhanced_templates = []
            for t in templates_res.data:
                template_id = t['template_id']
                details = details_map.get(template_id, {})
                
                # Get file_name and normalize for metadata lookup
                file_name = details.get('file_name', '')
                docx_file_name = ensure_docx_filename(file_name) if file_name else ''
                metadata_entry = metadata_map.get(docx_file_name, {}) if docx_file_name else {}
                
                # Get description from Supabase, fallback to metadata, fallback to empty
                description = (
                    details.get('description') or 
                    metadata_entry.get('description') or 
                    ''
                )
                
                # Get title/name - prefer Supabase title, fallback to metadata display_name
                template_title = (
                    details.get('title') or 
                    metadata_entry.get('display_name') or 
                    (file_name.replace('.docx', '') if file_name else 'Unknown')
                )
                
                # If user can download, use their plan name, otherwise try to get plan info for template
                plan_name = None
                plan_tier_val = None
                if t['can_download'] and user_plan_info:
                    plan_name = user_plan_info['plan_name']
                    plan_tier_val = user_plan_info['plan_tier']
                elif not t['can_download']:
                    # Try to get which plan allows this template
                    try:
                        perm_res = supabase.table('plan_template_permissions').select('plan_id').eq('template_id', template_id).eq('can_download', True).limit(1).execute()
                        if perm_res.data:
                            plan_id = perm_res.data[0]['plan_id']
                            plan_detail_res = supabase.table('subscription_plans').select('plan_name, plan_tier, name').eq('id', plan_id).limit(1).execute()
                            if plan_detail_res.data:
                                plan_name = plan_detail_res.data[0].get('plan_name') or plan_detail_res.data[0].get('name') or plan_detail_res.data[0].get('plan_tier')
                                plan_tier_val = plan_detail_res.data[0].get('plan_tier')
                    except Exception as e:
                        logger.warning(f"Could not fetch plan info for template {template_id}: {e}")
                
                enhanced_templates.append({
                    "id": str(template_id),
                    "name": template_title,
                    "title": template_title,
                    "file_name": file_name,
                    "description": description,
                    "placeholders": details.get('placeholders', []),
                    "can_download": t['can_download'],
                    "max_downloads": t['max_downloads'],
                    "current_downloads": t['current_downloads'],
                    "remaining_downloads": t['remaining_downloads'],
                    "plan_name": plan_name,
                    "plan_tier": plan_tier_val,
                    "metadata": {
                        "display_name": metadata_entry.get('display_name', template_title),
                        "description": metadata_entry.get('description', description)
                    }
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
    data_type: str = Form(...),
    current_user: str = Depends(get_current_user)
):
    """Upload CSV data file"""
    try:
        if not file.filename.endswith('.csv'):
            raise HTTPException(status_code=400, detail="Only .csv files are allowed")

        raw_label = (data_type or "").strip()
        if not raw_label:
            raise HTTPException(status_code=400, detail="data_type is required")

        dataset_id = normalise_dataset_id(raw_label)
        if not dataset_id:
            dataset_id = f"dataset_{uuid.uuid4().hex[:6]}"

        filename = dataset_id_to_filename(dataset_id)
        file_path = os.path.join(DATA_DIR, filename)

        with open(file_path, 'wb') as f:
            content = await file.read()
            f.write(content)

        upsert_data_source_metadata(dataset_id, raw_label)

        logger.info(f"CSV uploaded: {filename}")
        return {
            "success": True,
            "dataset_id": dataset_id,
            "filename": filename,
            "display_name": raw_label or dataset_id
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading CSV: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/data/all")
async def get_all_data(current_user: str = Depends(get_current_user)):
    """Get status of all CSV data sources"""
    try:
        data_sources: Dict[str, Dict[str, Optional[str]]] = {}
        for dataset in list_csv_datasets():
            file_path = dataset["path"]
            exists = os.path.exists(file_path)
            size = os.path.getsize(file_path) if exists else 0
            row_count = 0

            if exists:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        row_count = sum(1 for _ in reader)
                except Exception:
                    row_count = 0

            display_name = dataset.get("display_name") or dataset["id"].replace('_', ' ').title()

            data_sources[dataset["id"]] = {
                "filename": dataset["filename"],
                "exists": exists,
                "size": size,
                "row_count": row_count,
                "display_name": display_name
            }

        return {"success": True, "data_sources": data_sources}
    except Exception as e:
        logger.error(f"Error getting data sources: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/csv-files")
async def get_csv_files(current_user: str = Depends(get_current_user)):
    """Get list of available CSV files"""
    try:
        csv_files = []
        for dataset in list_csv_datasets():
            if os.path.exists(dataset["path"]):
                csv_files.append({
                    "id": dataset["id"],
                    "filename": dataset["filename"],
                    "display_name": dataset.get("display_name") or dataset["id"].replace('_', ' ').title()
                })

        return {"success": True, "csv_files": csv_files}
    except Exception as e:
        logger.error(f"Error getting CSV files: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/csv-fields/{csv_id}")
async def get_csv_fields(csv_id: str, current_user: str = Depends(get_current_user)):
    """Get columns/fields from a CSV file"""
    try:
        dataset_id = normalise_dataset_id(csv_id)
        if not dataset_id:
            raise HTTPException(status_code=404, detail="CSV file not found")

        file_path = os.path.join(DATA_DIR, dataset_id_to_filename(dataset_id))
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail=f"CSV file not found: {dataset_id}")

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
async def get_csv_rows(csv_id: str, field_name: str, current_user: str = Depends(get_current_user)):
    """Get all unique rows for a specific field in a CSV file"""
    try:
        dataset_id = normalise_dataset_id(csv_id)
        if not dataset_id:
            raise HTTPException(status_code=404, detail="CSV file not found")

        file_path = os.path.join(DATA_DIR, dataset_id_to_filename(dataset_id))
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail=f"CSV file not found: {dataset_id}")

        rows_data = []
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for idx, row in enumerate(reader):
                if field_name in row and row[field_name]:
                    value = row[field_name]
                    preview = value[:100] + "..." if len(str(value)) > 100 else value
                    rows_data.append({
                        "row_index": idx,
                        "value": value,
                        "preview": preview
                    })

        return {"success": True, "rows": rows_data[:100]}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting CSV rows: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/csv-files/{csv_id}")
async def delete_csv_file(csv_id: str, current_user: str = Depends(get_current_user)):
    """Delete a CSV data source file"""
    try:
        dataset_id = normalise_dataset_id(csv_id)
        if not dataset_id:
            raise HTTPException(status_code=404, detail="CSV file not found")

        filename = dataset_id_to_filename(dataset_id)
        file_path = os.path.join(DATA_DIR, filename)

        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="CSV file not found")

        os.remove(file_path)
        remove_data_source_metadata(dataset_id)
        logger.info(f"CSV deleted: {filename}")
        return {"success": True, "filename": filename, "dataset_id": dataset_id}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Error deleting CSV file: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))

def get_csv_data(csv_id: str, row_index: int = 0) -> Optional[Dict]:
    """Get data from a CSV file by row index"""
    try:
        # First, try to get filename from data_sources.json (for dynamic CSV uploads)
        metadata = load_data_sources_metadata()
        filename = None
        
        # Check if csv_id exists in metadata
        if csv_id in metadata:
            # Use dataset_id_to_filename to get the actual filename
            filename = dataset_id_to_filename(csv_id)
        else:
            # Fallback to legacy hardcoded mapping for backward compatibility
            csv_mapping = {
                "buyers_sellers": "buyers_sellers_data_220.csv",
                "bank_accounts": "bank_accounts.csv",
                "icpo": "icpo_section4_6_data_230.csv"
            }
            filename = csv_mapping.get(csv_id)
        
        if not filename:
            logger.warning(f"CSV dataset '{csv_id}' not found in metadata or legacy mapping")
            return None
        
        file_path = os.path.join(DATA_DIR, filename)
        if not os.path.exists(file_path):
            logger.warning(f"CSV file not found: {file_path}")
            return None
        
        # Read CSV data
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            
            if row_index < 0:
                row_index = 0
            if row_index < len(rows):
                logger.debug(f"Retrieved CSV data from {csv_id}[{row_index}]: {list(rows[row_index].keys())[:5]}...")
                return rows[row_index]
            else:
                logger.warning(f"Row index {row_index} out of range for CSV {csv_id} (has {len(rows)} rows)")
        
        return None
    except Exception as e:
        logger.error(f"Error reading CSV data for '{csv_id}' at row {row_index}: {e}")
        import traceback
        logger.error(traceback.format_exc())
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
        # Generate more realistic data based on placeholder name
        if 'company' in placeholder_lower or 'firm' in placeholder_lower:
            companies = ['Maritime Solutions Ltd', 'Ocean Trading Co', 'Global Shipping Inc', 'Marine Services Group', 'International Vessel Corp']
            return random.choice(companies)
        elif 'address' in placeholder_lower:
            addresses = ['123 Maritime Street, London, UK', '456 Harbor Road, Singapore', '789 Port Avenue, Dubai, UAE', '321 Dock Lane, Rotterdam, NL']
            return random.choice(addresses)
        elif 'person' in placeholder_lower or 'contact' in placeholder_lower:
            names = ['John Smith', 'Maria Garcia', 'Ahmed Hassan', 'Li Wei', 'David Johnson', 'Sarah Brown']
            return random.choice(names)
        elif 'value' in placeholder_lower or 'amount' in placeholder_lower or 'price' in placeholder_lower:
            return f"${random.randint(1000, 999999):,}"
        elif 'percent' in placeholder_lower or 'percentage' in placeholder_lower:
            return f"{random.uniform(0.1, 99.9):.2f}%"
        else:
            # Generate a more realistic generic value
            return f"Value-{random.randint(1000, 9999)}"

def _build_placeholder_pattern(placeholder: str) -> List[re.Pattern]:
    """
    Build regex patterns to match a placeholder WITH brackets in the document.
    Placeholder name from CMS is without brackets (e.g., "Vessel Name").
    We need to match it WITH brackets in document (e.g., "{Vessel Name}").
    """
    if not placeholder:
        return []

    # Normalize: remove any brackets if present (CMS stores without brackets)
    normalized = placeholder.strip()
    normalized = re.sub(r'^[{\[<%#_]+|[}\])%>#_]+$', '', normalized).strip()
    if not normalized:
        return []

    # Escape special regex characters, but allow flexible spacing/underscores
    # Convert spaces, underscores, hyphens to flexible pattern
    pattern_parts: List[str] = []
    for char in normalized:
        if char in {' ', '\u00A0', '_', '-'}:
            pattern_parts.append(r'[\s_\-]+')
        else:
            pattern_parts.append(re.escape(char))

    inner_pattern = ''.join(pattern_parts)
    
    # Build patterns that match the placeholder WITH brackets
    # Match: {placeholder}, {{placeholder}}, [placeholder], etc.
    wrappers = [
        rf"\{{\{{\s*{inner_pattern}\s*\}}\}}",   # {{placeholder}}
        rf"\{{\s*{inner_pattern}\s*\}}",         # {placeholder} - MOST COMMON
        rf"\[\[\s*{inner_pattern}\s*\]\]",       # [[placeholder]]
        rf"\[\s*{inner_pattern}\s*\]",           # [placeholder]
        rf"%\s*{inner_pattern}\s*%",             # %placeholder%
        rf"<\s*{inner_pattern}\s*>",             # <placeholder>
        rf"__\s*{inner_pattern}\s*__",           # __placeholder__
        rf"##\s*{inner_pattern}\s*##",           # ##placeholder##
    ]

    compiled_patterns = [re.compile(wrap, re.IGNORECASE) for wrap in wrappers]
    logger.debug(f"Built {len(compiled_patterns)} patterns for placeholder '{placeholder}' (normalized: '{normalized}')")
    for i, pattern in enumerate(compiled_patterns):
        logger.debug(f"  Pattern {i+1}: {pattern.pattern}")
    return compiled_patterns


def _replace_text_with_mapping(text: str, mapping: Dict[str, str], pattern_cache: Dict[str, List[re.Pattern]]) -> Tuple[str, int]:
    """
    Replace placeholders in text. Only replaces patterns WITH brackets.
    Example: "{Vessel Name}" -> "Titanic" (replaces entire pattern including brackets with value only)
    """
    total_replacements = 0
    updated_text = text

    for placeholder, value in mapping.items():
        if value is None or not value:
            logger.debug(f"Skipping placeholder '{placeholder}' - value is None or empty")
            continue

        # Get or build patterns for this placeholder
        patterns = pattern_cache.get(placeholder)
        if patterns is None:
            patterns = _build_placeholder_pattern(placeholder)
            pattern_cache[placeholder] = patterns
        
        if not patterns:
            logger.warning(f"No patterns built for placeholder '{placeholder}'")
            continue

        # Try each pattern until we find matches
        for pattern in patterns:
            matches = list(pattern.finditer(updated_text))
            if matches:
                logger.debug(f"Found {len(matches)} match(es) for placeholder '{placeholder}' using pattern: {pattern.pattern}")
                # Replace from end to start to preserve string positions
                for match in reversed(matches):
                    start, end = match.span()
                    matched_text = updated_text[start:end]
                    
                    # Replace entire match (including brackets) with value only
                    updated_text = updated_text[:start] + str(value) + updated_text[end:]
                    total_replacements += 1
                    logger.info(f"✅ Replaced: '{matched_text}' -> '{value}' (placeholder: '{placeholder}')")
                break  # Only use first matching pattern

    return updated_text, total_replacements


def replace_placeholders_in_docx(docx_path: str, data: Dict[str, str]) -> str:
    """
    Replace placeholders in a DOCX file.
    ONLY replaces placeholder patterns WITH brackets (e.g., {placeholder}).
    Replaces the ENTIRE pattern (including brackets) with just the value (no brackets).
    Preserves all other text and formatting.
    """
    try:
        logger.info("=" * 80)
        logger.info("🔄 Starting placeholder replacement with %d mappings", len(data))
        logger.info("=" * 80)
        for key, value in data.items():
            logger.info("📋 Mapping: '%s' -> '%s'", key, str(value))

        doc = Document(docx_path)
        replacements_made = 0
        pattern_cache: Dict[str, List[re.Pattern]] = {}
        
        # Build all patterns upfront for better performance
        logger.info("Building placeholder patterns...")
        for placeholder in data.keys():
            if placeholder not in pattern_cache:
                patterns = _build_placeholder_pattern(placeholder)
                pattern_cache[placeholder] = patterns
                logger.debug(f"Built {len(patterns)} patterns for '{placeholder}'")

        def replace_in_runs(runs, data_mapping, pattern_cache):
            """Replace placeholders in runs while preserving formatting"""
            total_replacements = 0
            
            for run in runs:
                original_run_text = run.text
                if not original_run_text:
                    continue
                
                # Quick check: does this run contain any placeholder pattern?
                has_placeholder = False
                for placeholder in data_mapping.keys():
                    patterns = pattern_cache.get(placeholder)
                    if patterns is None:
                        patterns = _build_placeholder_pattern(placeholder)
                        pattern_cache[placeholder] = patterns
                    
                    for pattern in patterns:
                        if pattern.search(original_run_text):
                            has_placeholder = True
                            break
                    if has_placeholder:
                        break
                
                if not has_placeholder:
                    continue  # Skip runs without placeholders
                
                # Replace placeholder patterns in this run
                updated_text, replaced = _replace_text_with_mapping(original_run_text, data_mapping, pattern_cache)
                
                if replaced > 0 and updated_text != original_run_text:
                    run.text = updated_text
                    total_replacements += replaced
                    logger.debug(f"Run updated: '{original_run_text[:50]}...' -> '{updated_text[:50]}...' ({replaced} replacements)")
            
            return total_replacements

        def process_paragraphs(paragraphs):
            """Process paragraphs and replace placeholders in their runs"""
            nonlocal replacements_made
            for paragraph in paragraphs:
                paragraph_text = paragraph.text
                if not paragraph_text:
                    continue
                
                # Quick check: does this paragraph contain any placeholder pattern?
                has_placeholder = False
                for placeholder in data.keys():
                    patterns = pattern_cache.get(placeholder)
                    if patterns is None:
                        patterns = _build_placeholder_pattern(placeholder)
                        pattern_cache[placeholder] = patterns
                    
                    for pattern in patterns:
                        if pattern.search(paragraph_text):
                            has_placeholder = True
                            break
                    if has_placeholder:
                        break
                
                if not has_placeholder:
                    continue  # Skip paragraphs without placeholders
                
                # Replace placeholders in runs (preserves formatting)
                replaced = replace_in_runs(paragraph.runs, data, pattern_cache)
                replacements_made += replaced
                
                if replaced > 0:
                    logger.info(f"📝 Paragraph: replaced {replaced} placeholder(s) in '{paragraph_text[:60]}...'")

        # Process body paragraphs
        logger.info("Processing body paragraphs...")
        process_paragraphs(doc.paragraphs)

        # Process tables
        logger.info("Processing tables...")
        for table_idx, table in enumerate(doc.tables):
            for row_idx, row in enumerate(table.rows):
                for cell_idx, cell in enumerate(row.cells):
                    for paragraph in cell.paragraphs:
                        paragraph_text = paragraph.text
                        if not paragraph_text:
                            continue
                        
                        # Check if paragraph has placeholders
                        has_placeholder = False
                        for placeholder in data.keys():
                            patterns = pattern_cache.get(placeholder, [])
                            for pattern in patterns:
                                if pattern.search(paragraph_text):
                                    has_placeholder = True
                                    break
                            if has_placeholder:
                                break
                        
                        if has_placeholder:
                            replaced = replace_in_runs(paragraph.runs, data, pattern_cache)
                            replacements_made += replaced
                            if replaced > 0:
                                logger.debug(f"Table[{table_idx}][{row_idx}][{cell_idx}]: {replaced} replacement(s)")

        # Process headers and footers
        logger.info("Processing headers and footers...")
        for section in doc.sections:
            for paragraph in section.header.paragraphs:
                paragraph_text = paragraph.text
                if paragraph_text:
                    has_placeholder = False
                    for placeholder in data.keys():
                        patterns = pattern_cache.get(placeholder, [])
                        for pattern in patterns:
                            if pattern.search(paragraph_text):
                                has_placeholder = True
                                break
                        if has_placeholder:
                            break
                    if has_placeholder:
                        replaced = replace_in_runs(paragraph.runs, data, pattern_cache)
                        replacements_made += replaced
            
            for paragraph in section.footer.paragraphs:
                paragraph_text = paragraph.text
                if paragraph_text:
                    has_placeholder = False
                    for placeholder in data.keys():
                        patterns = pattern_cache.get(placeholder, [])
                        for pattern in patterns:
                            if pattern.search(paragraph_text):
                                has_placeholder = True
                                break
                        if has_placeholder:
                            break
                    if has_placeholder:
                        replaced = replace_in_runs(paragraph.runs, data, pattern_cache)
                        replacements_made += replaced

        logger.info("=" * 80)
        logger.info("✅ Total replacements made: %d", replacements_made)
        logger.info("=" * 80)

        output_path = os.path.join(TEMP_DIR, f"processed_{uuid.uuid4().hex}.docx")
        doc.save(output_path)
        logger.info(f"💾 Saved processed document to: {output_path}")
        return output_path

    except Exception as e:
        logger.error("❌ Error processing document: %s", e)
        import traceback
        logger.error(traceback.format_exc())
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

            template_settings = fetch_template_placeholders(template_record['id'], template_record.get('file_name'))

            file_record = fetch_template_file_record(template_record['id'], include_data=True)
            fallback_checked = False
            template_path = None

            if file_record:
                file_data = file_record.get("file_data")
                if file_data:
                    template_temp_path = write_temp_docx_from_record(file_record)
                    template_path = template_temp_path
                    effective_template_name = template_record.get('file_name') or template_name
                else:
                    logger.error(f"Template file missing data for template_id={template_record['id']}")
                    fallback_checked = True
            else:
                fallback_checked = True

            if fallback_checked:
                logger.warning(f"Template file missing in Supabase for '{template_name}', attempting filesystem fallback")
                fallback_name = template_record.get('file_name') or template_name
                if not fallback_name.endswith('.docx'):
                    fallback_name = f"{fallback_name}.docx"

                fallback_path = os.path.join(TEMPLATES_DIR, fallback_name)
                if os.path.exists(fallback_path):
                    template_path = fallback_path
                    effective_template_name = fallback_name
                else:
                    raise HTTPException(status_code=404, detail=f"Template file missing for: {template_name}")
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
        
        # Filter out invalid placeholders (those with unclosed brackets or special characters)
        valid_placeholders = []
        for ph in placeholders:
            # Skip placeholders that contain bracket characters (likely incomplete)
            if any(char in ph for char in ['{', '}', '[', ']', '<', '>']):
                logger.warning(f"⚠️  Skipping invalid placeholder (contains brackets): '{ph}'")
                continue
            valid_placeholders.append(ph)
        
        placeholders = valid_placeholders
        
        # Generate data for each placeholder
        data_mapping = {}
        logger.info(f"📝 Processing {len(placeholders)} valid placeholders from document")
        logger.info(f"⚙️  Template has {len(template_settings)} configured placeholders in CMS")
        
        if template_settings:
            logger.info(f"   Configured placeholders: {list(template_settings.keys())[:10]}...")
        
        # Log all extracted placeholders for debugging
        logger.info(f"   Extracted placeholders: {placeholders[:20]}...")  # Show first 20
        
        for placeholder in placeholders:
            found = False
            setting_key, setting = resolve_placeholder_setting(template_settings, placeholder)
            
            # Log all available settings keys for debugging
            if not setting and template_settings:
                logger.warning(f"⚠️  Placeholder '{placeholder}' not found in template_settings")
                logger.warning(f"   Available settings keys: {list(template_settings.keys())[:10]}...")
                logger.warning(f"   Trying to match using normalization...")
                # Try to find similar placeholder names
                placeholder_lower = placeholder.lower().strip()
                for key in template_settings.keys():
                    if placeholder_lower in key.lower() or key.lower() in placeholder_lower:
                        logger.warning(f"   Similar key found: '{key}' (consider using this exact name)")

            if setting:
                source = setting.get('source', 'random')
                logger.info(f"\n🔍 Processing placeholder: '{placeholder}' (CMS key: '{setting_key}', source: {source})")
                logger.debug(f"Full CMS setting for '{placeholder}': {setting}")
                logger.debug(f"   customValue: '{setting.get('customValue')}'")
                logger.debug(f"   databaseField: '{setting.get('databaseField')}'")
                logger.debug(f"   csvId: '{setting.get('csvId')}', csvField: '{setting.get('csvField')}', csvRow: {setting.get('csvRow')}")

                if source == 'custom':
                    custom_value = str(setting.get('customValue', '')).strip()
                    if custom_value:
                        data_mapping[placeholder] = custom_value
                        found = True
                        logger.info(f"✅ {placeholder} -> '{custom_value}' (CMS custom value)")
                    else:
                        logger.warning(f"⚠️  Placeholder '{placeholder}' has custom source but customValue is empty")

                elif source == 'database':
                    database_field = (setting.get('databaseField') or '').strip()
                    logger.info(f"  🗄️  DATABASE source configured for '{placeholder}'")
                    logger.info(f"     databaseField='{database_field}'")
                    logger.info(f"     vessel_imo='{vessel_imo}' (from page)")
                    logger.info(f"  📋 Available vessel fields: {list(vessel.keys())}")

                    matched_field = None
                    matched_value = None

                    if database_field:
                        if database_field in vessel:
                            value = vessel[database_field]
                            if value is not None and str(value).strip() != '':
                                matched_field = database_field
                                matched_value = str(value).strip()
                                logger.info(f"  ✅ Exact match found: '{database_field}'")
                        else:
                            database_field_lower = database_field.lower()
                            for key, value in vessel.items():
                                if key.lower() == database_field_lower and value is not None and str(value).strip() != '':
                                    matched_field = key
                                    matched_value = str(value).strip()
                                    logger.info(f"  ✅ Case-insensitive match: '{database_field}' -> '{key}'")
                                    break

                    if not matched_field and not database_field:
                        logger.info(f"  🔍 databaseField is empty, trying intelligent matching for '{placeholder}'...")
                        matched_field, matched_value = _intelligent_field_match(placeholder, vessel)
                        if matched_field:
                            logger.info(f"  ✅ Intelligent match found: '{placeholder}' -> '{matched_field}'")

                    if not matched_field and database_field:
                        logger.info(f"  🔍 Explicit field '{database_field}' not found, trying intelligent matching...")
                        matched_field, matched_value = _intelligent_field_match(placeholder, vessel)
                        if matched_field:
                            logger.info(f"  ✅ Intelligent fallback match: '{placeholder}' -> '{matched_field}'")

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
                    csv_id = setting.get('csvId', '')
                    csv_field = setting.get('csvField', '')
                    csv_row = setting.get('csvRow', 0)

                    logger.info(f"  📊 CSV source configured for '{placeholder}'")
                    logger.info(f"     csvId='{csv_id}', csvField='{csv_field}', csvRow={csv_row}")

                    if csv_id and csv_field:
                        try:
                            csv_row_int = int(csv_row) if csv_row is not None else 0
                            csv_data = get_csv_data(csv_id, csv_row_int)
                            
                            if csv_data:
                                logger.info(f"  ✅ CSV data retrieved for '{csv_id}' at row {csv_row_int}")
                                logger.info(f"     Available fields: {list(csv_data.keys())[:10]}...")
                                
                                # Try exact match first
                                if csv_field in csv_data:
                                    value = csv_data[csv_field]
                                    if value is not None and str(value).strip() != '':
                                        data_mapping[placeholder] = str(value).strip()
                                        found = True
                                        logger.info(f"  ✅✅✅ SUCCESS: {placeholder} = '{value}' (CSV: {csv_id}[{csv_row_int}].{csv_field})")
                                    else:
                                        logger.warning(f"  ⚠️  CSV field '{csv_field}' exists but is empty")
                                else:
                                    # Try case-insensitive match
                                    csv_field_lower = csv_field.lower()
                                    matched_field = None
                                    for key in csv_data.keys():
                                        if key.lower() == csv_field_lower:
                                            value = csv_data[key]
                                            if value is not None and str(value).strip() != '':
                                                matched_field = key
                                                data_mapping[placeholder] = str(value).strip()
                                                found = True
                                                logger.info(f"  ✅✅✅ SUCCESS: {placeholder} = '{value}' (CSV: {csv_id}[{csv_row_int}].{matched_field} - case-insensitive match)")
                                                break
                                    
                                    if not matched_field:
                                        logger.error(f"  ❌❌❌ FAILED: CSV field '{csv_field}' not found in CSV data!")
                                        logger.error(f"  ❌ Available fields: {list(csv_data.keys())}")
                            else:
                                logger.error(f"  ❌❌❌ FAILED: Could not retrieve CSV data for '{csv_id}' at row {csv_row_int}")
                        except Exception as csv_exc:
                            logger.error(f"  ❌❌❌ ERROR processing CSV data for '{placeholder}': {csv_exc}")
                            import traceback
                            logger.error(traceback.format_exc())
                    else:
                        logger.warning(f"  ⚠️  {placeholder}: CSV source selected but csvId or csvField missing in CMS")
                        logger.warning(f"     csvId='{csv_id}', csvField='{csv_field}'")

            if not found:
                if setting:
                    random_option = setting.get('randomOption', 'auto')
                    source = setting.get('source', 'random')
                    logger.warning(f"  ⚠⚠⚠ {placeholder}: Using RANDOM data (source in CMS: '{source}', found: {found})")
                else:
                    random_option = 'auto'
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
        
        # Get template display name for filename (from metadata or Supabase title)
        template_display_name = template_name.replace('.docx', '').replace('.DOCX', '')
        if template_record:
            # Get display name from Supabase title or file_name
            template_display_name = template_record.get('title') or template_record.get('file_name', '')
            if template_display_name:
                template_display_name = template_display_name.replace('.docx', '').replace('.DOCX', '')
        
        # Also check metadata for display_name
        if template_record:
            docx_filename = ensure_docx_filename(template_record.get('file_name') or template_name)
            metadata_map = load_template_metadata()
            metadata_entry = metadata_map.get(docx_filename, {})
            if metadata_entry.get('display_name'):
                template_display_name = metadata_entry['display_name']
        
        # Clean template display name for filename (remove invalid characters)
        template_display_name = re.sub(r'[<>:"/\\|?*]', '_', template_display_name).strip()
        if not template_display_name:
            template_display_name = template_name.replace('.docx', '').replace('.DOCX', '')
        
        # Read file content
        if pdf_path.endswith('.pdf'):
            with open(pdf_path, 'rb') as f:
                file_content = f.read()
            media_type = "application/pdf"
            filename = f"{template_display_name}_{vessel_imo}.pdf"
        else:
            with open(processed_docx, 'rb') as f:
                file_content = f.read()
            media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            filename = f"{template_display_name}_{vessel_imo}.docx"
        
        logger.info(f"Generated filename: {filename} (from template display name: {template_display_name})")
        
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

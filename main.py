
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
import traceback
import csv
import zipfile
import io
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from urllib.parse import quote
from fastapi import FastAPI, HTTPException, File, UploadFile, Form, Request, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from supabase import create_client, Client
from docx import Document
import re

# Try to import optional dependencies
try:
    import fitz  # PyMuPDF
    FITZ_AVAILABLE = True
except ImportError:
    FITZ_AVAILABLE = False

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

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

# Directories (DATA_DIR overridable via env on VPS)
BASE_DIR = os.getcwd()
TEMPLATES_DIR = os.path.join(BASE_DIR, 'templates')
TEMP_DIR = os.path.join(BASE_DIR, 'temp')
DATA_DIR = os.environ.get('DOCUMENT_PROCESSOR_DATA_DIR') or os.path.join(BASE_DIR, 'data')
STORAGE_DIR = os.path.join(BASE_DIR, 'storage')
CMS_DIR = os.path.join(BASE_DIR, 'cms')

os.makedirs(TEMPLATES_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(STORAGE_DIR, exist_ok=True)
logger.info(f"DATA_DIR={DATA_DIR}")
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

# OpenAI Configuration - Try Supabase first, then environment variable
def get_openai_api_key_from_supabase() -> Optional[str]:
    """Get OpenAI API key from Supabase system_settings table."""
    if not SUPABASE_ENABLED:
        return None
    try:
        response = supabase.table('system_settings').select('setting_value').eq('setting_key', 'openai_api_key').limit(1).execute()
        if response.data and len(response.data) > 0:
            setting_value = response.data[0].get('setting_value')
            # Handle JSONB - can be string or dict
            if isinstance(setting_value, str):
                return setting_value.strip() if setting_value else None
            elif isinstance(setting_value, dict):
                # If stored as {"value": "key"} or similar
                return str(setting_value.get('value', '')).strip() or None
            return str(setting_value).strip() if setting_value else None
    except Exception as e:
        logger.debug(f"Could not retrieve OpenAI API key from Supabase: {e}")
    return None

# Try Supabase first, then environment variable
OPENAI_API_KEY = get_openai_api_key_from_supabase() or os.getenv("OPENAI_API_KEY", "")
OPENAI_ENABLED = OPENAI_AVAILABLE and bool(OPENAI_API_KEY)
openai_client = None

if OPENAI_ENABLED:
    try:
        openai_client = OpenAI(api_key=OPENAI_API_KEY)
        key_source = "Supabase" if get_openai_api_key_from_supabase() else "environment variable"
        logger.info(f"OpenAI client initialized successfully (API key from {key_source})")
    except Exception as e:
        logger.warning(f"Failed to initialize OpenAI client: {e}")
        openai_client = None
else:
    if not OPENAI_AVAILABLE:
        logger.warning("OpenAI library not installed. AI-powered placeholder matching will be disabled.")
    elif not OPENAI_API_KEY:
        logger.warning("OpenAI API key not configured (check Supabase system_settings or OPENAI_API_KEY env var). AI-powered placeholder matching will be disabled.")


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
        logger.warning("Supabase not enabled, cannot resolve template record")
        return None

    # Allow direct lookup by UUID string
    try:
        template_uuid = uuid.UUID(str(template_name))
    except (ValueError, TypeError):
        template_uuid = None

    if template_uuid:
        try:
            logger.debug(f"Attempting UUID lookup for template: {template_uuid}")
            response = supabase.table('document_templates') \
                .select('id, title, description, file_name, placeholders, is_active, created_at, updated_at, font_family, font_size') \
                .eq('id', str(template_uuid)) \
                .limit(1) \
                .execute()
            if response.data and len(response.data) > 0:
                logger.debug(f"✅ Found template by UUID: {template_uuid} -> {response.data[0].get('file_name')}")
                return response.data[0]
            else:
                logger.warning(f"⚠️ No template found in database with UUID: {template_uuid}")
        except Exception as exc:
            logger.error(
                f"❌ Failed to resolve template by ID '{template_name}': {exc}", exc_info=True)

    name_with_ext = template_name if template_name.endswith(
        '.docx') else f"{template_name}.docx"
    name_without_ext = template_name[:-
        5] if template_name.endswith('.docx') else template_name

    candidates = list({name_with_ext, name_without_ext})

    try:
        response = supabase.table('document_templates') \
            .select('id, title, description, file_name, placeholders, is_active, created_at, updated_at, font_family, font_size') \
            .in_('file_name', candidates) \
            .limit(1) \
            .execute()
        if response.data:
            return response.data[0]

        response = supabase.table('document_templates') \
            .select('id, title, description, file_name, placeholders, is_active, created_at, updated_at, font_family, font_size') \
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
    """
    Fetch placeholder settings for a template from Supabase and disk.
    Merges settings with priority: Supabase > disk.
    Returns normalized settings dict.
    """
    # Load disk settings first as fallback
    disk_settings = read_json_file(PLACEHOLDER_SETTINGS_PATH, {})
    disk_result = _lookup_placeholder_settings_from_disk(
        disk_settings, template_id, template_hint)

    if not SUPABASE_ENABLED:
        logger.info(f"Supabase not enabled, using disk settings only for template {template_id}")
        return disk_result

    # Try to load from Supabase
    supabase_settings: Dict[str, Dict[str, Optional[str]]] = {}
    try:
        response = supabase.table('template_placeholders').select(
            'placeholder, source, custom_value, database_table, database_field, csv_id, csv_field, csv_row, random_option'
        ).eq('template_id', template_id).execute()
        
        for row in response.data or []:
            placeholder_key = row.get('placeholder', '')
            if not placeholder_key:
                continue
                
            source = row.get('source')
            if source is None or (isinstance(source, str) and not source.strip()):
                source = 'database'
            else:
                source = str(source).strip()
            
            supabase_settings[placeholder_key] = {
                'source': source,
                'customValue': str(row.get('custom_value') or '').strip(),
                'databaseTable': str(row.get('database_table') or '').strip(),
                'databaseField': str(row.get('database_field') or '').strip(),
                'csvId': str(row.get('csv_id') or '').strip(),
                'csvField': str(row.get('csv_field') or '').strip(),
                'csvRow': int(row['csv_row']) if row.get('csv_row') is not None else 0,
                'randomOption': row.get('random_option', 'auto') or 'auto'
            }
            logger.debug(f"Loaded placeholder setting from Supabase for '{placeholder_key}': source={supabase_settings[placeholder_key]['source']}")
        
        if supabase_settings:
            logger.info(f"Loaded {len(supabase_settings)} placeholder settings from Supabase for template {template_id}")
    except Exception as exc:
        logger.error(f"Failed to fetch template placeholders from Supabase for {template_id}: {exc}")
        logger.info(f"Falling back to disk settings")

    # Merge settings: Supabase takes priority, but fill in missing placeholders from disk
    merged_settings = {}
    
    # First, add all disk settings
    merged_settings.update(disk_result)
    
    # Then, override with Supabase settings (higher priority)
    merged_settings.update(supabase_settings)
    
    # Default to 'database' only when source is missing or empty. Preserve explicit random/csv.
    for placeholder, setting in merged_settings.items():
        source = setting.get('source')
        if source is None or (isinstance(source, str) and not source.strip()):
            setting['source'] = 'database'
            logger.debug(f"Normalized placeholder '{placeholder}' source to 'database' (was missing)")
    
    if merged_settings:
        logger.info(f"Merged {len(merged_settings)} placeholder settings (Supabase: {len(supabase_settings)}, Disk: {len(disk_result)})")
    
    return merged_settings


def _lookup_placeholder_settings_from_disk(
    disk_settings: Dict[str, Dict], template_id: str, template_hint: Optional[str]) -> Dict[str, Dict[str, Optional[str]]]:
    """
    Internal helper to find placeholder config from disk storage.
    Uses unified normalization for consistent matching.
    """
    if not disk_settings:
        return {}
    
    candidates = []
    if template_hint:
        # Try various formats of template_hint
        candidates.extend([
            template_hint,
            normalize_template_name(template_hint, with_extension=True, for_key=False),
            normalize_template_name(template_hint, with_extension=False, for_key=False),
            normalize_template_name(template_hint, with_extension=False, for_key=True),
        ])
    if template_id:
        candidates.append(str(template_id))
        # Also try normalized versions
        candidates.append(normalize_template_name(str(template_id), with_extension=True, for_key=False))

    # Remove duplicates while preserving order
    seen = set()
    unique_candidates = []
    for candidate in candidates:
        if candidate and candidate not in seen:
            seen.add(candidate)
            unique_candidates.append(candidate)

    # Try direct matches first
    for candidate in unique_candidates:
        if candidate in disk_settings:
            logger.debug(f"Found disk settings using direct match: '{candidate}'")
            return disk_settings[candidate]
    
    # Try normalized key matching
    for candidate in unique_candidates:
        candidate_key = normalize_template_name(candidate, with_extension=False, for_key=True)
        if not candidate_key:
            continue
        
        for key in disk_settings.keys():
            key_normalized = normalize_template_name(key, with_extension=False, for_key=True)
            if key_normalized == candidate_key:
                logger.debug(f"Found disk settings using normalized match: '{candidate}' -> '{key}'")
                return disk_settings[key]
    
    logger.debug(f"No disk settings found for template_id={template_id}, template_hint={template_hint}")
    return {}


def upsert_template_placeholders(template_id: str,
    settings: Dict[str,
    Dict],
     template_hint: Optional[str] = None) -> None:
    """Upsert placeholder settings into Supabase"""
    if SUPABASE_ENABLED and settings:
        rows = []
        for placeholder, cfg in settings.items():
            source = cfg.get('source')
            if source is None or (isinstance(source, str) and not source.strip()):
                source = 'database'
            else:
                source = str(source).strip()
            
            rows.append({
                'template_id': template_id,
                'placeholder': placeholder,
                'source': source,
                'custom_value': cfg.get('customValue'),
                'database_table': cfg.get('databaseTable') or cfg.get('database_table'),
                'database_field': cfg.get('databaseField') or cfg.get('database_field'),
                'csv_id': cfg.get('csvId') or cfg.get('csv_id'),
                'csv_field': cfg.get('csvField') or cfg.get('csv_field'),
                'csv_row': cfg.get('csvRow') or cfg.get('csv_row', 0),
                'random_option': cfg.get('randomOption') or cfg.get('random_option', 'auto')
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
    try:
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
    except Exception as e:
        logger.warning(f"list_csv_datasets error: {e}")
    return datasets


def normalize_template_name(value: Optional[str], with_extension: bool = True, for_key: bool = False) -> str:
    """
    Unified template name normalization function.
    
    Args:
        value: Template name (with or without .docx extension)
        with_extension: If True, ensure .docx extension is present. If False, remove it.
        for_key: If True, normalize for use as a dictionary key (lowercase, no extension)
    
    Returns:
        Normalized template name
    """
    if not value:
        return ""
    
    # Strip whitespace and get basename
    name = value.strip()
    name = os.path.basename(name)
    
    # Remove extension if present
    if name.lower().endswith('.docx'):
        name = name[:-5]
    
    # For dictionary keys, return lowercase without extension
    if for_key:
        return name.strip().lower()
    
    # Add extension if requested
    if with_extension:
        return f"{name.strip()}.docx"
    
    return name.strip()


def normalise_template_key(value: Optional[str]) -> str:
    """Normalise template identifiers to a consistent filesystem key (deprecated - use normalize_template_name with for_key=True)."""
    return normalize_template_name(value, with_extension=False, for_key=True)


def _normalize_for_match(value: Optional[str]) -> str:
    """Normalize template name for fuzzy file matching (lower, no .docx, collapsed spaces)."""
    if not value:
        return ""
    s = value.strip().lower()
    if s.endswith(".docx"):
        s = s[:-5].strip()
    return " ".join(s.split())


def ensure_docx_filename(value: str) -> str:
    """Ensure filename ends with .docx (deprecated - use normalize_template_name with with_extension=True)."""
    return normalize_template_name(value, with_extension=True, for_key=False)


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

        # Set HttpOnly cookie - handle localhost vs cross-origin (petrodealhub.com -> control)
        response = Response(content=json.dumps(
            {"success": True, "user": username}), media_type="application/json")
        origin = (request.headers.get('origin') or '').strip().lower()
        # Cross-origin: petrodealhub.com -> control. SameSite=Lax blocks cookies on DELETE.
        # Use None + Secure so cross-origin DELETE (doc CMS) sends session.
        use_cross_site = origin in (
            'https://petrodealhub.com', 'https://www.petrodealhub.com',
            'https://control.petrodealhub.com',
        )
        kwargs = dict(key='session', value=token, httponly=True, max_age=86400, path='/')
        if use_cross_site:
            kwargs['samesite'] = 'none'
            kwargs['secure'] = True
        else:
            kwargs['samesite'] = 'lax'
        response.set_cookie(**kwargs)
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


def _cors_preflight_headers_auth(request: Request, allowed_methods: str) -> Dict[str, str]:
    """CORS headers for auth preflight (used before _cors_preflight_headers is defined)."""
    origin = request.headers.get("origin", "")
    h: Dict[str, str] = {
        "Access-Control-Allow-Methods": allowed_methods,
        "Access-Control-Allow-Headers": request.headers.get("access-control-request-headers", "Content-Type, Authorization"),
        "Access-Control-Allow-Credentials": "true",
        "Access-Control-Max-Age": "600",
        "Vary": "Origin",
    }
    if origin and origin in ALLOWED_ORIGINS:
        h["Access-Control-Allow-Origin"] = origin
    elif ALLOWED_ORIGINS:
        h["Access-Control-Allow-Origin"] = ALLOWED_ORIGINS[0]
    else:
        h["Access-Control-Allow-Origin"] = "*"
    return h


@app.options("/auth/login")
async def options_auth_login(request: Request):
    """CORS preflight for /auth/login."""
    return Response(status_code=204, headers=_cors_preflight_headers_auth(request, "POST, OPTIONS"))


@app.options("/auth/logout")
async def options_auth_logout(request: Request):
    """CORS preflight for /auth/logout."""
    return Response(status_code=204, headers=_cors_preflight_headers_auth(request, "POST, OPTIONS"))


@app.options("/auth/me")
async def options_auth_me(request: Request):
    """CORS preflight for /auth/me."""
    return Response(status_code=204, headers=_cors_preflight_headers_auth(request, "GET, POST, OPTIONS"))


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


@app.get("/database-tables")
async def get_database_tables(request: Request):
    """Get list of all available database tables that can be used as data sources"""
    # Allow unauthenticated access for CMS editor
    try:
        # List of available tables with their display names (brokers excluded - not used for mapping)
        tables = [
            {'name': 'vessels', 'label': 'Vessels', 'description': 'Vessel information and specifications'},
            {'name': 'ports', 'label': 'Ports', 'description': 'Port information and details'},
            {'name': 'refineries', 'label': 'Refineries', 'description': 'Refinery information'},
            {'name': 'companies', 'label': 'Companies', 'description': 'Company information'},
        ]
        
        # If Supabase is enabled, we could dynamically fetch table names
        # For now, return the predefined list
        logger.info(f"Returning {len(tables)} database tables")
        return {"success": True, "tables": tables}
    except Exception as e:
        logger.error(f"Error getting database tables: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/database-tables/{table_name}/columns")
async def get_database_table_columns(table_name: str, request: Request):
    """Get list of columns for a specific database table"""
    try:
        if not SUPABASE_ENABLED:
            raise HTTPException(status_code=503, detail="Supabase not available")
        
        # Try to get column information from Supabase
        # We'll query the table with LIMIT 0 to get column names without data
        try:
            # Get a sample row to infer column names
            response = supabase.table(table_name).select('*').limit(1).execute()
            
            if response.data and len(response.data) > 0:
                # Extract column names from the first row
                columns = []
                for key in response.data[0].keys():
                    # Create a human-readable label
                    label = key.replace('_', ' ').title()
                    columns.append({
                        'name': key,
                        'label': label,
                        'type': 'text'  # Default type, could be enhanced with actual type detection
                    })
                
                return {"success": True, "table": table_name, "columns": columns}
            else:
                # Table exists but is empty: use predefined columns so editor can still select fields
                predefined_columns = _get_predefined_table_columns(table_name)
                return {"success": True, "table": table_name, "columns": predefined_columns}
        except Exception as table_exc:
            logger.error(f"Error querying table {table_name}: {table_exc}")
            # Fallback to predefined column lists for known tables
            predefined_columns = _get_predefined_table_columns(table_name)
            if predefined_columns:
                return {"success": True, "table": table_name, "columns": predefined_columns}
            else:
                raise HTTPException(status_code=404, detail=f"Table '{table_name}' not found or not accessible")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting table columns for {table_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _get_predefined_table_columns(table_name: str) -> List[Dict[str, str]]:
    """Get predefined column list for known tables (fallback). Aligned with real DB schema (types.ts)."""

    def col(n: str, lbl: str, t: str = 'text') -> Dict[str, str]:
        return {'name': n, 'label': lbl, 'type': t}

    predefined = {
        'vessels': [
            col('id', 'ID', 'integer'),
            col('name', 'Vessel Name'),
            col('imo', 'IMO Number'),
            col('mmsi', 'MMSI'),
            col('vessel_type', 'Vessel Type'),
            col('flag', 'Flag'),
            col('built', 'Year Built', 'integer'),
            col('deadweight', 'Deadweight', 'numeric'),
            col('cargo_capacity', 'Cargo Capacity', 'numeric'),
            col('cargo_capacity_bbl', 'Cargo Capacity (bbl)', 'numeric'),
            col('length', 'Length', 'numeric'),
            col('width', 'Width', 'numeric'),
            col('beam', 'Beam'),
            col('draft', 'Draft'),
            col('draught', 'Draught', 'numeric'),
            col('gross_tonnage', 'Gross Tonnage', 'numeric'),
            col('owner_name', 'Owner Name'),
            col('operator_name', 'Operator Name'),
            col('callsign', 'Call Sign'),
            col('currentport', 'Current Port'),
            col('loading_port', 'Loading Port'),
            col('discharge_port', 'Discharge Port'),
            col('departure_port', 'Departure Port ID', 'integer'),
            col('destination_port', 'Destination Port ID', 'integer'),
            col('destination', 'Destination'),
            col('eta', 'ETA'),
            col('nav_status', 'Nav Status'),
            col('status', 'Status'),
            col('vesselstatus', 'Vessel Status'),
            col('fuel_consumption', 'Fuel Consumption', 'numeric'),
            col('engine_power', 'Engine Power', 'numeric'),
            col('speed', 'Speed'),
            col('service_speed', 'Service Speed'),
            col('deal_value', 'Deal Value', 'numeric'),
            col('dealvalue', 'Deal Value (text)'),
            col('deal_status', 'Deal Status'),
            col('deal_reference_id', 'Deal Reference ID'),
            col('buyer_name', 'Buyer Name'),
            col('seller_name', 'Seller Name'),
            col('buyer_company_id', 'Buyer Company ID', 'integer'),
            col('seller_company_id', 'Seller Company ID', 'integer'),
            col('company_id', 'Company ID', 'integer'),
            col('refinery_id', 'Refinery ID'),
            col('price', 'Price', 'numeric'),
            col('market_price', 'Market Price', 'numeric'),
            col('indicative_price', 'Indicative Price', 'numeric'),
            col('quantity', 'Quantity', 'numeric'),
            col('cargo_quantity', 'Cargo Quantity', 'numeric'),
            col('total_shipment_quantity', 'Total Shipment Quantity', 'numeric'),
            col('cargo_type', 'Cargo Type'),
            col('oil_type', 'Oil Type'),
            col('oil_source', 'Oil Source'),
            col('commodity_name', 'Commodity Name'),
            col('commodity_category', 'Commodity Category'),
            col('quality_specification', 'Quality Specification'),
            col('current_region', 'Current Region'),
            col('route_info', 'Route Info'),
            col('route_distance', 'Route Distance', 'numeric'),
            col('routedistance', 'Route Distance (text)'),
            col('arrival_date', 'Arrival Date'),
            col('departure_date', 'Departure Date'),
            col('payment_method', 'Payment Method'),
            col('payment_timing', 'Payment Timing'),
            col('delivery_method', 'Delivery Method'),
            col('delivery_terms', 'Delivery Terms'),
            col('shipping_type', 'Shipping Type'),
            col('contract_type', 'Contract Type'),
            col('source_company', 'Source Company'),
            col('source_refinery', 'Source Refinery'),
            col('target_refinery', 'Target Refinery'),
            col('voyage_status', 'Voyage Status'),
            col('voyage_notes', 'Voyage Notes'),
            col('crew_size', 'Crew Size', 'integer'),
            col('created_at', 'Created At'),
            col('updated_at', 'Updated At'),
            col('last_updated', 'Last Updated'),
        ],
        'ports': [
            col('id', 'ID', 'integer'),
            col('name', 'Port Name'),
            col('country', 'Country'),
            col('city', 'City'),
            col('region', 'Region'),
            col('lat', 'Latitude', 'numeric'),
            col('lng', 'Longitude', 'numeric'),
            col('address', 'Address'),
            col('port_type', 'Port Type'),
            col('type', 'Type'),
            col('status', 'Status'),
            col('description', 'Description'),
            col('facilities', 'Facilities'),
            col('services', 'Services'),
            col('email', 'Email'),
            col('phone', 'Phone'),
            col('website', 'Website'),
            col('operator', 'Operator'),
            col('owner', 'Owner'),
            col('port_authority', 'Port Authority'),
            col('capacity', 'Capacity', 'numeric'),
            col('timezone', 'Timezone'),
            col('created_at', 'Created At'),
            col('updated_at', 'Updated At'),
            col('last_updated', 'Last Updated'),
        ],
        'refineries': [
            col('id', 'ID'),
            col('name', 'Refinery Name'),
            col('country', 'Country'),
            col('city', 'City'),
            col('region', 'Region'),
            col('address', 'Address'),
            col('capacity', 'Capacity', 'numeric'),
            col('processing_capacity', 'Processing Capacity', 'numeric'),
            col('production_capacity', 'Production Capacity', 'numeric'),
            col('annual_throughput', 'Annual Throughput', 'numeric'),
            col('description', 'Description'),
            col('email', 'Email'),
            col('phone', 'Phone'),
            col('operator', 'Operator'),
            col('owner', 'Owner'),
            col('status', 'Status'),
            col('created_at', 'Created At'),
            col('last_updated', 'Last Updated'),
        ],
        'companies': [
            col('id', 'ID', 'integer'),
            col('name', 'Company Name'),
            col('company_type', 'Company Type'),
            col('country', 'Country'),
            col('city', 'City'),
            col('address', 'Address'),
            col('email', 'Email'),
            col('phone', 'Phone'),
            col('owner_name', 'Owner Name'),
            col('industry', 'Industry'),
            col('description', 'Description'),
            col('created_at', 'Created At'),
            col('updated_at', 'Updated At'),
        ],
        'brokers': [
            col('id', 'ID'),
            col('company_name', 'Company Name'),
            col('contact_person', 'Contact Person'),
            col('email', 'Email'),
            col('phone', 'Phone'),
            col('address', 'Address'),
            col('status', 'Status'),
            col('created_at', 'Created At'),
            col('updated_at', 'Updated At'),
        ],
    }
    return predefined.get(table_name.lower(), [])


def _build_schema_for_mapping() -> Dict[str, List[str]]:
    """Build {table: [col1, col2, ...]} for vessels, ports, refineries, companies. Brokers excluded."""
    tables = ['vessels', 'ports', 'refineries', 'companies']
    schema: Dict[str, List[str]] = {}
    for t in tables:
        cols = _get_predefined_table_columns(t)
        schema[t] = [c['name'] for c in cols]
    return schema


def _build_csv_schema_for_mapping() -> Dict[str, List[str]]:
    """Build {csv_id: [field1, field2, ...]} for available CSVs. Used by AI analysis on upload."""
    out: Dict[str, List[str]] = {}
    try:
        for d in list_csv_datasets():
            path = d.get("path") or os.path.join(DATA_DIR, d.get("filename", ""))
            if not os.path.exists(path):
                continue
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                reader = csv.DictReader(f)
                names = list(reader.fieldnames or [])
            out[d["id"]] = [n for n in names if n]
    except Exception as e:
        logger.warning(f"_build_csv_schema_for_mapping error: {e}")
    return out


# Rule-based placeholder -> (table, field) for upload-time mapping when OpenAI is unavailable.
# Extended for vessels, ports, companies. Field must exist in predefined columns.
_UPLOAD_FIELD_MAPPINGS: Dict[str, Tuple[str, str]] = {
    # vessels
    'imonumber': ('vessels', 'imo'), 'imo_number': ('vessels', 'imo'), 'imono': ('vessels', 'imo'), 'imo': ('vessels', 'imo'),
    'vesselname': ('vessels', 'name'), 'vessel_name': ('vessels', 'name'), 'shipname': ('vessels', 'name'), 'name': ('vessels', 'name'),
    'vesseltype': ('vessels', 'vessel_type'), 'vessel_type': ('vessels', 'vessel_type'), 'shiptype': ('vessels', 'vessel_type'),
    'flagstate': ('vessels', 'flag'), 'flag_state': ('vessels', 'flag'), 'flag': ('vessels', 'flag'),
    'mmsi': ('vessels', 'mmsi'), 'mmsinumber': ('vessels', 'mmsi'),
    'lengthoverall': ('vessels', 'length'), 'length_overall': ('vessels', 'length'), 'loa': ('vessels', 'length'), 'length': ('vessels', 'length'),
    'width': ('vessels', 'width'), 'beam': ('vessels', 'beam'), 'breadth': ('vessels', 'beam'), 'draft': ('vessels', 'draft'),
    'deadweight': ('vessels', 'deadweight'), 'dwt': ('vessels', 'deadweight'), 'grosstonnage': ('vessels', 'gross_tonnage'), 'gross_tonnage': ('vessels', 'gross_tonnage'),
    'ownername': ('vessels', 'owner_name'), 'owner_name': ('vessels', 'owner_name'), 'vesselowner': ('vessels', 'owner_name'), 'owner': ('vessels', 'owner_name'),
    'operatorname': ('vessels', 'operator_name'), 'operator_name': ('vessels', 'operator_name'), 'vesseloperator': ('vessels', 'operator_name'),
    'callsign': ('vessels', 'callsign'), 'built': ('vessels', 'built'), 'yearbuilt': ('vessels', 'built'), 'year_built': ('vessels', 'built'),
    'cargocapacity': ('vessels', 'cargo_capacity'), 'cargo_capacity': ('vessels', 'cargo_capacity'),
    'currentport': ('vessels', 'currentport'), 'loadingport': ('vessels', 'loading_port'), 'loading_port': ('vessels', 'loading_port'),
    'port': ('vessels', 'currentport'), 'country': ('vessels', 'flag'), 'email': ('vessels', 'email'), 'phone': ('vessels', 'phone'),
    'address': ('vessels', 'address'), 'companyname': ('vessels', 'owner_name'), 'company_name': ('vessels', 'owner_name'),
    'buyername': ('vessels', 'buyer_name'), 'buyer_name': ('vessels', 'buyer_name'),
    'sellername': ('vessels', 'seller_name'), 'seller_name': ('vessels', 'seller_name'),
    'cargotype': ('vessels', 'cargo_type'), 'cargo_type': ('vessels', 'cargo_type'),
    'oiltype': ('vessels', 'oil_type'), 'oil_type': ('vessels', 'oil_type'),
    'cargoquantity': ('vessels', 'cargo_quantity'), 'cargo_quantity': ('vessels', 'cargo_quantity'),
    'quantity': ('vessels', 'quantity'),
    # ports (common placeholders)
    'portname': ('ports', 'name'), 'port_name': ('ports', 'name'), 'loadingportname': ('ports', 'name'), 'portofloading': ('ports', 'name'),
    'portofdischarge': ('ports', 'name'), 'departureport': ('ports', 'name'),
    'destinationport': ('ports', 'name'), 'dischargeport': ('ports', 'name'), 'portloading': ('ports', 'name'), 'portdischarge': ('ports', 'name'),
    'portcountry': ('ports', 'country'), 'port_country': ('ports', 'country'), 'portcity': ('ports', 'city'), 'port_city': ('ports', 'city'),
    # companies
    'buyercompany': ('companies', 'name'), 'buyer_company': ('companies', 'name'), 'sellercompany': ('companies', 'name'), 'seller_company': ('companies', 'name'),
}


def _ai_suggest_placeholder_mapping(
    placeholders: List[str],
    schema: Dict[str, List[str]],
) -> Dict[str, Tuple[str, str]]:
    """
    Suggest (table, column) per placeholder using AI or rule-based fallback.
    Returns {placeholder: (table, column)}. Skips placeholders with no good match.
    """
    result: Dict[str, Tuple[str, str]] = {}

    def normalize_key(s: str) -> str:
        return re.sub(r'[^a-z0-9]', '', (s or '').lower())

    # Rule-based fallback: map to (table, field) using _UPLOAD_FIELD_MAPPINGS
    def rule_based() -> None:
        for ph in placeholders:
            key = normalize_key(ph)
            if not key:
                continue
            mapping = _UPLOAD_FIELD_MAPPINGS.get(key)
            if mapping:
                t, col = mapping
                if t in schema and col in (schema.get(t) or []):
                    result[ph] = (t, col)

    if OPENAI_ENABLED and openai_client and schema:
        flat: List[str] = []
        for t, cols in schema.items():
            for c in cols:
                flat.append(f"{t}.{c}")
        schema_str = ", ".join(flat[:200])
        ph_list = ", ".join(placeholders[:150])
        prompt = f"""You are a maritime document expert. Map each placeholder to the best database table.column.

Available table.column options: {schema_str}

Placeholders to map: {ph_list}

Rules:
- Prefer "vessels" for ship/vessel/IMO/owner/operator/dimensions/flag/cargo.
- Use "ports" for port names, countries, cities.
- Use "companies" for company names, emails, phones when vessel fields don't fit. Do NOT use brokers table.
- Return valid table.column only; if no good match, return NONE for that placeholder.

Return a JSON object: {{ "placeholder1": "table.column", "placeholder2": "NONE", ... }}. Use exact placeholder strings as keys. No other text."""

        try:
            r = openai_client.chat.completions.create(
                model='gpt-4o-mini',
                messages=[{'role': 'user', 'content': prompt}],
                max_tokens=2000,
                temperature=0.1,
            )
            raw = (r.choices[0].message.content or '').strip()
            json_match = re.search(r'\{[\s\S]*\}', raw)
            if json_match:
                try:
                    data = json.loads(json_match.group())
                    for ph, val in data.items():
                        if ph not in placeholders or not isinstance(val, str):
                            continue
                        val = val.strip().upper()
                        if val == 'NONE' or not val:
                            continue
                        if '.' in val:
                            t, col = val.split('.', 1)
                            t, col = t.strip().lower(), col.strip().lower()
                            if t in schema and col in (schema.get(t) or []):
                                result[ph] = (t, col)
                except json.JSONDecodeError:
                    pass
            if not result:
                rule_based()
        except Exception as e:
            logger.warning(f"AI mapping suggestion failed, using rule-based fallback: {e}")
            rule_based()
    else:
        rule_based()

    return result


def _ai_analyze_and_map_placeholders(
    placeholders: List[str],
    db_schema: Dict[str, List[str]],
    csv_schema: Dict[str, List[str]],
    doc_context: Optional[Dict[str, str]] = None,
) -> Dict[str, Dict]:
    """
    AI analyzes placeholders and chooses source (database|csv|random) plus mapping per placeholder.
    Returns {placeholder: {source, databaseTable, databaseField, csvId, csvField, csvRow, randomOption}}.
    Uses rule-based database-only fallback on OpenAI error or invalid output.
    """
    doc_context = doc_context or {}

    def rule_based_fallback() -> Dict[str, Dict]:
        suggested = _ai_suggest_placeholder_mapping(placeholders, db_schema)
        out: Dict[str, Dict] = {}
        for ph in placeholders:
            cfg: Dict = {
                'source': 'database',
                'databaseTable': '',
                'databaseField': '',
                'csvId': '',
                'csvField': '',
                'csvRow': 0,
                'randomOption': 'auto',
            }
            if ph in suggested:
                t, col = suggested[ph]
                cfg['databaseTable'] = t
                cfg['databaseField'] = col
            out[ph] = cfg
        return out

    if not (OPENAI_ENABLED and openai_client):
        return rule_based_fallback()

    db_flat: List[str] = []
    for t, cols in (db_schema or {}).items():
        for c in cols:
            db_flat.append(f"{t}.{c}")
    csv_flat: List[str] = []
    for cid, fields in (csv_schema or {}).items():
        for f in fields:
            csv_flat.append(f"csv:{cid}.{f}")

    db_str = ", ".join(db_flat[:250])
    csv_str = ", ".join(csv_flat[:150]) if csv_flat else "(none)"
    ph_list = ", ".join(placeholders[:120])

    prompt = f"""You are a maritime document expert. Analyse each placeholder and choose the best source.

**Sources:**
- **database**: vessel/ship/port/refinery/company data. Use table.column from the list.
- **csv**: data from uploaded CSV files (buyers, sellers, contacts, etc.). Use csvId.field from the list.
- **random**: no good match; we will generate realistic AI data at runtime.

**Database options (table.column):** {db_str}

**CSV options (csvId.field):** {csv_str}

**Placeholders to map:** {ph_list}

**Lookup order (follow strictly):**
1. **Vessels first**: IMO, vessel name, flag, owner, dimensions, cargo, port, etc. -> vessels table.
2. **Other tables**: Port names, company names, refinery -> ports, companies, refineries. (Do NOT use brokers table.)
3. **CSV**: Buyer/seller/contact/beneficiary/invoice party -> csv with matching column.
4. **Random**: ONLY when no database or CSV column fits. We will generate realistic AI data at runtime.

**Rules (follow strictly):**
1. **Buyer/seller data**: Placeholders that refer to BUYER or SELLER (name, company, email, address, phone, contact, etc.) MUST use **csv** when a matching CSV field exists. Example: BUYER_NAME, SELLER_COMPANY, BUYER_EMAIL → csv with buyer_name, seller_company, buyer_email, etc.
2. **Vessel/ship data**: IMO, vessel name, flag, port, cargo, etc. -> **database** (vessels, ports). Use table.column from the list.
3. **Company/port/refinery** (not buyer/seller): Use **database** when a matching table.column exists. NEVER use brokers table.
4. **Use csv** for any placeholder that clearly matches a CSV column (e.g. invoice party, beneficiary, bank details, contact person) when such CSV fields exist.
5. **Use random** only when no database or CSV fit.

Return a JSON object only. Each key is an exact placeholder string. Each value is one of:
{{"source": "database", "table": "vessels", "column": "imo"}}
{{"source": "csv", "csvId": "<id>", "csvField": "<field>"}}
{{"source": "random"}}

Use exact placeholder strings as keys. Only valid table.column and csvId.field from the lists above. No other text."""

    result: Dict[str, Dict] = {}
    try:
        r = openai_client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[{'role': 'user', 'content': prompt}],
            max_tokens=4000,
            temperature=0.1,
        )
        raw = (r.choices[0].message.content or '').strip()
        json_match = re.search(r'\{[\s\S]*\}', raw)
        if not json_match:
            return rule_based_fallback()
        try:
            data = json.loads(json_match.group())
        except json.JSONDecodeError as je:
            logger.warning(f"AI analyze-and-map invalid JSON, using rule-based fallback: {je}")
            return rule_based_fallback()
    except Exception as e:
        logger.warning(f"AI analyze-and-map failed, using rule-based fallback: {e}")
        return rule_based_fallback()

    def _find_ai_value(ph: str, d: dict) -> Optional[dict]:
        """Get AI value for placeholder, with fuzzy key match."""
        if not isinstance(d, dict):
            return None
        val = d.get(ph)
        if isinstance(val, dict):
            return val
        # Fuzzy match: normalize placeholder for key lookup
        ph_norm = re.sub(r'[^a-z0-9]', '', (ph or '').lower())
        for k, v in d.items():
            if isinstance(v, dict) and re.sub(r'[^a-z0-9]', '', (k or '').lower()) == ph_norm:
                return v
        return None

    # Brokers -> companies column mapping (brokers excluded from schema)
    _BROKERS_TO_COMPANIES = {'company_name': 'name', 'contact_person': 'owner_name', 'email': 'email', 'phone': 'phone', 'address': 'address'}

    for ph in placeholders:
        cfg: Dict = {
            'source': 'database',
            'databaseTable': '',
            'databaseField': '',
            'csvId': '',
            'csvField': '',
            'csvRow': 0,
            'randomOption': 'auto',
        }
        val = _find_ai_value(ph, data)
        if not isinstance(val, dict):
            result[ph] = cfg
            continue
        src = (val.get('source') or '').strip().lower()
        if src == 'random':
            cfg['source'] = 'random'
            cfg['randomOption'] = 'ai'
            result[ph] = cfg
            continue
        if src == 'csv':
            cid = (val.get('csvId') or '').strip()
            fld = (val.get('csvField') or '').strip()
            if cid in csv_schema and fld in (csv_schema.get(cid) or []):
                cfg['source'] = 'csv'
                cfg['csvId'] = cid
                cfg['csvField'] = fld
            else:
                cfg['source'] = 'random'
                cfg['randomOption'] = 'ai'
            result[ph] = cfg
            continue
        if src == 'database':
            t = (val.get('table') or '').strip().lower()
            col = (val.get('column') or '').strip().lower()
            # Remap brokers to companies (brokers table excluded)
            if t == 'brokers' and col:
                col = _BROKERS_TO_COMPANIES.get(col, col)
                t = 'companies'
            if t in db_schema and col in (db_schema.get(t) or []):
                cfg['source'] = 'database'
                cfg['databaseTable'] = t
                cfg['databaseField'] = col
            else:
                cfg['source'] = 'random'
                cfg['randomOption'] = 'ai'
            result[ph] = cfg
            continue
        result[ph] = cfg

    # Rescue: for placeholders that ended up as random, try rule-based database mapping
    suggested = _ai_suggest_placeholder_mapping(placeholders, db_schema)
    rescued = 0
    for ph in placeholders:
        if result.get(ph, {}).get('source') == 'random' and ph in suggested:
            t, col = suggested[ph]
            result[ph] = {
                'source': 'database',
                'databaseTable': t,
                'databaseField': col,
                'csvId': '',
                'csvField': '',
                'csvRow': 0,
                'randomOption': 'auto',
                'customValue': '',
            }
            rescued += 1
    if rescued:
        logger.info(f"AI mapping rescue: {rescued} placeholders remapped from random to database via rule-based")

    return result


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
    """
    Normalise placeholder identifiers for matching (case and punctuation insensitive).
    Handles spaces, underscores, hyphens, and special characters.
    """
    if not value:
        return ""
    
    # Strip and lowercase
    cleaned = value.strip().lower()
    
    # Replace all whitespace (spaces, tabs, newlines) with underscores
    cleaned = re.sub(r'\s+', '_', cleaned)
    
    # Replace hyphens and other common separators with underscores
    cleaned = re.sub(r'[-–—]+', '_', cleaned)
    
    # Remove all non-alphanumeric characters except underscores
    cleaned = re.sub(r'[^a-z0-9_]', '', cleaned)
    
    # Collapse multiple underscores into one
    cleaned = re.sub(r'_+', '_', cleaned)
    
    # Remove leading/trailing underscores
    cleaned = cleaned.strip('_')
    
    return cleaned


def resolve_placeholder_setting(
    template_settings: Dict[str, Dict], placeholder: str) -> Tuple[Optional[str], Optional[Dict]]:
    """
    Resolve a placeholder setting using multiple normalisation strategies.
    Returns the matched key and the setting dict.
    
    Matching strategies (in order of priority):
    1. Direct exact match
    2. Case-insensitive match
    3. Space/underscore/hyphen variant matches
    4. Normalized key comparison
    5. Fuzzy matching (contains/contained in)
    """
    if not template_settings or not placeholder:
        return None, None

    # Strategy 1: Direct exact match
    if placeholder in template_settings:
        return placeholder, template_settings[placeholder]

    # Strategy 2: Case-insensitive direct match
    placeholder_lower = placeholder.lower()
    for key in template_settings.keys():
        if key.lower() == placeholder_lower:
            return key, template_settings[key]

    # Strategy 3: Common variants (spaces, underscores, hyphens)
    variants = [
        placeholder.replace(' ', '_'),
        placeholder.replace('_', ' '),
        placeholder.replace('-', '_'),
        placeholder.replace('_', '-'),
        placeholder.replace(' ', '-'),
        placeholder.replace('-', ' '),
        placeholder.replace(' ', '_').lower(),
        placeholder.replace('_', ' ').lower(),
        placeholder.replace('-', '_').lower(),
        placeholder.replace('_', '-').lower(),
    ]
    
    # Remove duplicates while preserving order
    seen = set()
    unique_variants = []
    for variant in variants:
        if variant not in seen and variant != placeholder:
            seen.add(variant)
            unique_variants.append(variant)
    
    for variant in unique_variants:
        if variant in template_settings:
            return variant, template_settings[variant]
        # Also try case-insensitive variant match
        variant_lower = variant.lower()
        for key in template_settings.keys():
            if key.lower() == variant_lower:
                return key, template_settings[key]

    # Strategy 4: Normalised comparison
    target_norm = normalise_placeholder_key(placeholder)
    if target_norm:
        for key, value in template_settings.items():
            key_norm = normalise_placeholder_key(key)
            if key_norm == target_norm:
                return key, value

    # Strategy 5: Fuzzy matching (one contains the other, minimum 4 chars)
    if len(target_norm) >= 4:
        for key, value in template_settings.items():
            key_norm = normalise_placeholder_key(key)
            if key_norm and len(key_norm) >= 4:
                # Check if one is contained in the other
                if target_norm in key_norm or key_norm in target_norm:
                    # Additional check: ensure significant overlap (at least 70% of shorter string)
                    shorter = min(len(target_norm), len(key_norm))
                    longer = max(len(target_norm), len(key_norm))
                    if shorter >= longer * 0.7:
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
                    'id, title, description, file_name, placeholders, is_active, created_at, font_family, font_size'
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

                    # Get font settings - prioritize database, then metadata
                    font_family = record.get('font_family') or metadata_entry.get('font_family')
                    font_size = record.get('font_size') or metadata_entry.get('font_size')
                    
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
                            "font_family": font_family,
                            "font_size": font_size
                        },
                        "font_family": font_family,  # Also include at top level for easy access
                        "font_size": font_size,  # Also include at top level for easy access
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
            
            # Check if file exists before processing
            if not os.path.exists(file_path):
                logger.warning(f"Template file not found, skipping: {file_path}")
                continue
            
            try:
                file_size = os.path.getsize(file_path)
            except OSError:
                logger.warning(f"Could not get file size for {file_path}, skipping")
                continue
                
            try:
                created_at = datetime.fromtimestamp(
                    os.path.getctime(file_path)).isoformat()
            except OSError:
                logger.warning(f"Could not get creation time for {file_path}, using current time")
                created_at = datetime.now().isoformat()
                
            try:
                placeholders = extract_placeholders_from_docx(file_path)
            except Exception as ph_exc:
                logger.error(f"Failed to extract placeholders from {file_path}: {ph_exc}")
                # Continue with empty placeholders rather than failing completely
                placeholders = []
                
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
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(f"Error listing templates: {e}")
        import traceback
        logger.error(traceback.format_exc())
        # Return empty list instead of crashing - allows UI to still function
        return {"templates": [], "error": str(e), "warning": "Some templates could not be loaded"}


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

                # Get font settings - prioritize database, then metadata
                font_family = template_record.get('font_family') or metadata_entry.get('font_family')
                font_size = template_record.get('font_size') or metadata_entry.get('font_size')
                
                response = {
                    "id": str(template_record['id']),
                    "template_id": str(template_record['id']),  # Also include as template_id for consistency
                    "name": docx_name,
                    "title": metadata_entry.get('display_name') or template_record.get('title') or docx_name.replace('.docx', ''),
                    "file_name": docx_name.replace('.docx', ''),
                    "file_with_extension": docx_name,
                    "size": file_meta.get('file_size', 0),
                    "created_at": file_meta.get('uploaded_at') or template_record.get('created_at'),
                    "placeholders": placeholders,
                    "placeholder_count": len(placeholders),
                    "settings": placeholder_settings,
                    "description": metadata_entry.get('description') or template_record.get('description') or '',
                    "font_family": font_family,
                    "font_size": font_size,
                    "metadata": {
                        "display_name": metadata_entry.get('display_name') or template_record.get('title'),
                        "description": metadata_entry.get('description') or template_record.get('description') or '',
                        "font_family": font_family,
                        "font_size": font_size
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
        
        # Load placeholder settings - try multiple template name formats
        placeholder_settings_raw = read_json_file(PLACEHOLDER_SETTINGS_PATH, {})
        placeholder_settings = {}
        
        # Try to find settings using various template name formats
        candidates = [
            docx_name,
            normalize_template_name(docx_name, with_extension=True, for_key=False),
            normalize_template_name(docx_name, with_extension=False, for_key=False),
        ]
        
        for candidate in candidates:
            if candidate in placeholder_settings_raw:
                placeholder_settings = placeholder_settings_raw[candidate]
                logger.debug(f"Found placeholder settings for template using key: '{candidate}'")
                break
        
        # If still not found, try normalized key matching
        if not placeholder_settings:
            docx_key = normalize_template_name(docx_name, with_extension=False, for_key=True)
            for key in placeholder_settings_raw.keys():
                key_normalized = normalize_template_name(key, with_extension=False, for_key=True)
                if key_normalized == docx_key:
                    placeholder_settings = placeholder_settings_raw[key]
                    logger.debug(f"Found placeholder settings for template using normalized key: '{key}' -> '{docx_key}'")
                    break
        
        # Also try to load from Supabase if available
        if SUPABASE_ENABLED:
            template_record = resolve_template_record(docx_name)
            if template_record:
                supabase_settings = fetch_template_placeholders(template_record['id'], docx_name)
                # Merge: Supabase settings override disk settings
                placeholder_settings.update(supabase_settings)
                logger.debug(f"Merged Supabase placeholder settings for template {docx_name}")

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

@app.post("/templates/{template_id}/metadata")
async def update_template_metadata(
    request: Request,
    template_id: str,
    current_user: str = Depends(get_current_user)
):
    """Update template metadata (display name, description, fonts, plan assignments)."""
    try:
        body = await request.json()
        payload = body if isinstance(body, dict) else {}
        display_name = (payload.get('display_name') or payload.get('name') or "").strip()
        description = (payload.get('description') or "").strip()
        font_family = (payload.get('font_family') or "").strip() or None
        font_size_raw = payload.get('font_size')
        font_size = None
        if font_size_raw not in (None, ""):
            try:
                font_size = int(font_size_raw)
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="font_size must be an integer")
        
        # Only touch plan permissions when explicitly sent (Plans tab). Metadata-only save must not wipe them.
        plan_ids_raw = payload.get('plan_ids') if 'plan_ids' in payload else None
        plan_ids = plan_ids_raw if isinstance(plan_ids_raw, list) else []
        
        # Convert plan_tiers to plan_ids (UUIDs) if needed
        resolved_plan_ids = []
        if plan_ids and SUPABASE_ENABLED:
            for plan_identifier in plan_ids:
                if not plan_identifier:
                    continue
                try:
                    # Try to parse as UUID first
                    plan_uuid = uuid.UUID(str(plan_identifier))
                    resolved_plan_ids.append(str(plan_uuid))
                except (ValueError, TypeError):
                    # Not a UUID, treat as plan_tier and look up plan_id
                    try:
                        plan_res = supabase.table('subscription_plans').select('id').eq('plan_tier', str(plan_identifier)).eq('is_active', True).limit(1).execute()
                        if plan_res.data and len(plan_res.data) > 0:
                            resolved_plan_ids.append(str(plan_res.data[0]['id']))
                            logger.debug(f"Converted plan_tier '{plan_identifier}' to plan_id: {plan_res.data[0]['id']}")
                        else:
                            logger.warning(f"Could not find plan with plan_tier: {plan_identifier}")
                    except Exception as e:
                        logger.warning(f"Error looking up plan for '{plan_identifier}': {e}")

        plan_ids = resolved_plan_ids  # Use resolved UUIDs

        # Update Supabase metadata when available
        template_record = None
        if SUPABASE_ENABLED:
            # Try to resolve by template_id (UUID) first
            try:
                template_uuid = uuid.UUID(str(template_id))
                response = supabase.table('document_templates').select('id, title, description, file_name, font_family, font_size').eq('id', str(template_uuid)).limit(1).execute()
                if response.data:
                    template_record = response.data[0]
            except (ValueError, TypeError):
                # If not a UUID, try by file_name
                template_record = resolve_template_record(template_id)
            
            if template_record:
                template_id_uuid = template_record['id']
                update_data = {}
                if display_name:
                    update_data['title'] = display_name
                    logger.info(f"Updating Supabase title for template {template_id_uuid} to: {display_name}")
                if description:
                    update_data['description'] = description
                    logger.info(f"Updating Supabase description for template {template_id_uuid}")
                if font_family is not None:
                    update_data['font_family'] = font_family
                    logger.info(f"Updating Supabase font_family for template {template_id_uuid} to: {font_family}")
                if font_size is not None:
                    update_data['font_size'] = font_size
                    logger.info(f"Updating Supabase font_size for template {template_id_uuid} to: {font_size}")
                
                if update_data:
                    try:
                        result = supabase.table('document_templates').update(update_data).eq('id', template_id_uuid).execute()
                        if result.data:
                            logger.info(f"Successfully updated Supabase metadata for template {template_id_uuid}: {update_data}")
                        else:
                            logger.warning(f"Supabase update returned no data for template {template_id_uuid}")
                    except Exception as exc:
                        logger.error(f"Failed to update template metadata in Supabase: {exc}")
                        import traceback
                        logger.error(traceback.format_exc())
                
                # Update plan assignments only when plan_ids was explicitly sent
                if 'plan_ids' in payload:
                    try:
                        supabase.table('plan_template_permissions').delete().eq('template_id', template_id_uuid).execute()
                        if resolved_plan_ids:
                            permission_rows = []
                            for plan_id in resolved_plan_ids:
                                if plan_id:  # Only add non-empty plan IDs
                                    permission_rows.append({
                                        'plan_id': str(plan_id),
                                        'template_id': str(template_id_uuid),
                                        'can_download': True,
                                        'max_downloads_per_template': None  # Per-template limit (NULL = unlimited, use plan default)
                                    })
                            
                            if permission_rows:
                                permissions_response = supabase.table('plan_template_permissions').insert(permission_rows).execute()
                                if getattr(permissions_response, "error", None):
                                    logger.error(f"Plan permissions insert error: {permissions_response.error}")
                                else:
                                    logger.info(f"Updated plan permissions for {len(permission_rows)} plans")
                    except Exception as perm_exc:
                        logger.error(f"Error updating plan permissions: {perm_exc}")
            else:
                raise HTTPException(status_code=404, detail=f"Template not found: {template_id}")

        # Also update local metadata file if template_record has file_name
        if template_record and template_record.get('file_name'):
            docx_name = ensure_docx_filename(template_record['file_name'])
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
            "template_id": str(template_record['id']) if template_record else template_id,
            "template": template_record.get('file_name') if template_record else template_id,
            "metadata": {
                "display_name": display_name or None,
                "description": description or None,
                "font_family": font_family,
                "font_size": font_size
            },
            "plan_ids": plan_ids
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
    plan_ids: Optional[str] = Form(None),  # JSON array string of plan IDs
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

        # Parse font settings
        font_family_value = (font_family or "").strip() or None
        font_size_value: Optional[int] = None
        if font_size is not None and font_size != "":
            try:
                font_size_value = int(font_size)
            except ValueError:
                warnings.append("Invalid font size value; ignored")
                font_size_value = None

        # Parse plan_ids (JSON array string)
        plan_ids_list = []
        if plan_ids:
            try:
                plan_ids_list = json.loads(plan_ids)
                if not isinstance(plan_ids_list, list):
                    plan_ids_list = []
            except (json.JSONDecodeError, TypeError):
                warnings.append("Invalid plan_ids format; ignoring")
                plan_ids_list = []

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
                
                # Add font settings to database if provided
                if font_family_value:
                    template_payload['font_family'] = font_family_value
                if font_size_value is not None:
                    template_payload['font_size'] = font_size_value

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

                    # Create plan_template_permissions entries for selected plans
                    if plan_ids_list and template_id:
                        try:
                            # Delete existing permissions first
                            supabase.table('plan_template_permissions').delete().eq('template_id', template_id).execute()
                            
                            # Insert new permissions
                            permission_rows = []
                            for plan_id in plan_ids_list:
                                if plan_id:  # Only add non-empty plan IDs
                                    permission_rows.append({
                                        'plan_id': str(plan_id),
                                        'template_id': str(template_id),
                                        'can_download': True,
                                        'max_downloads_per_template': None  # Per-template limit (NULL = unlimited, use plan default)
                                    })
                            
                            if permission_rows:
                                permissions_response = supabase.table('plan_template_permissions').insert(permission_rows).execute()
                                if getattr(permissions_response, "error", None):
                                    warnings.append("Failed to set plan permissions")
                                    logger.error(f"Plan permissions insert error: {permissions_response.error}")
                                else:
                                    logger.info(f"Set plan permissions for {len(permission_rows)} plans")
                        except Exception as perm_exc:
                            warnings.append(f"Failed to set plan permissions: {str(perm_exc)}")
                            logger.error(f"Error setting plan permissions: {perm_exc}")
                else:
                    warnings.append("Supabase metadata sync failed; template served from local storage")
                    logger.warning("Unable to retrieve template metadata after Supabase upsert")
            except Exception as exc:
                warnings.append("Supabase sync failed; template available locally")
                logger.error(f"Failed to store template in Supabase: {exc}")

        # AI analysis on upload: choose source (database|csv|random) and mapping per placeholder, persist.
        mapped_count = 0
        database_count = 0
        csv_count = 0
        random_count = 0
        if placeholders:
            db_schema = _build_schema_for_mapping()
            csv_schema = _build_csv_schema_for_mapping()
            analyzed = _ai_analyze_and_map_placeholders(placeholders, db_schema, csv_schema)
            default_settings: Dict[str, Dict] = {}
            for ph in placeholders:
                cfg = (analyzed.get(ph) or {}).copy()
                cfg.setdefault('source', 'database')
                cfg.setdefault('databaseTable', '')
                cfg.setdefault('databaseField', '')
                cfg.setdefault('csvId', '')
                cfg.setdefault('csvField', '')
                cfg.setdefault('csvRow', 0)
                cfg.setdefault('randomOption', 'auto')
                if 'customValue' not in cfg:
                    cfg['customValue'] = ''
                default_settings[ph] = cfg
                if cfg.get('source') == 'database':
                    database_count += 1
                elif cfg.get('source') == 'csv':
                    csv_count += 1
                else:
                    random_count += 1
            mapped_count = database_count + csv_count + random_count
            # Supabase template_placeholders uses UUID FK; only upsert when we have template_id.
            if template_id:
                upsert_template_placeholders(str(template_id), default_settings, docx_filename)
                logger.info(f"AI mapping created: db={database_count} csv={csv_count} random={random_count} (template_id={template_id})")
            else:
                # No template_id (e.g. Supabase sync failed): persist to disk only so editor can still load.
                placeholder_settings = read_json_file(PLACEHOLDER_SETTINGS_PATH, {})
                key = ensure_docx_filename(docx_filename)
                placeholder_settings[key] = default_settings
                write_json_atomic(PLACEHOLDER_SETTINGS_PATH, placeholder_settings)
                logger.warning(f"AI mapping saved to disk only (no template_id): db={database_count} csv={csv_count} random={random_count} key={key}")
                warnings.append("AI mapping saved to disk only (no Supabase template_id). Open editor by template name to see mappings.")

        # Remove template from deleted list if it was previously deleted (re-upload scenario)
        unmark_template_as_deleted(docx_filename)
        unmark_template_as_deleted(safe_filename)
        if title_value and title_value != inferred_title:
            unmark_template_as_deleted(title_value)
        logger.info(f"Removed {docx_filename} from deleted templates list (if present)")

        # Persist metadata locally (font settings already parsed above)
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
        if placeholders:
            response_payload["mapping_created"] = True
            response_payload["mapped_count"] = mapped_count
            response_payload["ai_analysis"] = True
            response_payload["database_count"] = database_count if placeholders else 0
            response_payload["csv_count"] = csv_count if placeholders else 0
            response_payload["random_count"] = random_count if placeholders else 0
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
        
        # If template not in DB and no file deleted yet: try matching by normalized name (list dir)
        file_exists = any(os.path.exists(os.path.join(TEMPLATES_DIR, var)) for var in set(file_variations) if var)
        if not template_id and not deleted_local and not file_exists:
            try:
                target_key = _normalize_for_match(template_name)
                target_key_docx = _normalize_for_match(docx_name)
                for f in os.listdir(TEMPLATES_DIR):
                    if not f.lower().endswith(".docx"):
                        continue
                    p = os.path.join(TEMPLATES_DIR, f)
                    if not os.path.isfile(p):
                        continue
                    k = _normalize_for_match(f)
                    if k and (k == target_key or k == target_key_docx):
                        try:
                            os.remove(p)
                            logger.info(f"Deleted local template file (normalized match): {f}")
                            deleted_local = True
                            break
                        except Exception as exc:
                            logger.warning(f"Failed to delete matched file {f}: {exc}")
            except Exception as exc:
                logger.warning(f"Dir-listing fallback for delete failed: {exc}")

        # Never 404 on delete: always mark deleted + clean config so template disappears from list
        if not deleted_local and not template_id:
            logger.info(f"Template not found in DB or as file; marking deleted and cleaning config: {template_name}")
        elif not deleted_local and template_id:
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
        elif SUPABASE_ENABLED and not supabase_deleted and template_id:
            logger.warning(f"⚠ Template deleted locally but may not have been deleted from Supabase: {docx_name}")

        forgotten = not template_id and not deleted_local
        response = {
            "success": True,
            "message": (
                f"Template {docx_name} marked as deleted and config cleaned (it was not in DB or as a file)."
                if forgotten
                else f"Template {docx_name} deleted completely"
            ),
            "deleted_from_supabase": supabase_deleted if SUPABASE_ENABLED else None,
        }
        if forgotten:
            response["forgotten"] = True
        if warnings:
            response["warnings"] = warnings
        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting template: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.options("/api/templates/{template_name}")
async def options_delete_template_api(request: Request, template_name: str):
    """CORS preflight for DELETE /api/templates/{template_name} (VPS Nginx /api prefix)."""
    return Response(
        status_code=204,
        headers=_cors_preflight_headers(request, "DELETE, OPTIONS"),
    )


@app.delete("/api/templates/{template_name}")
async def delete_template_api(
    template_name: str,
    current_user: str = Depends(get_current_user),
):
    """Delete template (same as /templates/{name}) for Nginx /api-prefixed requests."""
    return await delete_template(template_name, current_user)


@app.post("/templates/{template_id}/ai-scan-placeholders")
async def ai_scan_placeholders(template_id: str):
    """AI scan all placeholders for a template, map to database/CSV/random, return settings.
    Used by CMS editor 'AI Scan' button. No auth required (CMS editor)."""
    try:
        template_record = resolve_template_record(template_id)
        if not template_record:
            raise HTTPException(status_code=404, detail=f"Template not found: {template_id}")
        placeholders = list(template_record.get("placeholders") or [])
        if not placeholders:
            return {"success": True, "settings": {}, "message": "No placeholders to scan"}
        db_schema = _build_schema_for_mapping()
        csv_schema = _build_csv_schema_for_mapping()
        analyzed = _ai_analyze_and_map_placeholders(placeholders, db_schema, csv_schema)
        settings: Dict[str, Dict] = {}
        for ph in placeholders:
            cfg = (analyzed.get(ph) or {}).copy()
            cfg.setdefault("source", "database")
            cfg.setdefault("databaseTable", "")
            cfg.setdefault("databaseField", "")
            cfg.setdefault("csvId", "")
            cfg.setdefault("csvField", "")
            cfg.setdefault("csvRow", 0)
            cfg.setdefault("randomOption", "auto")
            cfg.setdefault("customValue", "")
            settings[ph] = cfg
        logger.info(f"AI scan placeholders for template {template_id}: {len(settings)} mapped")
        return {"success": True, "settings": settings}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"AI scan placeholders error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/templates/{template_id}/ai-scan-placeholders")
async def ai_scan_placeholders_api(template_id: str):
    """AI scan placeholders (same as POST /templates/{id}/ai-scan-placeholders) for Nginx /api prefix."""
    return await ai_scan_placeholders(template_id)


@app.post("/templates/forget")
async def forget_template(
    request: Request,
    current_user: str = Depends(get_current_user),
):
    """Remove an orphan template by name: mark deleted, clean placeholder_settings, metadata, plans.
    Use when a template is not in DB, causes problems, and normal delete fails."""
    try:
        body = await request.json()
        name = (body.get("name") or body.get("template_name") or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="Missing 'name' or 'template_name' in JSON body")

        docx_name = ensure_docx_filename(name)
        removed_settings = False
        removed_meta = False

        placeholder_settings = read_json_file(PLACEHOLDER_SETTINGS_PATH, {})
        if placeholder_settings:
            if docx_name in placeholder_settings:
                placeholder_settings.pop(docx_name, None)
                removed_settings = True
            else:
                nk = normalise_template_key(docx_name)
                for key in list(placeholder_settings.keys()):
                    if normalise_template_key(key) == nk:
                        placeholder_settings.pop(key, None)
                        removed_settings = True
                        break
            if removed_settings:
                write_json_atomic(PLACEHOLDER_SETTINGS_PATH, placeholder_settings)

        metadata = load_template_metadata()
        if metadata:
            if docx_name in metadata:
                metadata.pop(docx_name, None)
                removed_meta = True
            else:
                nk = normalise_template_key(docx_name)
                for key in list(metadata.keys()):
                    if normalise_template_key(key) == nk:
                        metadata.pop(key, None)
                        removed_meta = True
                        break
            if removed_meta:
                save_template_metadata(metadata)

        plans = read_json_file(PLANS_PATH, {})
        plan_updated = False
        if isinstance(plans, dict) and plans:
            no_ext = docx_name.replace(".docx", "")
            for _plan_tier, plan_data in plans.items():
                if not isinstance(plan_data, dict) or "can_download" not in plan_data:
                    continue
                can = plan_data.get("can_download", [])
                if not isinstance(can, list):
                    continue
                orig = len(can)
                can = [t for t in can if t and ensure_docx_filename(t) != docx_name and t != no_ext]
                if len(can) != orig:
                    plan_data["can_download"] = can
                    plan_updated = True
            if plan_updated:
                write_json_atomic(PLANS_PATH, plans)

        for v in [docx_name, name, docx_name.lower(), docx_name.upper()]:
            if v:
                mark_template_as_deleted(v)

        logger.info(f"Forget template completed: {name} (placeholder_settings={removed_settings}, metadata={removed_meta}, plans={plan_updated})")
        return {
            "success": True,
            "message": f"Template '{name}' forgotten (marked deleted, config cleaned)",
            "removed_from_placeholder_settings": removed_settings,
            "removed_from_metadata": removed_meta,
            "plans_updated": plan_updated,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error forgetting template: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/templates/forget")
async def forget_template_api(
    request: Request,
    current_user: str = Depends(get_current_user),
):
    """Forget template (same as POST /templates/forget) for Nginx /api prefix."""
    return await forget_template(request, current_user)


@app.get("/api/database-tables")
async def get_database_tables_api(request: Request):
    """CMS editor: /api/database-tables (Nginx forwards with /api prefix)."""
    return await get_database_tables(request)


@app.get("/api/database-tables/{table_name}/columns")
async def get_database_table_columns_api(table_name: str, request: Request):
    """CMS editor: /api/database-tables/{table_name}/columns."""
    return await get_database_table_columns(table_name, request)


@app.get("/api/csv-files")
async def get_csv_files_api(request: Request):
    """CMS editor: /api/csv-files."""
    return await get_csv_files(request)


@app.get("/api/csv-fields/{csv_id}")
async def get_csv_fields_api(csv_id: str, request: Request):
    """CMS editor: /api/csv-fields/{csv_id}."""
    return await get_csv_fields(csv_id, request)


@app.get("/api/plans-db")
async def get_plans_db_api():
    """CMS editor: /api/plans-db."""
    return await get_plans_db()


@app.get("/api/plans")
async def get_plans_api():
    """CMS editor fallback: /api/plans."""
    return await get_plans()


# ============================================================================
# STEP 5: PLACEHOLDER SETTINGS API (JSON-backed)
# ============================================================================

@app.get("/placeholder-settings")
@app.get("/cmsplaceholder-settings")  # Alias for nginx rewrite compatibility
async def get_placeholder_settings(
    request: Request,
    template_name: Optional[str] = None,
    template_id: Optional[str] = None
):
    """Get placeholder settings (all or per-template) - allows unauthenticated access for CMS editor"""
    try:
        if SUPABASE_ENABLED and (template_name or template_id):
            template_record = None
            search_identifier = template_id or template_name
            logger.info(f"🔍 Looking up placeholder settings for template_id={template_id}, template_name={template_name}")
            
            if template_id:
                template_record = resolve_template_record(template_id)
                if template_record:
                    logger.info(f"✅ Found template by ID: {template_id} -> {template_record.get('file_name')}")
                else:
                    logger.warning(f"⚠️ Template not found by ID: {template_id}")
            
            if not template_record and template_name:
                template_record = resolve_template_record(template_name)
                if template_record:
                    logger.info(f"✅ Found template by name: {template_name} -> {template_record.get('file_name')}")
                else:
                    logger.warning(f"⚠️ Template not found by name: {template_name}")
            
            if not template_record:
                error_msg = f"Template not found: template_id={template_id}, template_name={template_name}"
                logger.error(f"❌ {error_msg}")
                raise HTTPException(status_code=404, detail=error_msg)
            
            settings = fetch_template_placeholders(template_record['id'], template_record.get('file_name'))
            
            # Preserve explicit 'random' and 'csv'. Only default to 'database' when source is missing or empty.
            for placeholder, setting in settings.items():
                s = setting.get('source')
                if s is None or (isinstance(s, str) and not s.strip()):
                    setting['source'] = 'database'
                    logger.debug(f"🔧 Defaulted placeholder '{placeholder}' source to 'database' (was missing)")
            
            logger.info(f"✅ Loaded {len(settings)} placeholder settings for template {template_record.get('file_name')}")
            return {
                "template": template_record.get('file_name') or template_name,
                "settings": settings,
                "template_id": str(template_record['id'])
            }

        if SUPABASE_ENABLED and not template_name:
            response = supabase.table('template_placeholders').select(
                'template_id, placeholder, source, custom_value, database_table, database_field, csv_id, csv_field, csv_row, random_option'
            ).execute()

            aggregated: Dict[str, Dict[str, Dict]] = {}
            for row in response.data or []:
                template_id = str(row['template_id'])
                source = row.get('source')
                if source is None or (isinstance(source, str) and not source.strip()):
                    source = 'database'
                else:
                    source = str(source).strip()
                aggregated.setdefault(template_id, {})[row['placeholder']] = {
                    'source': source,
                    'customValue': row.get('custom_value') or '',
                    'databaseTable': row.get('database_table') or '',
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

@app.post("/placeholder-settings/fix-random-defaults")
async def fix_random_defaults(current_user: str = Depends(get_current_user)):
    """Fix existing placeholder settings that have source='random' to source='database'."""
    if not SUPABASE_ENABLED:
        raise HTTPException(status_code=503, detail="Supabase not available")
    
    try:
        # Find all placeholders with source='random' or null/empty
        response = supabase.table('template_placeholders').select('template_id, placeholder, source').execute()
        
        fixed_count = 0
        for row in response.data or []:
            source = row.get('source')
            if not source or source == '' or source == 'random':
                template_id = row['template_id']
                placeholder = row['placeholder']
                supabase.table('template_placeholders').update({
                    'source': 'database'
                }).eq('template_id', template_id).eq('placeholder', placeholder).execute()
                fixed_count += 1
        
        return {"success": True, "fixed_count": fixed_count, "message": f"Fixed {fixed_count} placeholder settings to use 'database' as default"}
    except Exception as e:
        logger.error(f"Failed to fix random defaults: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fix defaults: {str(e)}")


@app.post("/placeholder-settings")
@app.post("/cmsplaceholder-settings")  # Alias for nginx rewrite compatibility
async def save_placeholder_settings(request: Request):
    """Save placeholder settings for a template"""
    # Allow unauthenticated access for CMS editor
    try:
        data = await request.json()
        template_name = data.get('template_name')
        template_id_override = data.get('template_id')
        new_settings = data.get('settings', {})
        
        logger.info(f"💾 Saving placeholder settings: template_id={template_id_override}, template_name={template_name}, settings_count={len(new_settings)}")
        
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

            # Normalise payload to Supabase schema then upsert. Preserve explicit random/csv.
            sanitised_settings: Dict[str, Dict] = {}
            for placeholder, cfg in new_settings.items():
                if not placeholder:
                    continue
                source = cfg.get('source')
                if source is None or (isinstance(source, str) and not source.strip()):
                    source = 'database'
                    logger.debug(f"Defaulted placeholder '{placeholder}' source to 'database' (was missing)")
                else:
                    source = str(source).strip()
                
                sanitised_settings[placeholder] = {
                    'source': source,
                    'customValue': str(cfg.get('customValue', '')).strip() if cfg.get('customValue') else '',
                    'databaseTable': str(cfg.get('databaseTable', '')).strip() if cfg.get('databaseTable') else '',
                    'databaseField': str(cfg.get('databaseField', '')).strip() if cfg.get('databaseField') else '',
                    'csvId': str(cfg.get('csvId', '')).strip() if cfg.get('csvId') else '',
                    'csvField': str(cfg.get('csvField', '')).strip() if cfg.get('csvField') else '',
                    'csvRow': int(cfg.get('csvRow', 0)) if cfg.get('csvRow') is not None else 0,
                    'randomOption': cfg.get('randomOption', 'auto') or 'auto'
                }
                logger.debug(f"Sanitized setting for '{placeholder}': source={sanitised_settings[placeholder]['source']}, databaseTable={sanitised_settings[placeholder]['databaseTable']}, databaseField={sanitised_settings[placeholder]['databaseField']}, csvId={sanitised_settings[placeholder]['csvId']}")

            logger.info(f"💾 Saving {len(sanitised_settings)} placeholder settings for template {template_id} ({template_record.get('file_name')})")
            logger.info(f"   Sample settings: {list(sanitised_settings.items())[:3]}")
            
            upsert_template_placeholders(template_id, sanitised_settings, template_record.get('file_name'))
            
            logger.info(f"✅ Successfully saved placeholder settings to Supabase")

            # Return latest snapshot
            refreshed = fetch_template_placeholders(template_id, template_record.get('file_name'))
            logger.info(f"✅ Verified: Loaded {len(refreshed)} settings back from Supabase")
            return {"success": True, "template": template_name, "template_id": str(template_id), "settings": refreshed, "saved_count": len(sanitised_settings)}

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
                                        'can_download': True,
                                        'max_downloads_per_template': None  # Per-template limit (NULL = unlimited, use plan default)
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

@app.get("/templates/{template_identifier}/plan-info")
async def get_template_plan_info(template_identifier: str):
    """Get plan information for a specific template (which plans can download it)"""
    try:
        if not supabase:
            return {
                "success": True,
                "template_name": template_identifier,
                "plans": [],
                "source": "json_fallback"
            }
        
        # Try to resolve by template_id (UUID) first
        template_id = None
        template_record = None
        
        try:
            template_uuid = uuid.UUID(str(template_identifier))
            template_res = supabase.table('document_templates').select('id, file_name').eq('id', str(template_uuid)).eq('is_active', True).limit(1).execute()
            if template_res.data:
                template_record = template_res.data[0]
                template_id = template_record['id']
        except (ValueError, TypeError):
            # Not a UUID, try by file_name
            template_file_name = template_identifier.replace('.docx', '')
            template_res = supabase.table('document_templates').select('id, file_name').eq('file_name', template_file_name).eq('is_active', True).limit(1).execute()
            if template_res.data:
                template_record = template_res.data[0]
                template_id = template_record['id']
        
        if not template_id:
            raise HTTPException(status_code=404, detail="Template not found")
        
        # Get all plans that can download this template (include max_downloads_per_template)
        permissions_res = supabase.table('plan_template_permissions').select(
            'plan_id, can_download, max_downloads_per_template'
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
                "template_id": str(template_id),
                "template_name": template_record.get('file_name') if template_record else template_identifier,
                "plans": unique_plans,
                "plan_name": unique_plans[0]['plan_name'] if unique_plans else None,
                "plan_tier": unique_plans[0]['plan_tier'] if unique_plans else None,
                "source": "database"
            }
        else:
            return {
                "success": True,
                "template_id": str(template_id),
                "template_name": template_record.get('file_name') if template_record else template_identifier,
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
            if not template_ids:
                return {"success": True, "templates": [], "source": "database"}

            details_res = supabase.table('document_templates').select('id, title, description, file_name, placeholders, font_family, font_size').in_('id', template_ids).execute()
            details_map = {d['id']: d for d in (details_res.data or [])}

            # Get user's plan info (subscribers.subscription_tier)
            user_plan_info = None
            try:
                user_res = supabase.table('subscribers').select('subscription_tier').eq('user_id', user_id).limit(1).execute()
                if user_res.data and user_res.data[0]:
                    plan_tier = user_res.data[0].get('subscription_tier')
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
                
                # Get display_name - prioritize metadata display_name, then Supabase title, then file_name
                display_name = (
                    metadata_entry.get('display_name') or 
                    details.get('title') or 
                    (file_name.replace('.docx', '') if file_name else 'Unknown')
                )
                
                # Get title (fallback to display_name)
                template_title = details.get('title') or display_name
                
                # Get font settings - prioritize database, then metadata
                font_family = details.get('font_family') or metadata_entry.get('font_family')
                font_size = details.get('font_size') or metadata_entry.get('font_size')
                
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
                                logger.info(f"Found plan for locked template {template_id}: {plan_name} (tier: {plan_tier_val})")
                    except Exception as e:
                        logger.warning(f"Could not fetch plan info for template {template_id}: {e}")
                
                enhanced_templates.append({
                    "id": str(template_id),
                    "template_id": str(template_id),  # Also include as template_id for consistency
                    "name": display_name,  # Use display_name as primary name
                    "title": template_title,
                    "file_name": file_name,
                    "description": description,
                    "font_family": font_family,
                    "font_size": font_size,
                    "placeholders": details.get('placeholders', []),
                    "can_download": t['can_download'],
                    "max_downloads": t['max_downloads'],
                    "current_downloads": t['current_downloads'],
                    "remaining_downloads": t['remaining_downloads'],
                    "plan_name": plan_name,  # Always include plan_name (even if None)
                    "plan_tier": plan_tier_val,
                    "metadata": {
                        "display_name": display_name,  # Always include display_name
                        "description": description or metadata_entry.get('description', ''),  # Always include description
                        "font_family": font_family,
                        "font_size": font_size
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
        logger.error("Error getting user downloadable templates: %s\n%s", e, traceback.format_exc())
        return {"success": True, "templates": [], "source": "database"}

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

def _resolve_csv_dataset(csv_id: str):
    """Resolve csv_id to a dataset from list_csv_datasets (case-insensitive match). Use actual path."""
    csv_id = (csv_id or "").strip()
    if not csv_id:
        return None
    csv_lower = csv_id.lower()
    for d in list_csv_datasets():
        if d["id"].lower() == csv_lower and os.path.exists(d["path"]):
            return d
    return None


@app.get("/csv-files")
async def get_csv_files(request: Request):
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
        logger.info(f"Returning {len(csv_files)} CSV files")
        return {"success": True, "csv_files": csv_files}
    except Exception as e:
        logger.error(f"Error getting CSV files: {e}")
        return {"success": True, "csv_files": []}

@app.get("/csv-fields/{csv_id}")
async def get_csv_fields(csv_id: str, request: Request):
    """Get columns/fields from a CSV file. Resolves csv_id via list (case-insensitive, actual path)."""
    try:
        dataset = _resolve_csv_dataset(csv_id)
        if not dataset:
            raise HTTPException(status_code=404, detail="CSV file not found")

        with open(dataset["path"], 'r', encoding='utf-8', errors='replace') as f:
            reader = csv.DictReader(f)
            names = list(reader.fieldnames or [])
        fields = [{"name": n, "label": n.replace('_', ' ').title()} for n in names]

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
            logger.debug(f"Found CSV '{csv_id}' in metadata, filename: {filename}")
        else:
            # Try to find in metadata by case-insensitive match
            csv_id_lower = csv_id.lower()
            for key in metadata.keys():
                if key.lower() == csv_id_lower:
                    filename = dataset_id_to_filename(key)
                    logger.debug(f"Found CSV '{csv_id}' in metadata (case-insensitive match with '{key}'), filename: {filename}")
                    break
            
            # Fallback to legacy hardcoded mapping for backward compatibility
            if not filename:
                csv_mapping = {
                    "buyers_sellers": "buyers_sellers_data_220.csv",
                    "buyers_sellers_data_220": "buyers_sellers_data_220.csv",  # Add direct mapping
                    "bank_accounts": "bank_accounts.csv",
                    "icpo": "icpo_section4_6_data_230.csv",
                    "icpo_section4_6_data_230": "icpo_section4_6_data_230.csv"  # Add direct mapping
                }
                filename = csv_mapping.get(csv_id)
                if filename:
                    logger.debug(f"Found CSV '{csv_id}' in legacy mapping, filename: {filename}")
        
        if not filename:
            logger.error(f"❌ CSV dataset '{csv_id}' not found in metadata or legacy mapping")
            logger.error(f"   Available datasets in metadata: {list(metadata.keys())[:10]}...")
            logger.error(f"   💡 TIP: Check if csvId in CMS matches dataset ID in data_sources.json")
            return None
        
        file_path = os.path.join(DATA_DIR, filename)
        if not os.path.exists(file_path):
            logger.error(f"❌ CSV file not found: {file_path}")
            logger.error(f"   💡 TIP: Check if CSV file exists in {DATA_DIR} directory")
            return None
        
        # Read CSV data
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            
            if not rows:
                logger.warning(f"⚠️  CSV file '{filename}' is empty (no data rows)")
                return None
            
            if row_index < 0:
                row_index = 0
            if row_index < len(rows):
                logger.debug(f"✅ Retrieved CSV data from {csv_id}[{row_index}]: {list(rows[row_index].keys())[:5]}...")
                return rows[row_index]
            else:
                logger.error(f"❌ Row index {row_index} out of range for CSV {csv_id} (file has {len(rows)} rows, requested row {row_index})")
                logger.error(f"   💡 TIP: Check csvRow in CMS - valid range is 0 to {len(rows)-1}")
        
        return None
    except Exception as e:
        logger.error(f"❌ Error reading CSV data for '{csv_id}' at row {row_index}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None

# ============================================================================
# STEP 7: DOCUMENT GENERATION (with PDF export)
# ============================================================================

def get_data_from_table(table_name: str, lookup_field: str, lookup_value) -> Optional[Dict]:
    """
    Get data from any database table using a lookup field and value.
    lookup_value must not be None; pass int for numeric IDs (ports, companies), str for UUIDs (refineries, brokers).

    Args:
        table_name: Name of the table (e.g., 'vessels', 'ports', 'refineries')
        lookup_field: Field name to search by (e.g., 'imo', 'id', 'name')
        lookup_value: Value to search for (int or str; must not be None)

    Returns:
        Dictionary with table data or None if not found
    """
    if not supabase:
        logger.warning(f"Supabase not available, cannot fetch data from {table_name}")
        return None
    if lookup_value is None:
        logger.warning("get_data_from_table: lookup_value is None, skipping fetch")
        return None

    try:
        logger.info(f"Fetching data from {table_name} table: {lookup_field}={lookup_value}")
        response = supabase.table(table_name).select('*').eq(lookup_field, lookup_value).limit(1).execute()
        
        if response.data and len(response.data) > 0:
            data = response.data[0]
            logger.info(f"Found data in {table_name}: {data.get('name', data.get('id', 'Unknown'))}")
            return data
        else:
            logger.warning(f"No data found in {table_name} for {lookup_field}={lookup_value}")
            return None
    except Exception as e:
        logger.error(f"Error fetching data from {table_name} for {lookup_field}={lookup_value}: {e}")
        return None


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
        vessel_data = get_data_from_table('vessels', 'imo', imo)
        
        if vessel_data:
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

def validate_placeholder_setting(setting: Dict) -> Tuple[bool, List[str]]:
    """
    Validate a placeholder setting structure.
    Returns (is_valid, list_of_errors).
    """
    errors = []
    
    if not isinstance(setting, dict):
        return False, ["Setting must be a dictionary"]
    
    source = setting.get('source') or 'database'
    valid_sources = ['random', 'database', 'csv', 'custom']
    
    if source not in valid_sources:
        errors.append(f"Invalid source '{source}'. Must be one of: {', '.join(valid_sources)}")
    
    if source == 'custom':
        custom_value = setting.get('customValue', '')
        if not custom_value or not str(custom_value).strip():
            errors.append("Custom source requires a non-empty customValue")
    
    if source == 'database':
        database_field = setting.get('databaseField', '')
        # Empty databaseField is OK - will use intelligent matching
        pass
    
    if source == 'csv':
        csv_id = setting.get('csvId', '')
        csv_field = setting.get('csvField', '')
        if not csv_id or not str(csv_id).strip():
            errors.append("CSV source requires a non-empty csvId")
        if not csv_field or not str(csv_field).strip():
            errors.append("CSV source requires a non-empty csvField")
    
    return len(errors) == 0, errors


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

def _ai_powered_field_match(placeholder: str, vessel: Dict, available_fields: List[str] = None) -> Optional[tuple]:
    """
    Use AI to intelligently match placeholder to database field.
    Returns (matched_field_name, matched_value) or None if no match.
    """
    if not OPENAI_ENABLED or not openai_client or not vessel:
        return None
    
    try:
        # Get available vessel fields
        if available_fields is None:
            available_fields = [k for k, v in vessel.items() if v is not None and str(v).strip() != '']
        
        if not available_fields:
            return None
        
        # Prepare context for AI
        vessel_summary = {k: str(v)[:100] for k, v in list(vessel.items())[:20]}  # First 20 fields, truncated
        
        prompt = f"""You are a maritime document processing assistant. Match the placeholder "{placeholder}" to the best database field from the available vessel data.

Available vessel fields (with sample values):
{json.dumps(vessel_summary, indent=2)}

Available field names: {', '.join(available_fields[:50])}

Task:
1. Understand what the placeholder "{placeholder}" represents (e.g., vessel name, IMO number, port, date, quantity, etc.)
2. Find the BEST matching field from the available fields
3. Return ONLY the field name that best matches, nothing else

Examples:
- "vesselname" → "name"
- "imonumber" → "imo"
- "portofloading" → "loading_port" or "currentport"
- "cargoquantity" → "cargo_quantity"
- "ownername" → "owner_name"

Return ONLY the field name (e.g., "name", "imo", "owner_name"), or "NONE" if no good match exists."""

        response = openai_client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[
                {'role': 'system', 'content': 'You are a maritime data matching expert. Return only the field name or "NONE".'},
                {'role': 'user', 'content': prompt}
            ],
            max_tokens=50,
            temperature=0.1,  # Low temperature for consistent matching
        )
        
        matched_field = (response.choices[0].message.content or '').strip().strip('"\'')
        
        if matched_field.upper() == 'NONE' or not matched_field:
            return None
        
        # Verify the matched field exists in vessel data
        if matched_field in vessel:
            value = vessel[matched_field]
            if value is not None and str(value).strip() != '':
                logger.debug(f"  🤖 AI match: '{placeholder}' -> '{matched_field}' = '{value}'")
                return (matched_field, str(value).strip())
        
        # Try case-insensitive match
        matched_field_lower = matched_field.lower()
        for field_name, field_value in vessel.items():
            if field_name.lower() == matched_field_lower:
                if field_value is not None and str(field_value).strip() != '':
                    logger.debug(f"  🤖 AI match (case-insensitive): '{placeholder}' -> '{field_name}' = '{field_value}'")
                    return (field_name, str(field_value).strip())
        
        return None
        
    except Exception as e:
        logger.debug(f"AI-powered matching failed for '{placeholder}': {e}")
        return None


def _intelligent_field_match(placeholder: str, vessel: Dict) -> tuple:
    """
    ADVANCED intelligent matching: Maximize database usage (90% of data is in DB).
    Uses AI-powered matching first, then multiple sophisticated strategies.
    Returns (matched_field_name, matched_value) or (None, None) if no match.
    """
    if not vessel:
        return (None, None)
    
    # Strategy 0: AI-Powered Matching (if OpenAI is available)
    # This uses AI to understand placeholder meaning and match to best database field
    if OPENAI_ENABLED and openai_client:
        ai_match = _ai_powered_field_match(placeholder, vessel)
        if ai_match:
            matched_field, matched_value = ai_match
            logger.info(f"  🤖✅ AI-POWERED MATCH: '{placeholder}' -> '{matched_field}' = '{matched_value}'")
            return (matched_field, matched_value)
    
    # Normalize placeholder name for matching
    placeholder_clean = placeholder.strip()
    placeholder_normalized = placeholder_clean.lower().replace('_', '').replace('-', '').replace(' ', '')
    placeholder_words = set(re.findall(r'[a-z]+', placeholder_normalized))
    
    # Extract meaningful words (length >= 2) for advanced matching
    meaningful_words = {w for w in placeholder_words if len(w) >= 2}
    
    # Synonym dictionary for advanced matching
    synonyms = {
        'vessel': ['ship', 'boat', 'tanker', 'carrier', 'vessel'],
        'name': ['title', 'label', 'name'],
        'owner': ['owner', 'proprietor', 'holder', 'company'],
        'operator': ['operator', 'manager', 'handler'],
        'port': ['harbor', 'harbour', 'dock', 'port'],
        'quantity': ['amount', 'volume', 'qty', 'quantity'],
        'type': ['kind', 'category', 'type'],
        'date': ['date', 'time', 'when'],
        'number': ['num', 'no', 'number', 'id'],
        'address': ['location', 'place', 'address'],
        'email': ['e-mail', 'mail', 'email'],
        'phone': ['tel', 'telephone', 'phone', 'contact'],
        'country': ['nation', 'state', 'country'],
        'flag': ['flag', 'registry', 'nationality'],
        'imo': ['imo', 'imo_number', 'imo_number'],
        'length': ['loa', 'length', 'long'],
        'width': ['beam', 'breadth', 'width'],
        'draft': ['draught', 'draft'],
        'speed': ['velocity', 'speed'],
        'cargo': ['freight', 'load', 'cargo'],
        'oil': ['petroleum', 'crude', 'oil'],
    }
    
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
        # Note: 'owner' can also map to vessel_owner field if owner_name doesn't exist
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
        # Common document fields
        'company': 'owner_name', 'companyname': 'owner_name', 'company_name': 'owner_name',
        'address': 'address', 'companyaddress': 'address', 'officeaddress': 'address',
        'email': 'email', 'emailaddress': 'email', 'e-mail': 'email',
        'phone': 'phone', 'telephone': 'phone', 'fax': 'fax', 'tel': 'phone',
        'contact': 'contact_person', 'contactperson': 'contact_person', 'contact_person': 'contact_person',
        'country': 'flag', 'nationality': 'flag', 'registry': 'registry_port',
        'port': 'currentport', 'portname': 'currentport', 'loadingport': 'loading_port',
        'via': 'via', 'position': 'position', 'pos': 'position',
        'quantity': 'cargo_quantity', 'amount': 'cargo_quantity', 'volume': 'cargo_quantity',
        'product': 'cargo_type', 'commodity': 'cargo_type', 'oil': 'oil_type',
        'date': 'updated_at', 'validity': 'updated_at', 'expiry': 'updated_at',
        # Additional common variations
        'shipname': 'name', 'tankername': 'name', 'carriername': 'name',
        'vesselimo': 'imo', 'shipimo': 'imo', 'tankerimo': 'imo',
        'vesseltype': 'vessel_type', 'shiptype': 'vessel_type', 'tankertype': 'vessel_type',
        'vesselowner': 'owner_name', 'shipowner': 'owner_name', 'tankerowner': 'owner_name',
        'portofregistry': 'registry_port', 'homeport': 'registry_port', 'registrationport': 'registry_port',
        'grossweight': 'gross_tonnage', 'netweight': 'net_tonnage', 'cargoweight': 'cargo_quantity',
        'loadport': 'loading_port', 'dischargeport': 'destination_port', 'arrivalport': 'destination_port',
        'departport': 'departure_port', 'sailingport': 'departure_port', 'fromport': 'departure_port',
        'toport': 'destination_port', 'finalport': 'destination_port', 'endport': 'destination_port',
        'cargoquantity': 'cargo_quantity', 'loadquantity': 'cargo_quantity', 'mt': 'cargo_quantity',
        'oilgrade': 'oil_type', 'crudetype': 'oil_type', 'producttype': 'cargo_type',
        'vesselstatus': 'status', 'shipstatus': 'status', 'currentstatus': 'status',
        'eta': 'eta', 'etd': 'etd', 'arrivaltime': 'eta', 'departuretime': 'etd',
        'vesselspeed': 'speed', 'shipspeed': 'speed', 'averagespeed': 'speed',
        'dwttonnage': 'deadweight', 'deadweighttons': 'deadweight', 'tonnage': 'deadweight',
        'grosstons': 'gross_tonnage', 'nettons': 'net_tonnage',
        'mastername': 'captain_name', 'captainname': 'captain_name', 'master': 'captain_name',
        'classification': 'class_society', 'class': 'class_society', 'classificationclass': 'class_society',
        'builtyear': 'built', 'constructedyear': 'built', 'constructionyear': 'built', 'ageyear': 'built',
        # Analysis/SGS specific
        'sampledate': 'updated_at', 'testdate': 'updated_at', 'analysisdate': 'updated_at',
        'result': 'cargo_quantity', 'testresult': 'cargo_quantity', 'analysisresult': 'cargo_quantity',
        'specification': 'cargo_type', 'spec': 'cargo_type', 'grade': 'oil_type',
        'density': 'cargo_quantity', 'viscosity': 'cargo_quantity', 'api': 'cargo_quantity',
        'sulfur': 'cargo_quantity', 'sulphur': 'cargo_quantity', 'water': 'cargo_quantity',
        'sediment': 'cargo_quantity', 'ash': 'cargo_quantity', 'pour': 'cargo_quantity',
        # Invoice/commercial specific  
        'invoicedate': 'updated_at', 'invoiceno': 'imo', 'invoicenumber': 'imo',
        'contractno': 'imo', 'contractnumber': 'imo', 'refno': 'imo', 'referenceno': 'imo',
        'blno': 'imo', 'blnumber': 'imo', 'billoflading': 'imo',
        'unitprice': 'price', 'pricepermt': 'price', 'rateperton': 'price',
        'totalamount': 'deal_value', 'totalvalue': 'deal_value', 'invoiceamount': 'deal_value',
        'currency': 'flag', 'paymentterms': 'shipping_type', 'terms': 'shipping_type',
    }
    
    # Strategy 1: Direct mapping (highest priority)
    if placeholder_normalized in field_mappings:
        mapped_field = field_mappings[placeholder_normalized]
        if mapped_field in vessel:
            value = vessel[mapped_field]
            if value is not None and str(value).strip() != '':
                logger.debug(f"  ✅ Direct mapping: '{placeholder}' -> '{mapped_field}'")
                return (mapped_field, str(value).strip())
        
        # Try alternative field names if primary doesn't exist
        # Special handling for 'owner' - try multiple field variations
        if placeholder_normalized == 'owner':
            for alt_field in ['vessel_owner', 'owner_name', 'owner']:
                if alt_field in vessel:
                    value = vessel[alt_field]
                    if value is not None and str(value).strip() != '':
                        logger.debug(f"  ✅ Alternative owner mapping: '{placeholder}' -> '{alt_field}'")
                        return (alt_field, str(value).strip())
    
    # Strategy 1.5: Synonym-based matching (check if placeholder words match synonyms)
    for word in meaningful_words:
        if word in synonyms:
            for synonym in synonyms[word]:
                # Try to find fields that contain this synonym
                for field_name, field_value in vessel.items():
                    if field_value is None or str(field_value).strip() == '':
                        continue
                    field_lower = field_name.lower()
                    if synonym in field_lower or field_lower in synonym:
                        logger.debug(f"  ✅ Synonym match: '{placeholder}' (word: '{word}') -> '{field_name}'")
                        return (field_name, str(field_value).strip())
    
    # Strategy 2: Exact match after normalization (high priority)
    best_match = None
    best_score = 0.0
    best_field = None
    all_candidates = []  # Store all potential matches for advanced selection
    
    for field_name, field_value in vessel.items():
        if field_value is None or str(field_value).strip() == '':
            continue
        
        field_normalized = field_name.lower().replace('_', '').replace('-', '').replace(' ', '')
        field_words = set(re.findall(r'[a-z]+', field_normalized))
        
        # Exact match after normalization
        if placeholder_normalized == field_normalized:
            logger.debug(f"  ✅ Exact normalized match: '{placeholder}' -> '{field_name}'")
            return (field_name, str(field_value).strip())
        
        # Calculate base similarity score
        similarity = _calculate_similarity(placeholder_normalized, field_normalized)
        
        # Strategy 2.1: Substring matching (very high boost)
        if placeholder_normalized in field_normalized or field_normalized in placeholder_normalized:
            similarity = max(similarity, 0.90)  # Very high boost for substring matches
        
        # Strategy 2.2: Word overlap bonus (enhanced)
        if placeholder_words and field_words:
            common_words = placeholder_words.intersection(field_words)
            if common_words:
                meaningful_common = [w for w in common_words if len(w) >= 2]  # Lowered to 2 chars
                if meaningful_common:
                    # Calculate word overlap ratio
                    overlap_ratio = len(meaningful_common) / max(len(placeholder_words), len(field_words))
                    similarity = max(similarity, 0.75 + (overlap_ratio * 0.15))  # Higher base boost
        
        # Strategy 2.3: Partial word matching (if ANY word from placeholder appears in field)
        if meaningful_words and field_words:
            partial_matches = meaningful_words.intersection(field_words)
            if partial_matches:
                # Boost based on how many words match
                match_ratio = len(partial_matches) / max(len(meaningful_words), len(field_words))
                similarity = max(similarity, 0.60 + (match_ratio * 0.20))  # Boost for partial matches
        
        # Strategy 2.4: Character-level substring (if placeholder chars appear in field)
        if len(placeholder_normalized) >= 3:
            # Check if significant portion of placeholder appears in field
            char_overlap = sum(1 for c in placeholder_normalized if c in field_normalized)
            char_ratio = char_overlap / max(len(placeholder_normalized), len(field_normalized))
            if char_ratio > 0.5:  # More than 50% character overlap
                similarity = max(similarity, 0.55 + (char_ratio * 0.25))
        
        # Strategy 2.5: Try variations (with/without underscores, different word orders)
        # Check if field name contains all placeholder words (in any order)
        if meaningful_words:
            field_words_lower = {w.lower() for w in field_words}
            if meaningful_words.issubset(field_words_lower) or field_words_lower.issubset(meaningful_words):
                similarity = max(similarity, 0.80)  # High boost for word set match
        
        # Track best match
        if similarity > best_score:
            best_score = similarity
            best_field = field_name
            best_match = str(field_value).strip()
        
        # Store all candidates for "best guess" fallback
        if similarity > 0.15:  # Very low threshold to capture all possibilities
            all_candidates.append({
                'field': field_name,
                'value': str(field_value).strip(),
                'score': similarity,
                'word_overlap': len(meaningful_words.intersection(field_words)) if meaningful_words and field_words else 0
            })
    
    # Strategy 3: Use best match if confidence is high enough (very aggressive)
    if best_match and best_score >= 0.50:  # Lowered to 50% - maximize DB usage
        logger.debug(f"  ✅ High confidence match: '{placeholder}' -> '{best_field}' (similarity: {best_score:.2f})")
        return (best_field, best_match)
    
    # Strategy 4: Medium confidence - any word overlap with similarity >= 0.35
    if best_match and best_score >= 0.35:
        key_words_placeholder = {w for w in placeholder_words if len(w) >= 2}  # Lowered to 2 chars
        if key_words_placeholder:
            best_field_words = set(re.findall(r'[a-z]+', best_field.lower().replace('_', '').replace('-', '')))
            if key_words_placeholder.intersection(best_field_words):
                logger.debug(f"  ✅ Medium confidence match: '{placeholder}' -> '{best_field}' (similarity: {best_score:.2f})")
                return (best_field, best_match)
    
    # Strategy 5: Low confidence - any word overlap with similarity >= 0.25
    if best_match and best_score >= 0.25:
        key_words_placeholder = {w for w in placeholder_words if len(w) >= 2}
        if key_words_placeholder:
            best_field_words = set(re.findall(r'[a-z]+', best_field.lower().replace('_', '').replace('-', '')))
            if key_words_placeholder.intersection(best_field_words):
                logger.debug(f"  ✅ Low confidence match: '{placeholder}' -> '{best_field}' (similarity: {best_score:.2f})")
                return (best_field, best_match)
    
    # Strategy 6: Very low threshold - any similarity >= 0.20 with ANY word match
    if best_match and best_score >= 0.20:
        key_words_placeholder = {w for w in placeholder_words if len(w) >= 2}
        if key_words_placeholder:
            best_field_words = set(re.findall(r'[a-z]+', best_field.lower().replace('_', '').replace('-', '')))
            if key_words_placeholder.intersection(best_field_words):
                logger.debug(f"  ✅ Very low confidence match: '{placeholder}' -> '{best_field}' (similarity: {best_score:.2f})")
                return (best_field, best_match)
    
    # Strategy 7: Ultra-aggressive - ANY similarity >= 0.15 (maximize DB usage)
    if best_match and best_score >= 0.15:
        logger.debug(f"  ✅ Ultra-low confidence match: '{placeholder}' -> '{best_field}' (similarity: {best_score:.2f})")
        return (best_field, best_match)
    
    # Strategy 8: "Best Guess" Fallback - Use the candidate with most word overlap
    # This ensures we ALWAYS try to use database data if available
    if all_candidates:
        # Sort by word overlap first, then by score
        all_candidates.sort(key=lambda x: (x['word_overlap'], x['score']), reverse=True)
        best_guess = all_candidates[0]
        if best_guess['word_overlap'] > 0 or best_guess['score'] > 0.10:
            logger.debug(f"  ✅ Best guess fallback: '{placeholder}' -> '{best_guess['field']}' (overlap: {best_guess['word_overlap']}, score: {best_guess['score']:.2f})")
            return (best_guess['field'], best_guess['value'])
    
    # Strategy 9: Smart guess based on placeholder pattern
    # Analyze placeholder name and guess most likely field
    pl_lower = placeholder_normalized.lower()
    
    # Pattern-based field selection
    pattern_to_fields = {
        # Names and identifiers
        ('name', 'vessel', 'ship', 'tanker'): ['name', 'vessel_name'],
        ('imo', 'number', 'id'): ['imo'],
        ('flag', 'country', 'nation', 'registry'): ['flag', 'registry_port'],
        ('type', 'kind', 'category'): ['vessel_type', 'cargo_type', 'oil_type'],
        ('owner', 'company', 'firm'): ['owner_name', 'vessel_owner', 'operator_name'],
        ('operator', 'manager'): ['operator_name', 'ism_manager'],
        
        # Location
        ('port', 'harbor', 'dock', 'terminal'): ['currentport', 'departure_port', 'destination_port', 'loading_port'],
        ('destination', 'arrival'): ['destination_port', 'destination'],
        ('departure', 'origin', 'from'): ['departure_port', 'origin'],
        ('position', 'location', 'where'): ['position', 'current_region', 'currentport'],
        
        # Dimensions
        ('length', 'loa', 'long'): ['length', 'loa'],
        ('width', 'beam', 'breadth'): ['width', 'beam'],
        ('draft', 'draught', 'depth'): ['draft', 'draught'],
        ('tonnage', 'dwt', 'weight', 'gross'): ['deadweight', 'gross_tonnage', 'net_tonnage'],
        
        # Cargo
        ('cargo', 'freight', 'load', 'product'): ['cargo_type', 'cargo_quantity', 'oil_type'],
        ('quantity', 'amount', 'volume', 'qty'): ['cargo_quantity', 'quantity'],
        ('oil', 'crude', 'petroleum'): ['oil_type', 'cargo_type'],
        
        # Dates
        ('date', 'time', 'when', 'eta', 'etd'): ['updated_at', 'created_at', 'eta', 'etd'],
        ('built', 'year', 'construction'): ['built', 'year_built'],
        
        # Contact
        ('email', 'mail'): ['email', 'contact_email'],
        ('phone', 'tel', 'telephone', 'contact'): ['phone', 'contact_phone'],
        ('address', 'street'): ['address'],
        
        # Speed and performance
        ('speed', 'velocity', 'knots'): ['speed', 'cruising_speed'],
        
        # Price and commercial
        ('price', 'cost', 'value', 'rate'): ['price', 'market_price', 'deal_value'],
        ('buyer', 'purchaser'): ['buyer_name'],
        ('seller', 'vendor'): ['seller_name'],
    }
    
    # Try pattern matching
    for patterns, fields in pattern_to_fields.items():
        for pattern in patterns:
            if pattern in pl_lower:
                for field in fields:
                    if field in vessel:
                        value = vessel[field]
                        if value is not None and str(value).strip() != '':
                            logger.debug(f"  ✅ Pattern match: '{placeholder}' (pattern: '{pattern}') -> '{field}'")
                            return (field, str(value).strip())
    
    # Strategy 10: Last resort - use ANY non-empty vessel field (prefer common fields)
    priority_fields = ['name', 'imo', 'flag', 'owner_name', 'operator_name', 'vessel_type', 
                       'currentport', 'cargo_type', 'cargo_quantity', 'length', 'width', 'draft',
                       'deadweight', 'gross_tonnage', 'speed', 'built', 'oil_type']
    for priority_field in priority_fields:
        if priority_field in vessel:
            value = vessel[priority_field]
            if value is not None and str(value).strip() != '':
                logger.debug(f"  ✅ Last resort (priority field): '{placeholder}' -> '{priority_field}'")
                return (priority_field, str(value).strip())
    
    # If we still have vessel data, use the first non-empty field
    for field_name, field_value in vessel.items():
        if field_value is not None and str(field_value).strip() != '':
            logger.debug(f"  ✅ Last resort (any field): '{placeholder}' -> '{field_name}'")
            return (field_name, str(field_value).strip())
    
    # No match found - vessel data is empty
    return (None, None)


def _intelligent_field_match_multi_table(placeholder: str, vessel: Dict) -> tuple:
    """
    Search vessels first, then ports/companies/refineries via vessel FKs. Brokers excluded.
    Returns (matched_field_name, matched_value) or (None, None).
    """
    if not vessel:
        return (None, None)

    # Step 1: Search vessel dict first
    matched_field, matched_value = _intelligent_field_match(placeholder, vessel)
    if matched_field and matched_value:
        return (matched_field, matched_value)

    # Step 2: Build merged "related data" dict from ports, companies, refineries (no brokers)
    merged: Dict[str, any] = dict(vessel)
    try:
        # Ports: departure_port, destination_port, loading_port, discharge_port (may be IDs)
        for port_key, prefix in [('departure_port', 'departure_port_'), ('destination_port', 'destination_port_'),
                                 ('loading_port', 'loading_port_'), ('discharge_port', 'discharge_port_')]:
            port_id = vessel.get(port_key)
            if port_id is not None:
                port_data = get_data_from_table('ports', 'id', port_id)
                if port_data:
                    for k, v in port_data.items():
                        if v is not None and str(v).strip():
                            merged[f"{prefix}{k}"] = v
                    merged[f"{prefix}name"] = port_data.get('name') or merged.get(f"{prefix}name")
        # Loading port often same as departure - add alias if missing
        if 'loading_port_name' not in merged and 'departure_port_name' in merged:
            merged['loading_port_name'] = merged['departure_port_name']
        # Generic port_name, port_loading, port_discharge for template placeholders
        if 'port_name' not in merged and merged.get('departure_port_name'):
            merged['port_name'] = merged['departure_port_name']
        if 'port_loading' not in merged and merged.get('loading_port_name'):
            merged['port_loading'] = merged['loading_port_name']
        if 'port_discharge' not in merged and merged.get('discharge_port_name'):
            merged['port_discharge'] = merged['discharge_port_name']
        # Company
        company_id = vessel.get('company_id') or vessel.get('buyer_company_id') or vessel.get('seller_company_id')
        if company_id is not None:
            company_data = get_data_from_table('companies', 'id', company_id)
            if company_data:
                for k, v in company_data.items():
                    if v is not None and str(v).strip():
                        merged[f"company_{k}"] = v
        # Refinery
        refinery_id = vessel.get('refinery_id')
        if refinery_id is not None:
            refinery_data = get_data_from_table('refineries', 'id', refinery_id)
            if refinery_data:
                for k, v in refinery_data.items():
                    if v is not None and str(v).strip():
                        merged[f"refinery_{k}"] = v
    except Exception as e:
        logger.debug(f"Building related data for multi-table match: {e}")

    # Step 3: Run matching against merged dict (exclude vessel keys we already tried)
    if len(merged) > len(vessel):
        matched_field, matched_value = _intelligent_field_match(placeholder, merged)
        if matched_field and matched_value:
            return (matched_field, matched_value)

    return (None, None)


def generate_realistic_random_data(placeholder: str, vessel_imo: str = None) -> str:
    """Generate realistic random data for placeholders (maritime/oil shipping context).
    Returns SHORT, SPECIFIC values matching placeholder type - no long text, no unrelated content."""
    import random
    import hashlib

    if vessel_imo:
        seed_input = f"{vessel_imo}_{placeholder.lower()}"
        random.seed(int(hashlib.md5(seed_input.encode()).hexdigest()[:8], 16))

    pl = placeholder.lower().replace('_', '').replace(' ', '').replace('-', '')

    # Dates - always short format
    if 'date' in pl or 'issue' in pl and 'date' in pl or 'expir' in pl or 'signature' in pl and 'date' in pl:
        from datetime import timedelta
        d = random.randint(1, 90)
        return (datetime.now() - timedelta(days=d)).strftime('%Y-%m-%d')

    # Bank / finance
    if 'swift' in pl or 'bic' in pl:
        return f"ABCDUS2S{random.randint(100,999)}"
    if 'account' in pl or 'acct' in pl:
        return f"ACC-{random.randint(1000000000, 9999999999)}"
    if 'bank' in pl and ('name' in pl or 'officer' not in pl):
        return random.choice(['HSBC Singapore', 'Standard Chartered', 'Deutsche Bank', 'ING Commercial Banking', 'BNP Paribas', 'Citibank'])
    if 'bank' in pl and 'address' in pl:
        return random.choice(['25 Raffles Place, Singapore 048619', '1 HarbourFront Place, Singapore 098633'])

    # Quality / spec values (short numbers)
    if 'result' in pl or 'max' in pl or 'min' in pl:
        if 'density' in pl or 'api' in pl:
            return f"{random.uniform(0.80, 0.90):.3f}"
        if 'viscosity' in pl:
            return f"{random.uniform(1.0, 6.0):.2f} cSt"
        if 'sulfur' in pl or 'sulphur' in pl:
            return f"{random.uniform(0.001, 0.5):.3f}%"
        if 'ash' in pl:
            return f"{random.uniform(0.01, 0.1):.3f}%"
        if 'acid' in pl:
            return f"{random.uniform(0.01, 0.5):.2f} mg KOH/g"
        if 'water' in pl:
            return f"{random.uniform(0.01, 0.5):.2f}%"
        if 'cloud' in pl or 'cfpp' in pl or 'pour' in pl:
            return f"{random.randint(-15, 25)}°C"
        if 'flash' in pl:
            return f"{random.randint(40, 100)}°C"
        if 'color' in pl or 'colour' in pl:
            return f"{random.randint(0, 3)}"
        if 'cetane' in pl:
            return f"{random.randint(45, 60)}"
        if 'distill' in pl or 'dist' in pl:
            return f"{random.randint(180, 360)}°C"
        return f"{random.uniform(0.01, 2.0):.2f}"

    # Contact
    if 'email' in pl:
        domains = ['maritimetrading.com', 'oceanfreight.co', 'petrodealhub.com']
        return f"contact{random.randint(1,99)}@{random.choice(domains)}"
    if 'phone' in pl or 'tel' in pl or 'mobile' in pl or 'fax' in pl:
        return f"+{random.choice([1,44,31,49,971])} {random.randint(100,999)} {random.randint(1000000,9999999)}"

    # Title/designation - BEFORE name (representative_title -> title, not name)
    if 'designation' in pl or 'position' in pl or 'title' in pl or 'role' in pl:
        return random.choice(['Operations Manager', 'Chartering Manager', 'Trader', 'Shipping Coordinator'])
    # Product/commodity - BEFORE name (commodity_name -> product, not person)
    products = ['Crude Oil', 'Diesel', 'Jet A-1', 'Fuel Oil 380', 'Gasoline', 'Brent Blend', 'Murban Crude']
    if 'product' in pl or 'oil' in pl or 'grade' in pl or 'commodity' in pl or ('cargo' in pl and 'quantity' not in pl and 'capacity' not in pl and 'tank' not in pl):
        return random.choice(products)
    # Person names - short
    names = ['John Smith', 'Maria Garcia', 'Ahmed Hassan', 'Li Wei', 'David Johnson', 'Sarah Brown']
    if 'person' in pl or 'representative' in pl or 'signatory' in pl or 'witness' in pl or 'officer' in pl or ('name' in pl and 'company' not in pl and 'commodity' not in pl):
        if 'company' in pl:
            return random.choice(['Maritime Solutions Ltd', 'Ocean Trading Co', 'Global Shipping Inc'])
        return random.choice(names)

    # Companies / buyer / seller
    companies = ['Maritime Solutions Ltd', 'Ocean Trading Co', 'Global Shipping Inc', 'PetroMarine Services', 'Gulf Energy Trading', 'Nordic Tanker Co']
    if 'company' in pl or 'seller' in pl or 'buyer' in pl and 'name' in pl:
        return random.choice(companies)

    # Address
    if 'address' in pl:
        return random.choice(['123 Maritime St, London', '456 Harbour Rd, Singapore', '55 Raffles Place, Singapore'])

    # Numbers / amounts - BEFORE product (cargo_quantity -> MT, not product name)
    if 'quantity' in pl or 'volume' in pl or 'mt' in pl or 'tons' in pl or 'weight' in pl:
        return f"{random.randint(1000, 50000):,} MT"

    # Ports / locations
    ports = ['Rotterdam', 'Singapore', 'Fujairah', 'Houston', 'Antwerp', 'Jebel Ali', 'Ras Tanura']
    if 'port' in pl or 'harbor' in pl or 'loading' in pl or 'discharge' in pl or 'origin' in pl or 'destination' in pl:
        return random.choice(ports)
    if 'country' in pl:
        return random.choice(['Singapore', 'UAE', 'Netherlands', 'USA', 'UK', 'Saudi Arabia'])

    if 'value' in pl or 'amount' in pl or 'price' in pl or 'total' in pl:
        return f"${random.randint(10000, 999999):,}"
    if 'percent' in pl or 'percentage' in pl or 'tolerance' in pl:
        return f"{random.uniform(0.1, 5.0):.2f}%"
    if 'tonnage' in pl or 'capacity' in pl:
        return f"{random.randint(5000, 120000):,}"
    if 'pumping' in pl:
        return f"{random.randint(500, 3000)} m³/hr"

    # References / IDs
    if 'ref' in pl or 'number' in pl or 'no' in pl and 'phone' not in pl:
        return f"REF-{random.randint(100000, 999999)}"
    if 'bin' in pl or 'okpo' in pl:
        return f"{random.randint(100000000, 999999999)}"

    # Legal / contract
    if 'arbitration' in pl or 'governing' in pl or 'law' in pl:
        return random.choice(['Singapore', 'London', 'Dubai', 'Geneva'])
    if 'registration' in pl and 'number' in pl:
        return f"REG-{random.randint(100000, 999999)}"

    # Vessel / maritime
    if 'ism' in pl or 'manager' in pl:
        return random.choice(['V.Ships', 'Anglo-Eastern', 'Synergy Marine', 'Fleet Management'])
    if 'class' in pl or 'society' in pl or 'classification' in pl:
        return random.choice(["Lloyd's Register", 'DNV', 'ABS', 'Bureau Veritas'])
    if 'via' in pl or 'carrier' in pl:
        return random.choice(['Maersk', 'MSC', 'CMA CGM', 'COSCO'])

    # Short fallbacks - never long text
    fallbacks = ['TBN', 'N/A', 'As per contract', 'To be confirmed', 'See annex']
    return random.choice(fallbacks)


def _try_csv_for_placeholder(setting: Optional[Dict]) -> Optional[str]:
    """Try to resolve placeholder from configured CSV. Returns value or None."""
    if not setting:
        return None
    csv_id = (setting.get('csvId') or '').strip()
    csv_field = (setting.get('csvField') or '').strip()
    if not csv_id or not csv_field:
        return None
    try:
        row_idx = int(setting.get('csvRow') or 0)
        data = get_csv_data(csv_id, row_idx)
        if not data:
            return None
        if csv_field in data:
            v = data[csv_field]
            if v is not None and str(v).strip():
                return str(v).strip()
        for k, v in data.items():
            if k.lower() == csv_field.lower() and v is not None and str(v).strip():
                return str(v).strip()
    except Exception:
        pass
    return None


def _smart_csv_search(placeholder: str) -> Optional[str]:
    """Search all CSVs for a column matching the placeholder. Returns value from first matching row or None."""
    def _normalize_for_column(s: str) -> str:
        return re.sub(r'[^a-z0-9]', '', (s or '').lower()).replace(' ', '_')

    ph_norm = _normalize_for_column(placeholder)
    ph_words = set(re.findall(r'[a-z]+', ph_norm))
    if not ph_norm:
        return None

    for dataset in list_csv_datasets():
        path = dataset.get("path") or os.path.join(DATA_DIR, dataset.get("filename", ""))
        if not os.path.exists(path):
            continue
        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                if not rows:
                    continue
                fieldnames = list(reader.fieldnames or rows[0].keys() or [])
            cols_norm = {_normalize_for_column(c): c for c in fieldnames if c}

            # Exact match
            if ph_norm in cols_norm:
                col = cols_norm[ph_norm]
                v = rows[0].get(col)
                if v is not None and str(v).strip():
                    return str(v).strip()

            # Case-insensitive
            ph_lower = placeholder.lower().replace(' ', '_').replace('-', '_')
            for c in fieldnames:
                if c and c.lower().replace(' ', '_') == ph_lower:
                    v = rows[0].get(c)
                    if v is not None and str(v).strip():
                        return str(v).strip()

            # Partial/word overlap
            best_col = None
            best_score = 0
            for c_norm, c_orig in cols_norm.items():
                c_words = set(re.findall(r'[a-z]+', c_norm))
                overlap = len(ph_words & c_words) / max(len(ph_words), 1)
                if overlap > best_score and overlap >= 0.5:
                    best_score = overlap
                    best_col = c_orig
            if best_col:
                v = rows[0].get(best_col)
                if v is not None and str(v).strip():
                    return str(v).strip()
        except Exception as e:
            logger.debug(f"_smart_csv_search error for {dataset.get('id', '')}: {e}")
    return None


def _sanitize_ai_replacement(text: str) -> str:
    """Strip explanatory prefixes and reject log-like output. Return clean value or empty string."""
    if not text or not isinstance(text, str):
        return ""
    s = text.strip().strip('"\'').replace("\r\n", "\n").replace("\r", "\n")
    # First line only (avoid multi-line explanations)
    first = s.split("\n")[0].strip()
    if not first:
        return ""
    # Remove common prefixes (case-insensitive), repeat until clean
    prefixes = (
        "here is the value:", "the value is", "answer:", "generated value:",
        "value:", "the generated value is", "the value:", "result:",
        "output:", "generated:", "here's the value:", "it is ", "it's ",
        "return only", "only the value", "just the value", "the answer is ",
    )
    for _ in range(5):
        lower = first.lower()
        hit = False
        for p in prefixes:
            if lower.startswith(p):
                first = first[len(p):].strip().lstrip(":-.")
                hit = True
                break
        if not hit:
            break
    if not first or len(first) > 120:
        return ""
    # Reject log-like / debug output (avoid putting logger text into documents)
    lower = first.lower()
    if lower.startswith(("info:", "debug:", "warning:", "error:", "traceback", "exception")):
        return ""
    if "mapping:" in lower or "-> '" in lower or "placeholder '" in lower or "logger." in lower:
        return ""
    for bad in ("✅", "⚠️", "❌", "📋", "🔍"):
        if bad in first:
            return ""
    return first[:100]


def generate_realistic_data_ai(placeholder: str, vessel: Dict, vessel_imo: str = None) -> str:
    """AI-generated realistic data (OpenAI when available), else improved random. Maritime/oil context."""
    if OPENAI_ENABLED and openai_client:
        try:
            imo = (vessel or {}).get('imo') or vessel_imo or 'N/A'
            pl_lower = (placeholder or '').lower()
            hints = []
            if 'date' in pl_lower: hints.append('date YYYY-MM-DD')
            if 'email' in pl_lower: hints.append('email')
            if 'company' in pl_lower or 'buyer' in pl_lower or 'seller' in pl_lower: hints.append('company name')
            if 'port' in pl_lower or 'loading' in pl_lower or 'discharge' in pl_lower: hints.append('port name')
            if 'quantity' in pl_lower or 'amount' in pl_lower: hints.append('number with unit')
            if 'phone' in pl_lower or 'tel' in pl_lower: hints.append('phone')
            if 'address' in pl_lower: hints.append('short address')
            if 'name' in pl_lower and 'company' not in pl_lower: hints.append('person name')
            if 'bank' in pl_lower or 'swift' in pl_lower: hints.append('bank/SWIFT')
            if 'price' in pl_lower or 'value' in pl_lower: hints.append('currency amount')
            hint_str = ', '.join(hints) if hints else 'short value'
            prompt = (
                f"Placeholder: '{placeholder}' (maritime/oil document). Type: {hint_str}. "
                f"Output ONLY the value - one short phrase or number, max 50 chars. "
                f"No quotes, no explanation, no sentences. Example: buyer_name -> 'John Smith'. "
                f"Vessel IMO: {imo}."
            )
            r = openai_client.chat.completions.create(
                model='gpt-4o-mini',
                messages=[{'role': 'user', 'content': prompt}],
                max_tokens=60,
                temperature=0.2,
            )
            raw = (r.choices[0].message.content or '').strip()
            out = _sanitize_ai_replacement(raw)
            if out:
                return out
        except Exception as e:
            logger.warning(f"OpenAI fallback for '{placeholder}': {e}")
    return generate_realistic_random_data(placeholder, vessel_imo)

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
    # Note: Can't use backslashes in f-string expressions, so build patterns with concatenation
    double_brace = r"\{\{" + r"\s*" + inner_pattern + r"\s*" + r"\}\}"
    single_brace = r"\{" + r"\s*" + inner_pattern + r"\s*" + r"\}"
    double_bracket = r"\[\[" + r"\s*" + inner_pattern + r"\s*" + r"\]\]"
    single_bracket = r"\[" + r"\s*" + inner_pattern + r"\s*" + r"\]"
    percent = r"%" + r"\s*" + inner_pattern + r"\s*" + r"%"
    angle = r"<" + r"\s*" + inner_pattern + r"\s*" + r">"
    double_underscore = r"__" + r"\s*" + inner_pattern + r"\s*" + r"__"
    double_hash = r"##" + r"\s*" + inner_pattern + r"\s*" + r"##"
    
    wrappers = [
        double_brace,      # {{placeholder}} - DOUBLE BRACES
        single_brace,      # {placeholder} - MOST COMMON
        double_bracket,    # [[placeholder]]
        single_bracket,    # [placeholder]
        percent,           # %placeholder%
        angle,             # <placeholder>
        double_underscore, # __placeholder__
        double_hash,       # ##placeholder##
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
        found_any = False
        for pattern in patterns:
            matches = list(pattern.finditer(updated_text))
            if matches:
                found_any = True
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
        
        if not found_any:
            logger.debug(f"⚠️  No matches found for placeholder '{placeholder}' in text (first 200 chars: '{updated_text[:200]}...')")
            logger.debug(f"   Patterns tried: {[p.pattern for p in patterns]}")

    return updated_text, total_replacements


EMPTY_PLACEHOLDER = "—"


def _normalize_replacement_value(val, _field_name: Optional[str] = None) -> str:
    """Normalize a value for placeholder replacement. None/empty -> '—'.
    Reject log-like, verbose, or unrelated text. Cap at 150 chars for document fields."""
    if val is None:
        return EMPTY_PLACEHOLDER
    s = str(val).strip()
    if not s or s.lower() in ("none", "null"):
        return EMPTY_PLACEHOLDER
    lower = s.lower()
    if "mapping:" in lower or "-> '" in lower or "placeholder '" in lower:
        return EMPTY_PLACEHOLDER
    for bad in ("✅", "⚠️", "❌", "📋", "🔍"):
        if bad in s:
            return EMPTY_PLACEHOLDER
    # Cap length - placeholders need short values, not paragraphs
    if len(s) > 150:
        s = s[:147].rsplit(' ', 1)[0] + "..." if ' ' in s[:147] else s[:147]
    return s[:150]


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
        
        # Log all mappings
        for key, value in data.items():
            logger.info("📋 Mapping: '%s' -> '%s'", key, str(value))
        
        # Extract all placeholders from document to compare
        doc = Document(docx_path)
        all_doc_placeholders = set()
        for paragraph in doc.paragraphs:
            placeholders = find_placeholders(paragraph.text)
            all_doc_placeholders.update(placeholders)
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        placeholders = find_placeholders(paragraph.text)
                        all_doc_placeholders.update(placeholders)
        
        logger.info("=" * 80)
        logger.info(f"📄 Document contains {len(all_doc_placeholders)} unique placeholders")
        logger.info(f"📋 Data mapping contains {len(data)} placeholders")
        
        # Find placeholders in document but not in mapping
        missing_in_mapping = all_doc_placeholders - set(data.keys())
        if missing_in_mapping:
            logger.warning(f"⚠️  {len(missing_in_mapping)} placeholders in document but NOT in mapping:")
            for ph in sorted(list(missing_in_mapping))[:20]:  # Show first 20
                logger.warning(f"   - {ph}")
            if len(missing_in_mapping) > 20:
                logger.warning(f"   ... and {len(missing_in_mapping) - 20} more")
        
        # Find placeholders in mapping but not in document
        extra_in_mapping = set(data.keys()) - all_doc_placeholders
        if extra_in_mapping:
            logger.info(f"ℹ️  {len(extra_in_mapping)} placeholders in mapping but NOT in document (will be ignored)")
        
        logger.info("=" * 80)

        replacements_made = 0
        pattern_cache: Dict[str, List[re.Pattern]] = {}
        
        # Build all patterns upfront for better performance
        logger.info("Building placeholder patterns...")
        for placeholder in data.keys():
            if placeholder not in pattern_cache:
                patterns = _build_placeholder_pattern(placeholder)
                pattern_cache[placeholder] = patterns
                logger.debug(f"Built {len(patterns)} patterns for '{placeholder}'")
                if not patterns:
                    logger.warning(f"⚠️  No patterns built for placeholder '{placeholder}'")
                else:
                    logger.debug(f"   First pattern: {patterns[0].pattern if patterns else 'None'}")

        def replace_in_runs(runs, data_mapping, pattern_cache):
            """Replace placeholders in runs while preserving formatting"""
            total_replacements = 0
            
            # First, try to replace in individual runs (for placeholders that are in a single run)
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
            
            # If no replacements in individual runs, try paragraph-level replacement
            # (handles placeholders split across multiple runs)
            if total_replacements == 0:
                # Combine all run texts to check for split placeholders
                combined_text = ''.join([run.text for run in runs if run.text])
                if combined_text:
                    # Check if combined text has placeholders
                    has_placeholder = False
                    for placeholder in data_mapping.keys():
                        patterns = pattern_cache.get(placeholder)
                        if patterns is None:
                            patterns = _build_placeholder_pattern(placeholder)
                            pattern_cache[placeholder] = patterns
                        
                        for pattern in patterns:
                            if pattern.search(combined_text):
                                has_placeholder = True
                                break
                        if has_placeholder:
                            break
                    
                    if has_placeholder:
                        # Replace in combined text
                        updated_combined, replaced = _replace_text_with_mapping(combined_text, data_mapping, pattern_cache)
                        
                        if replaced > 0 and updated_combined != combined_text:
                            # Update the first run with the combined text, clear others
                            if runs:
                                runs[0].text = updated_combined
                                for run in runs[1:]:
                                    run.text = ''
                                total_replacements += replaced
                                logger.debug(f"Paragraph-level replacement: {replaced} placeholder(s) (was split across runs)")
            
            return total_replacements

        def process_paragraphs(paragraphs):
            """Process paragraphs and replace placeholders in their runs"""
            nonlocal replacements_made
            for para_idx, paragraph in enumerate(paragraphs):
                paragraph_text = paragraph.text
                if not paragraph_text:
                    continue
                
                # Quick check: does this paragraph contain any placeholder pattern?
                has_placeholder = False
                matching_placeholders = []
                for placeholder in data.keys():
                    patterns = pattern_cache.get(placeholder)
                    if patterns is None:
                        patterns = _build_placeholder_pattern(placeholder)
                        pattern_cache[placeholder] = patterns
                    
                    for pattern in patterns:
                        if pattern.search(paragraph_text):
                            has_placeholder = True
                            matching_placeholders.append(placeholder)
                            break
                
                if not has_placeholder:
                    continue  # Skip paragraphs without placeholders
                
                logger.debug(f"Paragraph {para_idx} contains placeholders: {matching_placeholders[:5]}...")
                
                # Replace placeholders in runs (preserves formatting)
                replaced = replace_in_runs(paragraph.runs, data, pattern_cache)
                replacements_made += replaced
                
                if replaced > 0:
                    logger.info(f"📝 Paragraph {para_idx}: replaced {replaced} placeholder(s) in '{paragraph_text[:60]}...'")
                elif has_placeholder:
                    logger.warning(f"⚠️  Paragraph {para_idx} has placeholders but no replacements made: {matching_placeholders[:3]}...")
                    logger.warning(f"   Paragraph text: '{paragraph_text[:100]}...'")

        # Process body paragraphs
        logger.info("Processing body paragraphs...")
        process_paragraphs(doc.paragraphs)

        # Process tables
        logger.info("Processing tables...")
        for table_idx, table in enumerate(doc.tables):
            for row_idx, row in enumerate(table.rows):
                for cell_idx, cell in enumerate(row.cells):
                    for para_idx, paragraph in enumerate(cell.paragraphs):
                        paragraph_text = paragraph.text
                        if not paragraph_text:
                            continue
                        
                        # Check if paragraph has placeholders
                        has_placeholder = False
                        matching_placeholders = []
                        for placeholder in data.keys():
                            patterns = pattern_cache.get(placeholder, [])
                            for pattern in patterns:
                                if pattern.search(paragraph_text):
                                    has_placeholder = True
                                    matching_placeholders.append(placeholder)
                                    break
                            if has_placeholder:
                                break
                        
                        if has_placeholder:
                            replaced = replace_in_runs(paragraph.runs, data, pattern_cache)
                            replacements_made += replaced
                            if replaced > 0:
                                logger.info(f"📊 Table[{table_idx}][{row_idx}][{cell_idx}][para{para_idx}]: {replaced} replacement(s)")
                            else:
                                logger.warning(f"⚠️  Table[{table_idx}][{row_idx}][{cell_idx}][para{para_idx}] has placeholders but no replacements: {matching_placeholders[:3]}...")

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


def convert_pdf_to_images_zip(pdf_path: str, base_filename: str) -> bytes:
    """Convert PDF pages to images and create a zip file containing all images
    
    Args:
        pdf_path: Path to the PDF file
        base_filename: Base name for the images (without extension)
        
    Returns:
        bytes: ZIP file content containing all PDF pages as PNG images
    """
    if not FITZ_AVAILABLE:
        raise HTTPException(status_code=500, detail="PyMuPDF (fitz) is not available. Cannot convert PDF to images.")
    
    try:
        # Open PDF
        pdf_document = fitz.open(pdf_path)
        total_pages = len(pdf_document)
        logger.info(f"Converting PDF to images: {total_pages} pages")
        
        # Create zip file in memory
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # Convert each page to image
            for page_num in range(total_pages):
                page = pdf_document[page_num]
                
                # Render page to image (pixmap) at 2x resolution for better quality
                # 300 DPI equivalent (72 * 4.167)
                mat = fitz.Matrix(2.0, 2.0)
                pix = page.get_pixmap(matrix=mat)
                
                # Convert pixmap to PNG bytes
                img_bytes = pix.tobytes("png")
                
                # Add to zip with page number in filename
                image_filename = f"{base_filename}_page_{page_num + 1:03d}.png"
                zip_file.writestr(image_filename, img_bytes)
                logger.debug(f"Added page {page_num + 1} to zip: {image_filename}")
        
        pdf_document.close()
        
        # Get zip file content
        zip_buffer.seek(0)
        zip_content = zip_buffer.read()
        zip_buffer.close()
        
        logger.info(f"Successfully created zip file with {total_pages} images ({len(zip_content)} bytes)")
        return zip_content
        
    except Exception as e:
        logger.error(f"Error converting PDF to images: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to convert PDF to images: {str(e)}")


def convert_pdf_to_images_then_to_pdf(pdf_path: str) -> bytes:
    """Convert PDF → images → new PDF (image-based). Each page becomes an image in the output PDF.
    Returns PDF bytes (application/pdf) for download.
    """
    if not FITZ_AVAILABLE:
        raise HTTPException(status_code=500, detail="PyMuPDF (fitz) is not available. Cannot convert PDF.")
    try:
        src = fitz.open(pdf_path)
        total = len(src)
        logger.info(f"Converting PDF to images then to PDF: {total} pages")
        out = fitz.open()
        for i in range(total):
            page = src[i]
            mat = fitz.Matrix(2.0, 2.0)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            w, h = pix.width, pix.height
            r = fitz.Rect(0, 0, w, h)
            new_page = out.new_page(-1, width=w, height=h)
            new_page.insert_image(r, pixmap=pix)
        src.close()
        pdf_bytes = out.write(deflate=False)
        out.close()
        logger.info(f"Created image-based PDF: {len(pdf_bytes)} bytes ({total} pages)")
        return pdf_bytes
    except Exception as e:
        logger.error(f"Error converting PDF to images then to PDF: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to convert PDF: {str(e)}")


@app.options("/generate-document")
async def options_generate_document(request: Request):
    """Handle CORS preflight for generate-document endpoint"""
    return Response(status_code=200, headers=_cors_preflight_headers(request, "POST, OPTIONS"))

@app.options("/api/generate-document")
async def options_api_generate_document(request: Request):
    """CORS preflight when Nginx forwards /api prefix (no trailing slash in proxy_pass)"""
    return Response(status_code=200, headers=_cors_preflight_headers(request, "POST, OPTIONS"))

@app.post("/generate-document")
@app.post("/api/generate-document")
async def generate_document(request: Request):
    """Generate a document from template"""
    template_temp_path: Optional[str] = None
    template_record: Optional[Dict] = None
    try:
        body = await request.json()
        template_id = body.get('template_id')  # New: prefer template_id
        template_name = body.get('template_name')  # Fallback for backward compatibility
        vessel_imo = body.get('vessel_imo')
        user_id = body.get('user_id')  # Optional: for permission checking
        
        # Validate required fields
        if not template_id and not template_name:
            raise HTTPException(status_code=422, detail="template_id or template_name is required")
        
        if not vessel_imo:
            raise HTTPException(status_code=422, detail="vessel_imo is required. Please provide the IMO number of the vessel.")
        
        # Log the vessel IMO being used - CRITICAL for debugging
        logger.info("=" * 80)
        logger.info(f"🚢 GENERATING DOCUMENT")
        logger.info(f"   Template ID: {template_id}")
        logger.info(f"   Template Name: {template_name}")
        logger.info(f"   Vessel IMO: {vessel_imo} (from vessel detail page)")
        logger.info(f"   User ID: {user_id}")
        logger.info("=" * 80)
        
        effective_template_name = template_name
        template_settings: Dict[str, Dict] = {}
        template_temp_path: Optional[str] = None
        template_record: Optional[Dict] = None

        if SUPABASE_ENABLED:
            # Try to resolve by template_id first (UUID)
            if template_id:
                try:
                    template_uuid = uuid.UUID(str(template_id))
                    response = supabase.table('document_templates').select('id, title, description, file_name, placeholders, is_active, created_at, updated_at').eq('id', str(template_uuid)).limit(1).execute()
                    if response.data:
                        template_record = response.data[0]
                        logger.info(f"Found template by ID: {template_id}")
                except (ValueError, TypeError):
                    # Not a valid UUID, try as template_name
                    logger.info(f"template_id '{template_id}' is not a valid UUID, trying as template_name")
                    template_record = resolve_template_record(template_id)
            
            # Fallback to template_name if template_id didn't work
            if not template_record and template_name:
                template_record = resolve_template_record(template_name)
            
            if not template_record:
                raise HTTPException(status_code=404, detail=f"Template not found: {template_id or template_name}")

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
        logger.info(f"   Extracted placeholders ({len(placeholders)} total): {placeholders[:30]}...")  # Show first 30
        logger.info(f"   Configured CMS placeholders ({len(template_settings)} total): {list(template_settings.keys())[:30]}...")  # Show first 30
        
        # Create a mapping report
        matched_placeholders = []
        unmatched_placeholders = []
        
        for placeholder in placeholders:
            found = False
            setting_key, setting = resolve_placeholder_setting(template_settings, placeholder)
            # Default: database. Random only when user explicitly chooses it in CMS.
            source = (setting.get('source') or 'database') if setting else 'database'
            
            # Log all available settings keys for debugging
            if not setting and template_settings:
                unmatched_placeholders.append(placeholder)
                logger.warning(f"⚠️  Placeholder '{placeholder}' not found in template_settings")
                logger.warning(f"   Available settings keys: {list(template_settings.keys())[:20]}...")
                logger.warning(f"   Trying to match using normalization...")
                
                # Try to find similar placeholder names using normalization
                placeholder_norm = normalise_placeholder_key(placeholder)
                logger.warning(f"   Normalized placeholder: '{placeholder_norm}'")
                
                similar_keys = []
                for key in template_settings.keys():
                    key_norm = normalise_placeholder_key(key)
                    if placeholder_norm == key_norm:
                        similar_keys.append(f"'{key}' (exact normalized match)")
                    elif placeholder_norm in key_norm or key_norm in placeholder_norm:
                        similarity = len(set(placeholder_norm) & set(key_norm)) / max(len(placeholder_norm), len(key_norm))
                        if similarity > 0.5:
                            similar_keys.append(f"'{key}' (similarity: {similarity:.2f})")
                
                if similar_keys:
                    logger.warning(f"   Similar keys found: {', '.join(similar_keys[:5])}")
                else:
                    logger.warning(f"   No similar keys found. This placeholder will use cascade (DB → CSV → AI).")
            else:
                matched_placeholders.append(placeholder)
                logger.debug(f"✅ Found CMS setting for '{placeholder}' (matched key: '{setting_key}')")

            # Respect editor choice: only try "intelligent DB first" when source is database (or no setting).
            # When user chose csv / custom / random, never override with DB – use their choice.
            src = (setting.get('source') or 'database') if setting else 'database'
            dt = (setting.get('databaseTable') or '').strip() if setting else ''
            df = (setting.get('databaseField') or '').strip() if setting else ''
            has_explicit_db = bool(setting and src == 'database' and dt and df)
            run_intelligent_db_first = (not setting) or (src == 'database')

            if has_explicit_db:
                logger.info(f"\n🔍 Processing placeholder: '{placeholder}' [explicit (table, column) configured; using those first]")
            elif run_intelligent_db_first:
                logger.info(f"\n🔍 Processing placeholder: '{placeholder}' [source=database; trying intelligent DB match first]")
                logger.info(f"  🗄️  STEP 1: Trying intelligent database matching (vessels → ports → companies → refineries)...")
                matched_field, matched_value = _intelligent_field_match_multi_table(placeholder, vessel)
                if matched_field and matched_value:
                    data_mapping[placeholder] = _normalize_replacement_value(matched_value)
                    found = True
                    logger.info(f"  ✅✅✅ DATABASE MATCH (intelligent): {placeholder} = '{matched_value}' (from '{matched_field}')")
                    continue
                logger.info(f"  ⚠️  No intelligent DB match for '{placeholder}', will try configured source or cascade")
            else:
                logger.info(f"\n🔍 Processing placeholder: '{placeholder}' [source={src}; using configured source only, no DB override]")

            if setting:
                # Validate setting structure
                is_valid, validation_errors = validate_placeholder_setting(setting)
                if not is_valid:
                    logger.warning(f"⚠️  Invalid placeholder setting for '{placeholder}': {', '.join(validation_errors)}")
                    logger.warning(f"   Will use cascade (CSV → random/AI) as fallback")
                
                source = setting.get('source') or 'database'
                logger.info(f"  📋 CMS SETTING for '{placeholder}' (source: {source}):")
                logger.info(f"     customValue: '{setting.get('customValue')}'")
                logger.info(f"     databaseTable: '{setting.get('databaseTable')}'")
                logger.info(f"     databaseField: '{setting.get('databaseField')}'")
                logger.info(f"     csvId: '{setting.get('csvId')}', csvField: '{setting.get('csvField')}', csvRow: {setting.get('csvRow')}")
                logger.info(f"     randomOption: '{setting.get('randomOption')}'")

                try:
                    
                    # STEP 2: If database matching failed, try configured source
                    if source == 'custom':
                        custom_value = str(setting.get('customValue', '')).strip()
                        if custom_value:
                            data_mapping[placeholder] = _normalize_replacement_value(custom_value)
                            found = True
                            logger.info(f"✅ {placeholder} -> '{custom_value}' (CMS custom value)")
                        else:
                            logger.warning(f"⚠️  Placeholder '{placeholder}' has custom source but customValue is empty")
                            found = False  # Will fall through to cascade

                    elif source == 'random':
                        # Use cascade: try CSV if configured, else random/AI. No DB override.
                        logger.info(f"  🎲 Source is 'random'. Will use cascade (CSV if configured → random/AI)")
                        found = False  # Fall through to cascade

                    elif source == 'database':
                        database_table = (setting.get('databaseTable') or '').strip()
                        database_field = (setting.get('databaseField') or '').strip()
                        logger.info(f"  🗄️  DATABASE source configured for '{placeholder}'")
                        logger.info(f"     databaseTable='{database_table}'")
                        logger.info(f"     databaseField='{database_field}'")
                        logger.info(f"     vessel_imo='{vessel_imo}' (from page)")

                        matched_field = None
                        matched_value = None
                        source_data = vessel  # Default to vessel data

                        # If database_table is brokers, skip DB lookup and fall through to cascade
                        if database_table and database_table.lower() == 'brokers':
                            logger.info(f"  ⚠️  Brokers table excluded from mapping; will use cascade (CSV → AI)")
                            found = False
                            source_data = None  # Skip matching block
                        # If database_table is specified and it's not 'vessels', fetch data from that table
                        elif database_table and database_table.lower() != 'vessels':
                            logger.info(f"  🔍 Fetching data from table '{database_table}'...")
                            
                            # Determine lookup field and value based on table
                            # For now, we'll try common lookup strategies
                            lookup_field = None
                            lookup_value = None
                            
                            if database_table.lower() == 'ports':
                                # Vessel has departure_port, destination_port (numeric port IDs). Prefer departure, else destination.
                                lookup_field = 'id'
                                lookup_value = vessel.get('departure_port')
                                if lookup_value is None:
                                    lookup_value = vessel.get('destination_port')
                            elif database_table.lower() == 'refineries':
                                lookup_field = 'id'
                                lookup_value = vessel.get('refinery_id')
                            elif database_table.lower() == 'companies':
                                lookup_field = 'id'
                                lookup_value = vessel.get('company_id') or vessel.get('buyer_company_id') or vessel.get('seller_company_id')
                            else:
                                lookup_field = 'id'
                                lookup_value = vessel.get(f'{database_table.lower()}_id')
                            
                            if lookup_field and lookup_value is not None:
                                source_data = get_data_from_table(database_table, lookup_field, lookup_value)
                                if not source_data:
                                    logger.warning(f"  ⚠️  Could not fetch data from {database_table} using {lookup_field}={lookup_value}")
                                    source_data = vessel  # Fallback to vessel data
                            else:
                                logger.warning(f"  ⚠️  Could not determine lookup field/value for table {database_table}, using vessel data")
                                source_data = vessel
                        else:
                            # Use vessel data (default or explicitly 'vessels' table)
                            logger.info(f"  📋 Using vessel data (table: {database_table or 'vessels'})")
                            logger.info(f"  📋 Available fields: {list(vessel.keys())[:20]}...")

                        if source_data is not None and source_data:
                            if database_field:
                                # Try exact match first
                                if database_field in source_data:
                                    value = source_data[database_field]
                                    if value is not None and str(value).strip() != '':
                                        matched_field = database_field
                                        matched_value = str(value).strip()
                                        logger.info(f"  ✅ Exact match found: '{database_field}' = '{matched_value}'")
                                else:
                                    # Try case-insensitive match
                                    database_field_lower = database_field.lower()
                                    for key, value in source_data.items():
                                        if key.lower() == database_field_lower and value is not None and str(value).strip() != '':
                                            matched_field = key
                                            matched_value = str(value).strip()
                                            logger.info(f"  ✅ Case-insensitive match: '{database_field}' -> '{key}' = '{matched_value}'")
                                            break

                            if not matched_field and not database_field:
                                logger.info(f"  🔍 databaseField is empty, trying intelligent matching for '{placeholder}'...")
                                matched_field, matched_value = _intelligent_field_match(placeholder, source_data)
                                if matched_field:
                                    logger.info(f"  ✅ Intelligent match found: '{placeholder}' -> '{matched_field}' = '{matched_value}'")
                                else:
                                    logger.warning(f"  ⚠️  Intelligent matching failed for '{placeholder}'")

                            if not matched_field and database_field:
                                logger.info(f"  🔍 Explicit field '{database_field}' not found, trying intelligent matching...")
                                matched_field, matched_value = _intelligent_field_match(placeholder, source_data)
                                if matched_field:
                                    logger.info(f"  ✅ Intelligent fallback match: '{placeholder}' -> '{matched_field}' = '{matched_value}'")
                                else:
                                    logger.warning(f"  ⚠️  Intelligent fallback matching failed for '{placeholder}'")

                            if matched_field and matched_value:
                                data_mapping[placeholder] = _normalize_replacement_value(matched_value)
                                found = True
                                table_info = f" from {database_table}" if database_table and database_table.lower() != 'vessels' else ""
                                logger.info(f"  ✅✅✅ SUCCESS: {placeholder} = '{matched_value}' (from database field '{matched_field}'{table_info})")
                            else:
                                # Explicitly set found=False so cascade triggers
                                found = False
                                logger.warning(f"  ⚠️  Database source failed for '{placeholder}', will try cascade (DB → CSV → AI)")
                                if database_field:
                                    logger.warning(f"  ⚠️  Explicit field '{database_field}' not found in data")
                                logger.debug(f"  📋 Available fields: {list(source_data.keys())[:20]}...")
                        else:
                            # Explicitly set found=False so cascade triggers
                            found = False
                            logger.warning(f"  ⚠️  No data available from {database_table or 'vessels'} table, will try cascade")

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
                                            data_mapping[placeholder] = _normalize_replacement_value(value)
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
                                                    data_mapping[placeholder] = _normalize_replacement_value(value)
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

                except Exception as resolve_exc:
                    logger.error(f"  ❌❌❌ ERROR resolving data source for '{placeholder}': {resolve_exc}")
                    import traceback
                    logger.error(traceback.format_exc())
                    logger.warning(f"   Will use cascade (DB → CSV → AI) as fallback")

            if not found:
                # Cascade: CSV (CMS config) → smart CSV search → AI-generated realistic data
                logger.info(f"  🔍 {placeholder}: Cascade CSV → Smart CSV → AI (realistic fallback)")
                # 1. CSV (from CMS config) - try configured CSV first
                csv_val = _try_csv_for_placeholder(setting)
                if not csv_val:
                    # 2. Smart CSV search - search all CSVs for matching column
                    csv_val = _smart_csv_search(placeholder)
                if csv_val:
                    data_mapping[placeholder] = _normalize_replacement_value(csv_val)
                    found = True
                    logger.info(f"  ✅ CSV: {placeholder} = '{csv_val}'")
                if not found:
                    # 3. Always generate realistic AI data when no match – never use "—"
                    ai_val = generate_realistic_data_ai(placeholder, vessel, vessel_imo)
                    data_mapping[placeholder] = _normalize_replacement_value(ai_val)
                    found = True
                    logger.info(f"  ✅ AI (realistic fallback): {placeholder} = '{ai_val}'")
            else:
                logger.info(f"  ✓ {placeholder}: Successfully filled with configured data source")
        
        logger.info(f"Generated data mapping for {len(data_mapping)} placeholders")
        
        # Log matching summary
        logger.info("=" * 80)
        logger.info("📊 PLACEHOLDER MATCHING SUMMARY")
        logger.info("=" * 80)
        logger.info(f"✅ Matched with CMS settings: {len(matched_placeholders)} placeholders")
        if matched_placeholders:
            logger.info(f"   Matched: {matched_placeholders[:20]}...")
        logger.info(f"⚠️  Unmatched (using cascade DB→CSV→AI): {len(unmatched_placeholders)} placeholders")
        if unmatched_placeholders:
            logger.info(f"   Unmatched: {unmatched_placeholders[:20]}...")
            logger.warning("💡 TIP: Configure these placeholders in the CMS editor to use proper data sources")
        logger.info("=" * 80)
        
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
        
        # Flow: Template → PDF → [optional: images→PDF] → download
        # Image conversion is slow (30+ sec for multi-page); use fast_pdf=true to skip for quicker downloads
        fast_pdf = body.get('fast_pdf', True)  # Default True = skip image conversion for speed
        if pdf_path.endswith('.pdf') and os.path.exists(pdf_path):
            base_filename = f"{template_display_name}_{vessel_imo}"
            if fast_pdf:
                # Direct PDF - faster download (skip slow image rasterization)
                with open(pdf_path, 'rb') as f:
                    file_content = f.read()
                logger.info(f"Using direct PDF for download: {base_filename} ({len(file_content)} bytes)")
            else:
                logger.info(f"Converting PDF to images then to PDF for download: {base_filename}")
                try:
                    file_content = convert_pdf_to_images_then_to_pdf(pdf_path)
                    logger.info(f"Successfully created image-based PDF: {base_filename} ({len(file_content)} bytes)")
                except HTTPException:
                    raise
                except Exception as conv_error:
                    logger.error(f"Failed to convert PDF to images then PDF: {conv_error}", exc_info=True)
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to convert PDF: {str(conv_error)}. Please try again."
                    )
            media_type = "application/pdf"
            filename = f"{template_display_name}_{vessel_imo}.pdf"
        else:
            # If no PDF, return DOCX
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

        # Return file with properly encoded filename
        encoded_filename = quote(filename.encode('utf-8'))
        content_disposition = f'attachment; filename="{filename}"; filename*=UTF-8\'\'{encoded_filename}'
        
        headers = {
            "Content-Disposition": content_disposition,
            "Content-Type": media_type,
            "X-Content-Type-Options": "nosniff"
        }
        
        return Response(
            content=file_content,
            media_type=media_type,
            headers=headers
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error generating document: %s\n%s", e, traceback.format_exc())
        raise HTTPException(status_code=500, detail="Document generation failed")
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
    logger.info("AI upload mapping: enabled (database/csv/random per placeholder, disk fallback if no template_id)")
    uvicorn.run(app, host="0.0.0.0", port=8000)

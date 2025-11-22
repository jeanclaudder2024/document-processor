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
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    logger.warning("OpenAI library not installed. AI-powered random data generation will be disabled.")

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

# CRITICAL: Use service_role key for backend operations to bypass RLS
# Service role key has full access and bypasses Row-Level Security policies
SUPABASE_SERVICE_ROLE_KEY = os.getenv(
    "SUPABASE_SERVICE_ROLE_KEY",
    SUPABASE_KEY  # Fallback to regular key if service role key not set
)

try:
    # Use service_role key for backend operations (bypasses RLS)
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    logger.info("Successfully connected to Supabase (using service_role key for backend operations)")
except Exception as e:
    logger.error(f"Failed to connect to Supabase: {e}")
    supabase = None

SUPABASE_ENABLED = supabase is not None

# OpenAI Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_ENABLED = OPENAI_AVAILABLE and bool(OPENAI_API_KEY)
openai_client = None

if OPENAI_ENABLED:
    try:
        openai_client = OpenAI(api_key=OPENAI_API_KEY)
        logger.info("OpenAI client initialized successfully")
    except Exception as e:
        logger.warning(f"Failed to initialize OpenAI client: {e}")
        OPENAI_ENABLED = False
else:
    if not OPENAI_AVAILABLE:
        logger.info("OpenAI library not available")
    elif not OPENAI_API_KEY:
        logger.info("OPENAI_API_KEY not set in environment variables")


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
                .select('id, title, description, file_name, placeholders, is_active, created_at, updated_at, font_family, font_size') \
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
                
            supabase_settings[placeholder_key] = {
                'source': row.get('source', 'random'),
                'customValue': str(row.get('custom_value') or '').strip(),
                'databaseTable': str(row.get('database_table') or '').strip(),
                'databaseField': str(row.get('database_field') or '').strip(),
                'csvId': str(row.get('csv_id') or '').strip(),
                'csvField': str(row.get('csv_field') or '').strip(),
                'csvRow': int(row['csv_row']) if row.get('csv_row') is not None else 0,
                'randomOption': row.get('random_option', 'ai') or 'ai'
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
            rows.append({
                'template_id': template_id,
                'placeholder': placeholder,
                'source': cfg.get('source', 'random'),
                'custom_value': cfg.get('customValue'),
                'database_table': cfg.get('databaseTable') or cfg.get('database_table'),
                'database_field': cfg.get('databaseField') or cfg.get('database_field'),
                'csv_id': cfg.get('csvId') or cfg.get('csv_id'),
                'csv_field': cfg.get('csvField') or cfg.get('csv_field'),
                'csv_row': cfg.get('csvRow') or cfg.get('csv_row', 0),
                'random_option': cfg.get('randomOption') or cfg.get('random_option', 'ai')
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


def ensure_docx_filename(value: str) -> str:
    """Ensure filename ends with .docx (deprecated - use normalize_template_name with with_extension=True)."""
    return normalize_template_name(value, with_extension=True, for_key=False)


# ============================================================================
# STEP 2: AUTHENTICATION (Simple login with HttpOnly cookies)
# ============================================================================

def get_user_id_from_username(username: str) -> Optional[str]:
    """Get user_id from username/email"""
    if not SUPABASE_ENABLED or not username:
        return None
    
    try:
        # Try to get user_id from auth.users by email
        user_res = supabase.table('auth.users').select('id').eq('email', username).limit(1).execute()
        if user_res.data:
            return str(user_res.data[0]['id'])
        
        # Try subscribers table by email
        subscriber_res = supabase.table('subscribers').select('user_id').eq('email', username).limit(1).execute()
        if subscriber_res.data and subscriber_res.data[0].get('user_id'):
            return str(subscriber_res.data[0]['user_id'])
        
        return None
    except Exception as e:
        logger.error(f"Error getting user_id from username: {e}")
        return None

def get_user_plan_id(user_id: str) -> Optional[str]:
    """Get the user's current subscription plan ID"""
    if not SUPABASE_ENABLED or not user_id:
        return None
    
    try:
        # Get user's subscription tier
        subscriber_res = supabase.table('subscribers').select('subscription_tier, subscription_plan').eq('user_id', user_id).limit(1).execute()
        if not subscriber_res.data:
            return None
        
        subscriber = subscriber_res.data[0]
        plan_tier = subscriber.get('subscription_tier') or subscriber.get('subscription_plan')
        if not plan_tier:
            return None
        
        # Get plan ID from tier
        plan_res = supabase.table('subscription_plans').select('id').eq('plan_tier', plan_tier).eq('is_active', True).limit(1).execute()
        if plan_res.data:
            return str(plan_res.data[0]['id'])
        
        return None
    except Exception as e:
        logger.error(f"Error getting user plan ID: {e}")
        return None

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


@app.get("/debug-plan-permissions")
async def debug_plan_permissions(plan_tier: str = None):
    """Debug endpoint to check plan permissions in database"""
    if not SUPABASE_ENABLED or not supabase:
        return {"error": "Supabase not enabled"}
    
    try:
        result = {
            "plans": {},
            "templates": {},
            "permissions": {}
        }
        
        # Get all plans
        plans_res = supabase.table('subscription_plans').select('id, plan_tier, plan_name').eq('is_active', True).execute()
        if plans_res.data:
            for plan in plans_res.data:
                plan_id = plan['id']
                tier = plan.get('plan_tier', 'unknown')
                
                if plan_tier and tier != plan_tier:
                    continue
                
                result["plans"][tier] = {
                    "plan_id": str(plan_id),
                    "plan_tier": tier,
                    "plan_name": plan.get('plan_name', '')
                }
                
                # Get permissions for this plan
                perms_res = supabase.table('plan_template_permissions').select(
                    'template_id, can_download, max_downloads_per_template'
                ).eq('plan_id', plan_id).execute()
                
                result["permissions"][tier] = {
                    "plan_id": str(plan_id),
                    "count": len(perms_res.data) if perms_res.data else 0,
                    "permissions": perms_res.data if perms_res.data else []
                }
        
        # Get all templates
        templates_res = supabase.table('document_templates').select('id, file_name, is_active').execute()
        if templates_res.data:
            for template in templates_res.data:
                template_id = str(template['id'])
                result["templates"][template_id] = {
                    "file_name": template.get('file_name', ''),
                    "is_active": template.get('is_active', True)
                }
        
        return {
            "success": True,
            "data": result,
            "summary": {
                "total_plans": len(result["plans"]),
                "total_templates": len(result["templates"]),
                "plans_with_permissions": sum(1 for p in result["permissions"].values() if p["count"] > 0)
            }
        }
    except Exception as e:
        logger.error(f"Debug endpoint error: {e}", exc_info=True)
        return {"error": str(e), "traceback": str(e.__traceback__)}

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "supabase": "connected" if supabase else "disconnected",
        "openai": "enabled" if OPENAI_ENABLED else "disabled",
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
        # List of available tables with their display names
        tables = [
            {'name': 'vessels', 'label': 'Vessels', 'description': 'Vessel information and specifications'},
            {'name': 'ports', 'label': 'Ports', 'description': 'Port information and details'},
            {'name': 'refineries', 'label': 'Refineries', 'description': 'Refinery information'},
            {'name': 'companies', 'label': 'Companies', 'description': 'Company information'},
            {'name': 'brokers', 'label': 'Brokers', 'description': 'Broker information'},
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
                # Table exists but is empty, try to get schema info
                # For now, return empty list
                return {"success": True, "table": table_name, "columns": []}
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
    """Get predefined column list for known tables (fallback)"""
    predefined = {
        'vessels': [
            {'name': 'id', 'label': 'ID', 'type': 'integer'},
            {'name': 'name', 'label': 'Vessel Name', 'type': 'text'},
            {'name': 'imo', 'label': 'IMO Number', 'type': 'text'},
            {'name': 'mmsi', 'label': 'MMSI', 'type': 'text'},
            {'name': 'vessel_type', 'label': 'Vessel Type', 'type': 'text'},
            {'name': 'flag', 'label': 'Flag', 'type': 'text'},
            {'name': 'built', 'label': 'Year Built', 'type': 'integer'},
            {'name': 'deadweight', 'label': 'Deadweight', 'type': 'numeric'},
            {'name': 'cargo_capacity', 'label': 'Cargo Capacity', 'type': 'numeric'},
            {'name': 'length', 'label': 'Length', 'type': 'numeric'},
            {'name': 'width', 'label': 'Width', 'type': 'numeric'},
            {'name': 'beam', 'label': 'Beam', 'type': 'numeric'},
            {'name': 'draft', 'label': 'Draft', 'type': 'numeric'},
            {'name': 'gross_tonnage', 'label': 'Gross Tonnage', 'type': 'numeric'},
            {'name': 'owner_name', 'label': 'Owner Name', 'type': 'text'},
            {'name': 'operator_name', 'label': 'Operator Name', 'type': 'text'},
            {'name': 'callsign', 'label': 'Call Sign', 'type': 'text'},
        ],
        'ports': [
            {'name': 'id', 'label': 'ID', 'type': 'integer'},
            {'name': 'name', 'label': 'Port Name', 'type': 'text'},
            {'name': 'country', 'label': 'Country', 'type': 'text'},
            {'name': 'city', 'label': 'City', 'type': 'text'},
            {'name': 'latitude', 'label': 'Latitude', 'type': 'numeric'},
            {'name': 'longitude', 'label': 'Longitude', 'type': 'numeric'},
        ],
        'refineries': [
            {'name': 'id', 'label': 'ID', 'type': 'uuid'},
            {'name': 'name', 'label': 'Refinery Name', 'type': 'text'},
            {'name': 'location', 'label': 'Location', 'type': 'text'},
            {'name': 'capacity', 'label': 'Capacity', 'type': 'numeric'},
        ],
        'companies': [
            {'name': 'id', 'label': 'ID', 'type': 'integer'},
            {'name': 'name', 'label': 'Company Name', 'type': 'text'},
            {'name': 'country', 'label': 'Country', 'type': 'text'},
            {'name': 'type', 'label': 'Company Type', 'type': 'text'},
        ],
        'brokers': [
            {'name': 'id', 'label': 'ID', 'type': 'integer'},
            {'name': 'name', 'label': 'Broker Name', 'type': 'text'},
            {'name': 'email', 'label': 'Email', 'type': 'text'},
            {'name': 'phone', 'label': 'Phone', 'type': 'text'},
        ],
    }
    return predefined.get(table_name.lower(), [])

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
                    
                    # Get plan permissions for this template
                    plan_names = []
                    can_download_plans = []
                    display_plan_name = None  # Initialize before try block
                    
                    try:
                        # Get all plans that have permission for this template
                        perms_res = supabase.table('plan_template_permissions').select(
                            'plan_id, can_download, max_downloads_per_template'
                        ).eq('template_id', template_id).eq('can_download', True).execute()
                        
                        if perms_res.data:
                            plan_ids = [p['plan_id'] for p in perms_res.data]
                            if plan_ids:
                                # Get plan names
                                plans_info = supabase.table('subscription_plans').select(
                                    'id, plan_name, plan_tier'
                                ).in_('id', plan_ids).execute()
                                
                                if plans_info.data:
                                    plan_names = [p['plan_name'] for p in plans_info.data]
                                    can_download_plans = [p['plan_tier'] for p in plans_info.data]
                                    
                                    # Determine plan_name for display
                                    # Check if template has permissions for ALL active plans
                                    all_plans_res = supabase.table('subscription_plans').select('id').eq('is_active', True).execute()
                                    all_plan_ids = set(p['id'] for p in (all_plans_res.data or []))
                                    plan_ids_set = set(plan_ids)
                                    
                                    # Only show "All Plans" if template has permissions for EVERY active plan (exact match)
                                    if plan_ids_set == all_plan_ids and len(plan_ids_set) > 0 and len(all_plan_ids) > 0:
                                        display_plan_name = "All Plans"
                                        logger.debug(f"Template {template_id} ({file_name}) has permissions for all {len(all_plan_ids)} plans - showing 'All Plans'")
                                    elif len(plan_names) > 0:
                                        # Show specific plan names (what user configured in CMS)
                                        if len(plan_names) <= 2:
                                            display_plan_name = ", ".join(plan_names)
                                        else:
                                            display_plan_name = ", ".join(plan_names[:2]) + f" +{len(plan_names)-2} more"
                                        logger.debug(f"Template {template_id} ({file_name}) has permissions for {len(plan_names)} specific plans: {plan_names}")
                                    else:
                                        display_plan_name = None
                                else:
                                    # No plan info found
                                    display_plan_name = None
                            else:
                                # No plan IDs
                                display_plan_name = None
                        else:
                            # No permissions found - template is public/available to all
                            display_plan_name = None
                            logger.debug(f"Template {template_id} ({file_name}) has no plan permissions - available to all")
                    except Exception as perm_exc:
                        logger.debug(f"Could not fetch plan permissions for template {template_id}: {perm_exc}")
                        display_plan_name = None
                    
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
                        "is_active": record.get('is_active', True),
                        # Add plan information
                        "plan_name": display_plan_name,
                        "plan_tiers": can_download_plans,
                        "can_download": len(plan_names) > 0  # True if at least one plan has access
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
            # For local templates, check if they exist in database for plan permissions
            plan_names = []
            can_download_plans = []
            try:
                if SUPABASE_ENABLED:
                    # Try to find template in database by file_name
                    db_template_res = supabase.table('document_templates').select('id').eq('file_name', file_name).limit(1).execute()
                    if db_template_res.data:
                        db_template_id = db_template_res.data[0]['id']
                        # Get plan permissions
                        perms_res = supabase.table('plan_template_permissions').select(
                            'plan_id, can_download'
                        ).eq('template_id', db_template_id).eq('can_download', True).execute()
                        
                        if perms_res.data:
                            plan_ids = [p['plan_id'] for p in perms_res.data]
                            if plan_ids:
                                plans_info = supabase.table('subscription_plans').select('id, plan_name, plan_tier').in_('id', plan_ids).execute()
                                if plans_info.data:
                                    plan_names = [p['plan_name'] for p in plans_info.data]
                                    can_download_plans = [p['plan_tier'] for p in plans_info.data]
            except Exception:
                pass  # If we can't get plan info, template is still available (public)
            
            display_plan_name = ", ".join(plan_names) if plan_names else None
            
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
                "is_active": True,
                # Add plan information
                "plan_name": display_plan_name,
                "plan_tiers": can_download_plans,
                "can_download": len(plan_names) > 0 if plan_names else True  # Public if no plan restrictions
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
            # CRITICAL: Always use database, never fallback to plans.json when Supabase is enabled
            # Get plans from database - include ALL active plans (NOTE: broker is a membership, not a plan)
            plans_res = supabase.table('subscription_plans').select(
                '*').eq('is_active', True).order('sort_order', desc=False).execute()
            
            plan_count = len(plans_res.data) if plans_res.data else 0
            logger.info(f"[plans-db] Loading {plan_count} plans from database (NOT using plans.json cache)")
            plan_tiers = [p.get('plan_tier', 'unknown') for p in (plans_res.data or [])]
            logger.info(f"Fetched {plan_count} active plans from database")
            logger.info(f"Plan tiers found: {plan_tiers}")

            if not plans_res.data:
                # CRITICAL: Don't fallback to JSON - return empty plans
                # This ensures we always use database, not stale cache
                logger.warning(f"[plans-db] No plans found in database, returning empty plans (not using JSON fallback)")
                return {
                    "success": True,
                    "plans": {},
                    "source": "database_empty"
                }

            # Get all templates (may not exist yet, so handle gracefully)
            # CRITICAL: Query ALL templates (including inactive) to ensure we can map all template_ids from permissions
            template_map = {}
            all_template_ids = set()
            all_active_template_ids = set()
            try:
                templates_res = supabase.table('document_templates').select(
                    'id, file_name, title, is_active').execute()
                if templates_res.data:
                    # Include ALL templates in map (active and inactive) to ensure we can map all permissions
                    template_map = {t['id']: t for t in templates_res.data}
                    all_template_ids = set(t['id'] for t in templates_res.data)
                    all_active_template_ids = set(t['id'] for t in templates_res.data if t.get('is_active', True))
                    logger.info(f"Fetched {len(template_map)} templates from database ({len(all_active_template_ids)} active)")
            except Exception as e:
                logger.warning(f"Could not fetch templates from database: {e}")

            # Get permissions for each plan
            # NOTE: Filter out 'broker' as it's a membership, not a subscription plan
            plans_dict = {}
            for plan in plans_res.data:
                plan_tier = plan['plan_tier']
                
                # Skip broker - it's a membership, not a subscription plan
                if plan_tier and plan_tier.lower() == 'broker':
                    logger.info(f"Skipping broker plan (broker is a membership, not a subscription plan)")
                    continue

                # Get permissions for this plan (may not exist yet)
                allowed_templates = []
                template_limits = {}  # Store per-template download limits
                try:
                    # CRITICAL: Log the plan_id we're querying with
                    plan_db_id = plan['id']
                    logger.info(f"[plans-db] 🔍 Querying permissions for plan {plan_tier} (ID: {plan_db_id})")
                    
                    # CRITICAL: Fetch both can_download AND max_downloads_per_template
                    permissions_res = supabase.table('plan_template_permissions').select(
                        'template_id, can_download, max_downloads_per_template').eq('plan_id', plan_db_id).execute()

                    logger.info(f"[plans-db] 📊 Query result: {len(permissions_res.data) if permissions_res.data else 0} permission records found")
                    
                    if permissions_res.data:
                        logger.info(f"[plans-db] Plan {plan_tier} found {len(permissions_res.data)} permission records")
                        # Get all template IDs that this plan has permissions for
                        plan_template_ids = set()
                        skipped_permissions = []
                        for perm in permissions_res.data:
                            can_download_value = perm.get('can_download')
                            template_id = perm.get('template_id')
                            
                            logger.debug(f"[plans-db] Permission record: template_id={template_id}, can_download={can_download_value}")
                            
                            if can_download_value:  # True or truthy value
                                if template_id:
                                    plan_template_ids.add(template_id)
                                    
                                    # Store per-template download limit
                                    if perm.get('max_downloads_per_template') is not None:
                                        template_limits[str(template_id)] = perm['max_downloads_per_template']
                                    
                                    # Add template file_name to allowed_templates list
                                    template_info = template_map.get(template_id)
                                    if template_info:
                                        file_name = template_info.get('file_name', '')
                                        if file_name and file_name not in allowed_templates:
                                            allowed_templates.append(file_name)
                                            logger.debug(f"[plans-db] ✅ Added template '{file_name}' (ID: {template_id}) to allowed_templates")
                                        elif not file_name:
                                            logger.warning(f"[plans-db] ⚠️ Template ID {template_id} has no file_name in template_info")
                                    else:
                                        skipped_permissions.append(template_id)
                                        logger.warning(f"[plans-db] ⚠️ Template ID {template_id} not found in template_map (permission exists but template missing from map)")
                                else:
                                    logger.warning(f"[plans-db] ⚠️ Permission record has no template_id: {perm}")
                            else:
                                logger.debug(f"[plans-db] Skipping permission with can_download=False or None for template_id={template_id}")
                        
                        if skipped_permissions:
                            logger.warning(f"[plans-db] ⚠️ Plan {plan_tier} has {len(skipped_permissions)} permissions for templates not in template_map: {skipped_permissions[:3]}...")
                        logger.info(f"[plans-db] Plan {plan_tier} mapped {len(allowed_templates)} templates from {len(plan_template_ids)} permission template IDs")
                        
                        # CRITICAL: Check if plan has permissions for ALL available templates
                        # Only treat as "*" if plan has permissions for EVERY active template
                        total_templates_count = len(all_active_template_ids) if all_active_template_ids else len(all_template_ids)
                        plan_permissions_count = len(plan_template_ids)
                        
                        logger.info(f"[plans-db] Plan {plan_tier} (ID: {plan['id']}): {plan_permissions_count} permissions out of {total_templates_count} total active templates")
                        logger.info(f"[plans-db] Plan {plan_tier} template IDs: {list(plan_template_ids)[:3]}...")
                        logger.info(f"[plans-db] All active template IDs: {list(all_active_template_ids)[:3]}...")
                        logger.info(f"[plans-db] Plan {plan_tier} allowed templates: {allowed_templates[:3]}... ({len(allowed_templates)} total)")
                        
                        # If plan has permissions for ALL templates (exact match), treat as "*"
                        # CRITICAL: Must be EXACT match - plan_template_ids must equal all_active_template_ids
                        # AND there must be at least 1 template in the database
                        if total_templates_count > 0 and plan_permissions_count > 0:
                            # Check if plan has permissions for every single active template (exact set match)
                            # Use set comparison to ensure exact match
                            if plan_template_ids == all_active_template_ids and len(plan_template_ids) == len(all_active_template_ids) and len(all_active_template_ids) > 0:
                                logger.info(f"[plans-db] ✅ Plan {plan_tier} has permissions for ALL {total_templates_count} templates (exact match) - treating as '*'")
                                allowed_templates = ['*']
                            else:
                                # Plan has some permissions but not all - show specific templates
                                logger.info(f"[plans-db] ✅ Plan {plan_tier} has permissions for {plan_permissions_count} templates (not all {total_templates_count}) - showing specific templates")
                                logger.info(f"[plans-db] Plan template IDs set: {sorted(list(plan_template_ids))[:3]}...")
                                logger.info(f"[plans-db] All template IDs set: {sorted(list(all_template_ids))[:3]}...")
                                logger.info(f"[plans-db] Sets equal? {plan_template_ids == all_template_ids}")
                                # allowed_templates already contains the specific template names
                                # Make sure we don't accidentally return '*' if we have specific templates
                                if allowed_templates and allowed_templates != ['*']:
                                    logger.info(f"[plans-db] Returning specific templates: {allowed_templates[:3]}...")
                        elif plan_permissions_count > 0:
                            logger.info(f"[plans-db] ✅ Plan {plan_tier} has permissions for {plan_permissions_count} specific templates: {allowed_templates[:3]}...")
                        else:
                            logger.info(f"[plans-db] ⚠️ Plan {plan_tier} has NO template permissions - returning empty array")
                except Exception as e:
                    logger.warning(
                        f"Could not fetch permissions for plan {plan_tier}: {e}")
                    # CRITICAL: Don't default to '*' - return empty array
                    # This allows CMS to show "No templates selected" instead of "All templates"
                    allowed_templates = []
                    logger.info(f"[plans-db] Plan {plan_tier} - exception occurred, returning empty array (not '*')")

                # CRITICAL: If no permissions set, return empty array (not '*')
                # This allows the CMS to show "No templates selected" instead of "All templates"
                # Only default to '*' if permissions table doesn't exist (legacy fallback)
                if not allowed_templates:
                    # If we got here and allowed_templates is empty, it means:
                    # 1. No permissions were found in plan_template_permissions table
                    # 2. This could mean the plan has no specific template permissions
                    # Don't default to '*' - return empty array so CMS can show "No templates selected"
                    allowed_templates = []
                    logger.info(f"Plan {plan_tier} has NO template permissions - returning empty array (not '*')")

                # Normalize template names (ensure .docx extension)
                normalized_templates = []
                if allowed_templates:
                    for t in allowed_templates:
                        if t == '*':
                            normalized_templates.append('*')
                        elif isinstance(t, str) and t:
                            normalized_templates.append(
                                ensure_docx_filename(t))
                        else:
                            normalized_templates.append(str(t))
                
                logger.debug(f"Plan {plan_tier} can_download: {normalized_templates[:5]}... ({len(normalized_templates)} total)")

                plans_dict[plan_tier] = {
                    "id": str(plan['id']),
                    "name": plan['plan_name'],
                    "plan_tier": plan_tier,
                    "description": plan.get('description', ''),
                    "monthly_price": float(plan.get('monthly_price', 0)),
                    "annual_price": float(plan.get('annual_price', 0)),
                    "max_downloads_per_month": plan.get('max_downloads_per_month', 10),
                    "can_download": normalized_templates if normalized_templates else [],  # CRITICAL: Return empty array, not ['*'] - allows CMS to show "No templates selected"
                    "template_limits": template_limits,  # Include per-template download limits
                    "features": list(plan.get('features', [])) if isinstance(plan.get('features'), (list, tuple)) else (plan.get('features', []) if plan.get('features') else []),
                    "is_active": plan.get('is_active', True)
                }
            
            # Get broker membership template permissions
            broker_membership_dict = {}
            try:
                # Get all active broker memberships (for CMS display, we show broker membership as a single entity)
                # We'll create a single "broker" entry that represents broker membership
                broker_permissions_res = supabase.table('broker_template_permissions').select(
                    'broker_membership_id, template_id, can_download, max_downloads_per_template'
                ).execute()
                
                if broker_permissions_res.data:
                    # Group permissions by template to show which templates broker membership can access
                    broker_template_ids = set()
                    broker_allowed_templates = []
                    for perm in broker_permissions_res.data:
                        if perm.get('can_download'):
                            template_id = perm['template_id']
                            broker_template_ids.add(template_id)
                            
                            # Add template file_name to allowed_templates list
                            template_info = template_map.get(template_id)
                            if template_info:
                                file_name = template_info.get('file_name', '')
                                if file_name and file_name not in broker_allowed_templates:
                                    broker_allowed_templates.append(file_name)
                    
                    # Check if broker has permissions for ALL templates
                    total_templates_count = len(all_template_ids)
                    broker_permissions_count = len(broker_template_ids)
                    
                    if total_templates_count > 0 and broker_permissions_count >= total_templates_count:
                        if broker_template_ids == all_template_ids:
                            logger.info(f"Broker membership has permissions for ALL {total_templates_count} templates - treating as '*'")
                            broker_allowed_templates = ['*']
                    
                    # Normalize template names
                    normalized_broker_templates = []
                    if broker_allowed_templates:
                        for t in broker_allowed_templates:
                            if t == '*':
                                normalized_broker_templates.append('*')
                            elif isinstance(t, str) and t:
                                normalized_broker_templates.append(ensure_docx_filename(t))
                            else:
                                normalized_broker_templates.append(str(t))
                    
                    # Create broker membership entry (single entry for all broker memberships)
                    broker_membership_dict['broker'] = {
                        "id": "broker-membership",
                        "name": "Broker Membership",
                        "plan_tier": "broker",
                        "description": "Lifetime broker membership with access to selected templates",
                        "monthly_price": 0.0,
                        "annual_price": 0.0,
                        "max_downloads_per_month": None,  # Per-template limits are set individually
                        "can_download": normalized_broker_templates if normalized_broker_templates else ['*'],
                        "template_limits": broker_template_limits,  # Include per-template download limits
                        "features": ["Lifetime access", "Broker verification", "Deal management"],
                        "is_active": True,
                        "is_membership": True  # Flag to distinguish from subscription plans
                    }
                    logger.info(f"Added broker membership with {len(normalized_broker_templates)} template permissions")
                else:
                    # No broker permissions set yet - default to all templates
                    broker_membership_dict['broker'] = {
                        "id": "broker-membership",
                        "name": "Broker Membership",
                        "plan_tier": "broker",
                        "description": "Lifetime broker membership with access to selected templates",
                        "monthly_price": 0.0,
                        "annual_price": 0.0,
                        "max_downloads_per_month": None,
                        "can_download": ['*'],
                        "features": ["Lifetime access", "Broker verification", "Deal management"],
                        "is_active": True,
                        "is_membership": True
                    }
            except Exception as broker_error:
                logger.warning(f"Could not fetch broker membership permissions: {broker_error}")
                # Still add broker membership entry with default values
                broker_membership_dict['broker'] = {
                    "id": "broker-membership",
                    "name": "Broker Membership",
                    "plan_tier": "broker",
                    "description": "Lifetime broker membership with access to selected templates",
                    "monthly_price": 0.0,
                    "annual_price": 0.0,
                    "max_downloads_per_month": None,
                    "can_download": ['*'],
                    "features": ["Lifetime access", "Broker verification", "Deal management"],
                    "is_active": True,
                    "is_membership": True
                }
            
            # Merge plans and broker membership
            all_plans = {**plans_dict, **broker_membership_dict}
            
            return {"success": True, "plans": all_plans, "source": "database"}
        except Exception as db_error:
            logger.warning(f"Database query failed, falling back to JSON: {db_error}")
            # Fallback to JSON - filter out broker plan
            plans = read_json_file(PLANS_PATH, {})
            # Remove broker from plans (it's a membership, not a subscription plan)
            filtered_plans = {k: v for k, v in plans.items() if k.lower() != 'broker' and (not v.get('plan_tier') or v.get('plan_tier', '').lower() != 'broker')}
            return {"success": True, "plans": filtered_plans, "source": "json_fallback"}
    except Exception as e:
        logger.error(f"Error getting plans: {e}")
        # Final fallback - filter out broker plan
        try:
            plans = read_json_file(PLANS_PATH, {})
            # Remove broker from plans (it's a membership, not a subscription plan)
            filtered_plans = {k: v for k, v in plans.items() if k.lower() != 'broker' and (not v.get('plan_tier') or v.get('plan_tier', '').lower() != 'broker')}
            return {"success": True, "plans": filtered_plans, "source": "json_error_fallback"}
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
    payload: Dict = Body(...),
    current_user: str = Depends(get_current_user)
):
    """Update template metadata (display name, description, fonts, plan assignments)."""
    try:
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
        
        plan_ids = payload.get('plan_ids', [])  # Array of plan IDs
        if not isinstance(plan_ids, list):
            plan_ids = []
        
        requires_broker_membership = payload.get('requires_broker_membership', False)
        if not isinstance(requires_broker_membership, bool):
            requires_broker_membership = bool(requires_broker_membership)
        
        # AUTO-CONNECT: If no plan_ids provided, auto-connect to user's current plan
        if not plan_ids and SUPABASE_ENABLED:
            try:
                # Get user_id from request headers, payload, or current_user
                user_id = payload.get('user_id')
                if request:
                    user_id = user_id or request.headers.get('x-user-id')
                if not user_id and current_user:
                    # Try to get user_id from username/email
                    user_id = get_user_id_from_username(current_user)
                
                if user_id:
                    user_plan_id = get_user_plan_id(str(user_id))
                    if user_plan_id:
                        plan_ids = [user_plan_id]
                        logger.info(f"Auto-connected template to user's plan: {user_plan_id} (user: {current_user})")
            except Exception as auto_plan_exc:
                logger.warning(f"Could not auto-connect to user plan: {auto_plan_exc}")

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
                
                # Update requires_broker_membership if provided
                if 'requires_broker_membership' in payload:
                    # Try to update in database if column exists
                    try:
                        supabase.table('document_templates').update({'requires_broker_membership': requires_broker_membership}).eq('id', template_id_uuid).execute()
                        logger.info(f"Updated requires_broker_membership for template {template_id_uuid} to: {requires_broker_membership}")
                    except Exception as broker_exc:
                        # Column might not exist yet, store in metadata instead
                        logger.warning(f"Could not update requires_broker_membership in database (column may not exist): {broker_exc}")
                
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
                
                # Update plan assignments
                if plan_ids is not None:
                    try:
                        logger.info(f"Updating plan permissions for template {template_id_uuid} with plan_ids: {plan_ids}")
                        
                        # Delete existing permissions
                        supabase.table('plan_template_permissions').delete().eq('template_id', template_id_uuid).execute()
                        logger.info(f"Deleted existing permissions for template {template_id_uuid}")
                        
                        # Insert new permissions
                        if plan_ids:
                            # CRITICAL: plan_ids can be plan_tier (basic, professional) or plan_id (UUID)
                            # We need to convert plan_tier to plan_id (UUID)
                            permission_rows = []
                            for plan_identifier in plan_ids:
                                if not plan_identifier:
                                    continue
                                
                                # Try to get plan_id from plan_tier
                                plan_id_uuid = None
                                try:
                                    # First, check if plan_identifier is already a UUID
                                    plan_uuid_test = uuid.UUID(str(plan_identifier))
                                    plan_id_uuid = str(plan_uuid_test)
                                    logger.debug(f"plan_identifier {plan_identifier} is a UUID: {plan_id_uuid}")
                                except (ValueError, TypeError):
                                    # Not a UUID, try to find by plan_tier
                                    logger.debug(f"plan_identifier {plan_identifier} is not a UUID, trying to find by plan_tier")
                                    plan_res = supabase.table('subscription_plans').select('id').eq('plan_tier', str(plan_identifier)).eq('is_active', True).limit(1).execute()
                                    if plan_res.data and len(plan_res.data) > 0:
                                        plan_id_uuid = str(plan_res.data[0]['id'])
                                        logger.info(f"Found plan_id {plan_id_uuid} for plan_tier {plan_identifier}")
                                    else:
                                        logger.warning(f"Could not find plan_id for plan_tier {plan_identifier}")
                                
                                if plan_id_uuid:
                                    permission_rows.append({
                                        'plan_id': plan_id_uuid,
                                        'template_id': str(template_id_uuid),
                                        'can_download': True
                                    })
                                    logger.debug(f"Added permission for plan_id {plan_id_uuid} (from plan_identifier {plan_identifier})")
                            
                            if permission_rows:
                                logger.info(f"Inserting {len(permission_rows)} plan permissions for template {template_id_uuid}")
                                logger.info(f"Plan permission rows: {[r['plan_id'] for r in permission_rows]}")
                                permissions_response = supabase.table('plan_template_permissions').insert(permission_rows).execute()
                                if getattr(permissions_response, "error", None):
                                    logger.error(f"Plan permissions insert error: {permissions_response.error}")
                                    logger.error(f"Failed permission rows: {permission_rows}")
                                else:
                                    logger.info(f"✅ Successfully updated plan permissions for {len(permission_rows)} plans (template: {template_id_uuid})")
                                    logger.info(f"Inserted permissions: {[r['plan_id'] for r in permission_rows]}")
                            else:
                                logger.info(f"No plan permissions to insert for template {template_id_uuid} (plan_ids was empty or could not resolve to UUIDs)")
                                # IMPORTANT: If no plan_ids provided, template has no plan restrictions (available to all plans)
                                # This is OK - the template will be available to all plans
                                logger.info(f"Template {template_id_uuid} will be available to all plans (no specific plan permissions set)")
                                
                                # CRITICAL: Delete existing permissions to ensure template is available to all
                                try:
                                    delete_result = supabase.table('plan_template_permissions').delete().eq('template_id', template_id_uuid).execute()
                                    logger.info(f"Deleted existing permissions for template {template_id_uuid} (making it available to all plans)")
                                except Exception as del_exc:
                                    logger.warning(f"Could not delete existing permissions: {del_exc}")
                    except Exception as perm_exc:
                        logger.error(f"Error updating plan permissions: {perm_exc}")
                        import traceback
                        logger.error(traceback.format_exc())
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
                "requires_broker_membership": requires_broker_membership if 'requires_broker_membership' in payload else None,
                "updated_at": datetime.utcnow().isoformat()
            }
            update_template_metadata_entry(docx_name, {k: v for k, v in metadata_updates.items() if v is not None})

        # Get plan_tiers for plan_ids (for response)
        plan_tiers = []
        if plan_ids and template_record:
            try:
                # Convert plan_id (UUID) to plan_tier for response
                for plan_id in plan_ids:
                    try:
                        # Try to find plan by UUID
                        plan_res = supabase.table('subscription_plans').select('plan_tier').eq('id', str(plan_id)).limit(1).execute()
                        if plan_res.data and len(plan_res.data) > 0:
                            plan_tiers.append(plan_res.data[0]['plan_tier'])
                        else:
                            # If not found by UUID, maybe it's already a plan_tier
                            plan_tiers.append(str(plan_id))
                    except Exception:
                        # If error, just use plan_id as-is (might be plan_tier)
                        plan_tiers.append(str(plan_id))
            except Exception as e:
                logger.warning(f"Could not convert plan_ids to plan_tiers: {e}")
                plan_tiers = plan_ids
        
        return {
            "success": True,
            "template_id": str(template_record['id']) if template_record else template_id,
            "template": template_record.get('file_name') if template_record else template_id,
            "metadata": {
                "display_name": display_name or None,
                "description": description or None,
                "font_family": font_family,
                "font_size": font_size,
                "requires_broker_membership": requires_broker_membership if 'requires_broker_membership' in payload else None
            },
            "plan_ids": plan_tiers if plan_tiers else plan_ids  # Return plan_tiers for easier use in frontend
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
    request: Request = None,
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
        
        # AUTO-CONNECT: If no plan_ids provided, auto-connect to user's current plan
        if not plan_ids_list and SUPABASE_ENABLED:
            try:
                # Get user_id from request headers or current_user
                user_id = request.headers.get('x-user-id')
                if not user_id and current_user:
                    # Try to get user_id from username/email
                    user_id = get_user_id_from_username(current_user)
                
                if user_id:
                    user_plan_id = get_user_plan_id(str(user_id))
                    if user_plan_id:
                        plan_ids_list = [user_plan_id]
                        logger.info(f"Auto-connected uploaded template to user's plan: {user_plan_id} (user: {current_user})")
            except Exception as auto_plan_exc:
                logger.warning(f"Could not auto-connect uploaded template to user plan: {auto_plan_exc}")

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

                    existing_settings = fetch_template_placeholders(template_id, template_record.get('file_name'))
                    missing_placeholders = [
                        {
                            'template_id': template_id,
                            'placeholder': placeholder,
                            'source': 'random',
                            'random_option': 'ai'
                        }
                        for placeholder in placeholders
                        if placeholder not in existing_settings
                    ]
                    if missing_placeholders:
                        placeholders_response = supabase.table('template_placeholders').insert(missing_placeholders).execute()
                        if getattr(placeholders_response, "error", None):
                            warnings.append("Supabase placeholder sync error; using local settings")
                            logger.error(f"Supabase placeholder insert error: {placeholders_response.error}")
                    
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
                                        'can_download': True
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
                'randomOption': 'ai'
            })

        upsert_template_placeholders(template_id or docx_filename, default_settings, docx_filename)

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
                'template_id, placeholder, source, custom_value, database_table, database_field, csv_id, csv_field, csv_row, random_option'
            ).execute()

            aggregated: Dict[str, Dict[str, Dict]] = {}
            for row in response.data or []:
                template_id = str(row['template_id'])
                aggregated.setdefault(template_id, {})[row['placeholder']] = {
                    'source': row.get('source', 'random'),
                    'customValue': row.get('custom_value') or '',
                    'databaseTable': row.get('database_table') or '',
                    'databaseField': row.get('database_field') or '',
                    'csvId': row.get('csv_id') or '',
                    'csvField': row.get('csv_field') or '',
                    'csvRow': row['csv_row'] if row.get('csv_row') is not None else 0,
                    'randomOption': row.get('random_option', 'ai') or 'ai'
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

            # Normalise payload to Supabase schema then upsert
            sanitised_settings: Dict[str, Dict] = {}
            for placeholder, cfg in new_settings.items():
                if not placeholder:
                    continue
                sanitised_settings[placeholder] = {
                    'source': cfg.get('source', 'random'),
                    'customValue': str(cfg.get('customValue', '')).strip() if cfg.get('customValue') else '',
                    'databaseTable': str(cfg.get('databaseTable', '')).strip() if cfg.get('databaseTable') else '',
                    'databaseField': str(cfg.get('databaseField', '')).strip() if cfg.get('databaseField') else '',
                    'csvId': str(cfg.get('csvId', '')).strip() if cfg.get('csvId') else '',
                    'csvField': str(cfg.get('csvField', '')).strip() if cfg.get('csvField') else '',
                    'csvRow': int(cfg.get('csvRow', 0)) if cfg.get('csvRow') is not None else 0,
                    'randomOption': cfg.get('randomOption', 'ai') or 'ai'
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
        
        # CRITICAL: Track if database update was successful
        database_update_success = False
        db_plan_id = None
        
        # If Supabase is available, update in database
        if supabase:
            try:
                logger.info(f"[update-plan] 🔍 Searching for plan: '{plan_id}'")
                
                # First, try to find by plan_tier (case-sensitive, most common case)
                plan_res = supabase.table('subscription_plans').select('id, plan_tier, plan_name').eq('plan_tier', str(plan_id)).limit(1).execute()
                if plan_res.data and len(plan_res.data) > 0:
                    db_plan_id = plan_res.data[0]['id']
                    found_plan_tier = plan_res.data[0].get('plan_tier')
                    logger.info(f"[update-plan] ✅ Found plan '{plan_id}' by plan_tier, UUID: {db_plan_id}, Name: {plan_res.data[0].get('plan_name')}, Tier: {found_plan_tier}")
                else:
                    # Try case-insensitive search by fetching all plans and comparing
                    logger.debug(f"[update-plan] ⚠️ Exact match not found for plan_tier='{plan_id}', trying case-insensitive search...")
                    all_plans_res = supabase.table('subscription_plans').select('id, plan_tier, plan_name').eq('is_active', True).execute()
                    if all_plans_res.data:
                        for p in all_plans_res.data:
                            if p.get('plan_tier', '').lower() == str(plan_id).lower():
                                db_plan_id = p['id']
                                logger.info(f"[update-plan] ✅ Found plan '{plan_id}' by case-insensitive plan_tier, UUID: {db_plan_id}, Name: {p.get('plan_name')}, Tier: {p.get('plan_tier')}")
                                break
                    
                    # If still not found, try by UUID if plan_id might be a UUID
                    if not db_plan_id:
                        try:
                            plan_uuid_test = uuid.UUID(str(plan_id))
                            plan_res = supabase.table('subscription_plans').select('id, plan_tier, plan_name').eq('id', str(plan_uuid_test)).limit(1).execute()
                            if plan_res.data and len(plan_res.data) > 0:
                                db_plan_id = plan_res.data[0]['id']
                                logger.info(f"[update-plan] ✅ Found plan '{plan_id}' by UUID: {db_plan_id}, Name: {plan_res.data[0].get('plan_name')}")
                        except (ValueError, TypeError):
                            logger.debug(f"[update-plan] plan_id '{plan_id}' is not a UUID")
                
                if not db_plan_id:
                    logger.error(f"[update-plan] ❌ Plan '{plan_id}' not found in database (tried plan_tier exact, case-insensitive, and UUID)")
                    # List available plans for debugging
                    try:
                        all_plans_debug = supabase.table('subscription_plans').select('plan_tier, plan_name, id').eq('is_active', True).execute()
                        if all_plans_debug.data:
                            available_tiers = [p.get('plan_tier') for p in all_plans_debug.data]
                            logger.error(f"[update-plan] 📋 Available plan_tiers in database: {available_tiers}")
                    except Exception as debug_exc:
                        logger.warning(f"[update-plan] Could not list available plans: {debug_exc}")
                    # Don't raise 404 here - try JSON fallback first
                    database_update_success = False
                else:
                    logger.info(f"[update-plan] ✅ Found plan '{plan_id}', proceeding with update...")
                    
                    # Update max_downloads_per_month
                    update_data = {}
                    if 'max_downloads_per_month' in plan_data:
                        max_downloads = plan_data['max_downloads_per_month']
                        update_data['max_downloads_per_month'] = max_downloads
                        logger.info(f"Updating max_downloads_per_month for plan {plan_id} to: {max_downloads}")
                    
                    if update_data:
                        result = supabase.table('subscription_plans').update(update_data).eq('id', db_plan_id).execute()
                        if result.data:
                            logger.info(f"✅ Successfully updated plan {plan_id}: {update_data}")
                        else:
                            logger.warning(f"⚠️ Plan update returned no data for plan {plan_id}")
                    
                    # Update template permissions if provided
                    # Check both 'allowed_templates' and 'can_download' for compatibility
                    allowed = plan_data.get('allowed_templates') or plan_data.get('can_download')
                    
                    logger.info(f"[update-plan] 📥 Received 'allowed' value: {allowed}")
                    logger.info(f"[update-plan] 📥 Type of 'allowed': {type(allowed)}")
                    if isinstance(allowed, dict):
                        logger.info(f"[update-plan] 📥 Dict keys: {list(allowed.keys())}")
                        logger.info(f"[update-plan] 📥 Dict values: {allowed}")
                    
                    # Get per-template limits if provided
                    template_limits = plan_data.get('template_limits', {})  # {template_id: max_downloads, ...}
                    
                    # CRITICAL: Handle new format with template_ids and template_names
                    template_ids_from_request = None
                    if isinstance(allowed, dict):
                        # New format: {template_ids: [...], template_names: [...]}
                        template_ids_from_request = allowed.get('template_ids', [])
                        template_names_from_request = allowed.get('template_names', [])
                        # Filter out empty strings and None values from template_ids
                        template_ids_from_request = [tid for tid in template_ids_from_request if tid and str(tid).strip()]
                        template_names_from_request = [tname for tname in template_names_from_request if tname and str(tname).strip()]
                        
                        if template_ids_from_request:
                            logger.info(f"[update-plan] Using template IDs format: {len(template_ids_from_request)} IDs")
                            allowed = template_ids_from_request  # Use IDs for matching
                        elif template_names_from_request:
                            logger.info(f"[update-plan] Using template names format: {len(template_names_from_request)} names")
                            allowed = template_names_from_request  # Fallback to names
                        else:
                            logger.error(f"[update-plan] ❌ Both template_ids and template_names are empty or invalid!")
                            logger.error(f"[update-plan] ❌ Original allowed value: {allowed}")
                            logger.error(f"[update-plan] ❌ This means NO templates were selected in frontend!")
                            allowed = []  # Explicitly set to empty list
                    
                    logger.info(f"[update-plan] 📊 Final 'allowed' value after processing: {allowed}")
                    logger.info(f"[update-plan] 📊 Will process permissions: {bool(allowed)}")
                    
                    if allowed:
                        # Get all templates (including inactive for matching, but we'll only insert active ones)
                        # CRITICAL: Query ALL templates first to ensure we can match template IDs even if they're inactive
                        templates_res_all = supabase.table('document_templates').select('id, file_name, is_active').execute()
                        # Filter to active templates for insertion
                        templates_res = type('obj', (object,), {'data': [t for t in (templates_res_all.data or []) if t.get('is_active', True)]})()
                        
                        logger.info(f"[update-plan] 📊 Found {len(templates_res_all.data) if templates_res_all.data else 0} total templates ({len(templates_res.data) if templates_res.data else 0} active)")
                        
                        if templates_res.data:
                            # CRITICAL: Delete existing permissions FIRST to clear old data
                            delete_result = supabase.table('plan_template_permissions').delete().eq('plan_id', db_plan_id).execute()
                            deleted_count = len(delete_result.data) if delete_result.data else 0
                            logger.info(f"[update-plan] Deleted {deleted_count} existing permissions for plan {plan_id}")
                            
                            # Create new permissions
                            if allowed == '*' or allowed == ['*'] or (isinstance(allowed, list) and '*' in allowed):
                                # Allow all templates
                                for template in templates_res.data:
                                    template_id = template['id']
                                    max_downloads = template_limits.get(str(template_id)) if isinstance(template_limits, dict) else None
                                    # Convert to int if it's a string
                                    if max_downloads is not None:
                                        try:
                                            max_downloads = int(max_downloads) if max_downloads != '' else None
                                        except (ValueError, TypeError):
                                            max_downloads = None
                                    
                                    permission_data = {
                                        'plan_id': db_plan_id,
                                        'template_id': template_id,
                                        'can_download': True
                                    }
                                    if max_downloads is not None:
                                        permission_data['max_downloads_per_template'] = max_downloads
                                    
                                    supabase.table('plan_template_permissions').insert(permission_data).execute()
                                logger.info(f"Set all templates permission for plan {plan_id}")
                            elif isinstance(allowed, list) and len(allowed) > 0:
                                # Check if this is a list of template IDs (UUIDs) or template names
                                is_uuid_list = all(isinstance(item, str) and len(item) == 36 and '-' in item for item in allowed[:3])
                                
                                if is_uuid_list or template_ids_from_request:
                                    # This is a list of template IDs - direct matching
                                    logger.info(f"[update-plan] Processing {len(allowed)} template IDs")
                                    logger.info(f"[update-plan] 📋 Template IDs from request: {template_ids_from_request}")
                                    logger.info(f"[update-plan] 📋 Template IDs in allowed list: {allowed[:5]}...")
                                    inserted_count = 0
                                    for template_id_str in allowed:
                                        try:
                                            # CRITICAL: Find template by ID - don't filter by is_active when matching by exact ID
                                            # We match by exact UUID, so we should find it regardless of active status
                                            template_res = supabase.table('document_templates').select('id, file_name, is_active').eq('id', template_id_str).limit(1).execute()
                                            
                                            if template_res.data and len(template_res.data) > 0:
                                                template = template_res.data[0]
                                                template_id = template['id']
                                                
                                                # Check if template is active - warn but still allow (for backward compatibility)
                                                if not template.get('is_active', True):
                                                    logger.warning(f"[update-plan] ⚠️ Template ID {template_id_str} ({template.get('file_name', 'unknown')}) is inactive, but creating permission anyway")
                                                
                                                # Get per-template limit if provided
                                                max_downloads = None
                                                if isinstance(template_limits, dict):
                                                    max_downloads = template_limits.get(str(template_id)) or template_limits.get(template_id)
                                                    if max_downloads is not None:
                                                        try:
                                                            max_downloads = int(max_downloads) if max_downloads != '' else None
                                                        except (ValueError, TypeError):
                                                            max_downloads = None
                                                
                                                permission_data = {
                                                    'plan_id': db_plan_id,
                                                    'template_id': template_id,
                                                    'can_download': True
                                                }
                                                if max_downloads is not None:
                                                    permission_data['max_downloads_per_template'] = max_downloads
                                                
                                                insert_result = supabase.table('plan_template_permissions').insert(permission_data).execute()
                                                inserted_count += 1
                                                logger.info(f"[update-plan] ✅ Added permission for template ID {template_id} ({template.get('file_name', 'unknown')}) to plan_id {db_plan_id}")
                                                logger.info(f"[update-plan] 📋 Insert result: {len(insert_result.data) if insert_result.data else 0} records inserted")
                                            else:
                                                logger.error(f"[update-plan] ❌ Template ID {template_id_str} NOT FOUND in database!")
                                                logger.error(f"[update-plan] ❌ This means the template_id sent from frontend doesn't exist in document_templates table")
                                                logger.error(f"[update-plan] ❌ Check if template was deleted or ID is incorrect")
                                        except Exception as id_exc:
                                            logger.warning(f"[update-plan] Failed to process template ID {template_id_str}: {id_exc}")
                                    
                                    logger.info(f"[update-plan] ✅ Set {inserted_count} template permissions using IDs")
                                else:
                                    # This is a list of template names - use name matching
                                    logger.info(f"[update-plan] Processing {len(allowed)} template names")
                                # Normalize template names from can_download list (may have .docx or not)
                                # Store both normalized keys AND original names for flexible matching
                                template_names_normalized = set()
                                template_names_original = {}  # Map normalized -> original for logging
                                
                                for t in allowed:
                                    if t != '*':
                                        # Store original
                                        original = t.strip()
                                        
                                        # Ensure .docx extension for comparison
                                        normalized = ensure_docx_filename(original)
                                        
                                        # Add multiple normalization strategies
                                        key1 = normalise_template_key(normalized)  # With .docx
                                        key2 = normalise_template_key(original.replace('.docx', '').replace('.DOCX', ''))  # Without extension
                                        
                                        template_names_normalized.add(key1)
                                        template_names_normalized.add(key2)
                                        
                                        # Also add original (normalized) for direct comparison
                                        template_names_normalized.add(normalized.lower().strip())
                                        template_names_normalized.add(original.lower().strip().replace('.docx', '').replace('.DOCX', ''))
                                        
                                        template_names_original[key1] = original
                                        template_names_original[key2] = original
                                
                                logger.info(f"[update-plan] 🔍 Matching templates for plan {plan_id}")
                                logger.info(f"[update-plan] 📋 Received template names: {allowed[:5]}...")
                                logger.info(f"[update-plan] 📋 Normalized keys: {list(template_names_normalized)[:5]}...")
                                logger.info(f"[update-plan] 📋 Available templates in DB: {[t.get('file_name', '') for t in templates_res.data[:10]]}")

                                inserted_count = 0
                                for template in templates_res.data:
                                    template_name = template.get('file_name', '').strip()
                                    if not template_name:
                                        continue
                                    
                                    # Try multiple normalization strategies for matching
                                    # Strategy 1: Normalize with .docx
                                    normalized_with_ext = normalise_template_key(ensure_docx_filename(template_name))
                                    # Strategy 2: Normalize without extension
                                    normalized_no_ext = normalise_template_key(template_name.replace('.docx', '').replace('.DOCX', ''))
                                    # Strategy 3: Direct lowercase comparison
                                    template_lower = template_name.lower().strip()
                                    template_lower_no_ext = template_lower.replace('.docx', '').replace('.docx', '')
                                    
                                    # Check if this template matches any in the allowed list
                                    # Try multiple matching strategies for flexibility
                                    matches = False
                                    matched_key = None
                                    
                                    # Try all normalization strategies
                                    for test_key in [normalized_with_ext, normalized_no_ext, template_lower, template_lower_no_ext]:
                                        if test_key in template_names_normalized:
                                            matches = True
                                            matched_key = test_key
                                            original_name = template_names_original.get(test_key, test_key)
                                            logger.info(f"[update-plan] ✅ Matched template '{template_name}' (normalized: '{test_key}') with allowed '{original_name}'")
                                            break
                                    
                                    # If still no match, try fuzzy matching (case-insensitive, ignore extra spaces)
                                    if not matches:
                                        for allowed_original in allowed:
                                            if allowed_original == '*':
                                                continue
                                            # Normalize both for comparison
                                            allowed_normalized = normalise_template_key(ensure_docx_filename(allowed_original))
                                            template_normalized = normalise_template_key(ensure_docx_filename(template_name))
                                            
                                            # Try direct comparison after normalization
                                            if allowed_normalized == template_normalized:
                                                matches = True
                                                matched_key = allowed_normalized
                                                logger.info(f"[update-plan] ✅ Matched template '{template_name}' with allowed '{allowed_original}' (fuzzy match)")
                                                break
                                    
                                    if not matches:
                                        logger.debug(f"[update-plan] ❌ Template '{template_name}' did not match any allowed templates")
                                    
                                    if matches:
                                        try:
                                            template_id = template['id']
                                            # Get per-template limit if provided
                                            max_downloads = None
                                            if isinstance(template_limits, dict):
                                                # Try both string and UUID key
                                                max_downloads = template_limits.get(str(template_id)) or template_limits.get(template_id)
                                                if max_downloads is not None:
                                                    try:
                                                        max_downloads = int(max_downloads) if max_downloads != '' else None
                                                    except (ValueError, TypeError):
                                                        max_downloads = None
                                            
                                            permission_data = {
                                                'plan_id': db_plan_id,
                                                'template_id': template_id,
                                                'can_download': True
                                            }
                                            if max_downloads is not None:
                                                permission_data['max_downloads_per_template'] = max_downloads
                                            
                                            supabase.table('plan_template_permissions').insert(permission_data).execute()
                                            inserted_count += 1
                                            logger.debug(f"Added permission for template {template_name} (ID: {template_id}) to plan {plan_id} with limit {max_downloads}")
                                        except Exception as insert_exc:
                                            logger.warning(f"Failed to insert permission for template {template_name}: {insert_exc}")
                                
                                logger.info(f"[update-plan] ✅ Set {inserted_count} template permissions for plan {plan_id} (matched {len(template_names_normalized)} template names)")
                                
                                # CRITICAL: If no templates were matched, log error
                                if inserted_count == 0:
                                    logger.error(f"[update-plan] ❌❌❌ NO TEMPLATES MATCHED FOR PLAN {plan_id}!")
                                    logger.error(f"[update-plan] ❌ Sent templates: {allowed[:5]}...")
                                    logger.error(f"[update-plan] ❌ Available templates in DB: {[t.get('file_name', '') for t in (templates_res.data or [])[:5]]}")
                                    logger.error(f"[update-plan] ❌ Template IDs sent: {template_ids_from_request[:5] if template_ids_from_request else 'NONE'}...")
                                    logger.error(f"[update-plan] ❌ This means NO permissions will be saved! Plan will have 0 templates!")
                    
                    logger.info(f"Updated plan in database: {plan_id}")
                    database_update_success = True
                    
                    # Return success response with updated plan data
                    # Get updated plan from database
                    updated_plan_res = supabase.table('subscription_plans').select('*').eq('id', db_plan_id).limit(1).execute()
                    if updated_plan_res.data:
                        updated_plan_data = updated_plan_res.data[0]
                        # CRITICAL: Wait a moment for database to be ready, then get fresh permissions
                        import time
                        time.sleep(0.5)  # Increased delay to ensure database transaction is committed
                        
                        # Get template permissions for response (including per-template limits)
                        # CRITICAL: Filter by can_download=True to ensure we only get valid permissions
                        perms_res = supabase.table('plan_template_permissions').select('template_id, max_downloads_per_template, can_download').eq('plan_id', db_plan_id).eq('can_download', True).execute()
                        template_ids = [p['template_id'] for p in (perms_res.data or []) if p.get('can_download', True)]
                        
                        logger.info(f"[update-plan] After save - Found {len(template_ids)} template permissions for plan {plan_id}")
                        if len(template_ids) == 0:
                            logger.warning(f"[update-plan] ⚠️⚠️⚠️ NO PERMISSIONS FOUND AFTER SAVE! This means save failed or permissions were cleared.")
                        
                        # Build template_limits dict for response
                        template_limits_response = {}
                        for perm in (perms_res.data or []):
                            template_id = perm['template_id']
                            max_downloads = perm.get('max_downloads_per_template')
                            if max_downloads is not None:
                                template_limits_response[str(template_id)] = max_downloads
                        
                        # Check if all templates - need to convert template_ids to file_names for response
                        # CRITICAL: Query ALL templates (including inactive) to ensure we can map all template_ids from permissions
                        all_templates = supabase.table('document_templates').select('id, file_name, is_active').execute()
                        all_active_template_ids = set(t['id'] for t in (all_templates.data or []) if t.get('is_active', True))
                        plan_template_ids_set = set(template_ids)
                        
                        logger.info(f"[update-plan] Plan {plan_id} has permissions for {len(plan_template_ids_set)} templates out of {len(all_active_template_ids)} total active templates")
                        logger.info(f"[update-plan] Plan template IDs: {list(plan_template_ids_set)[:5]}...")
                        logger.info(f"[update-plan] All active template IDs: {list(all_active_template_ids)[:5]}...")
                        logger.info(f"[update-plan] Sets equal? {plan_template_ids_set == all_active_template_ids}")
                        
                        # Convert template IDs to file names for CMS response
                        # CRITICAL: Include ALL templates in map (active and inactive) to ensure we can map all permissions
                        template_id_to_name = {t['id']: t.get('file_name', '') for t in (all_templates.data or [])}
                        template_file_names = []
                        missing_template_ids = []
                        for tid in template_ids:
                            if tid:
                                template_name = template_id_to_name.get(tid)
                                if template_name:
                                    template_file_names.append(ensure_docx_filename(template_name))
                                else:
                                    missing_template_ids.append(tid)
                                    logger.warning(f"[update-plan] ⚠️ Template ID {tid} not found in template map - permission exists but template missing!")
                        
                        if missing_template_ids:
                            logger.warning(f"[update-plan] ⚠️ {len(missing_template_ids)} template IDs from permissions not found in database: {missing_template_ids[:3]}...")
                        
                        logger.info(f"[update-plan] Template file names for response: {template_file_names[:5]}... (total: {len(template_file_names)})")
                        
                        # CRITICAL: Only return '*' if plan has permissions for EVERY single template (exact set match)
                        # AND there are actually templates in the database
                        is_all_templates = (all_active_template_ids and 
                                          len(all_active_template_ids) > 0 and 
                                          len(plan_template_ids_set) > 0 and
                                          plan_template_ids_set == all_active_template_ids)
                        can_download = ['*'] if is_all_templates else (template_file_names if template_file_names else [])
                        
                        logger.info(f"[update-plan] Returning can_download: {'[*]' if is_all_templates else f'{len(template_file_names)} specific templates'}")
                        if not is_all_templates and not template_file_names:
                            logger.warning(f"[update-plan] ⚠️ Plan {plan_id} has NO template permissions! Returning empty array.")
                        
                        return {
                            "success": True,
                            "plan_id": plan_id,
                            "plan_data": {
                                "id": str(updated_plan_data['id']),
                                "name": updated_plan_data.get('plan_name'),
                                "plan_tier": updated_plan_data.get('plan_tier'),
                                "max_downloads_per_month": updated_plan_data.get('max_downloads_per_month', 10),
                                "can_download": can_download,
                                "template_limits": template_limits_response if template_limits_response else None,
                                "features": list(updated_plan_data.get('features', [])) if isinstance(updated_plan_data.get('features'), (list, tuple)) else []
                            }
                        }
            except HTTPException:
                raise
            except Exception as e:
                logger.warning(f"Failed to update plan in database: {e}, using JSON fallback")
                logger.error(f"Database update error details: {type(e).__name__}: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
        
        # Only update JSON file if database update failed
        # CRITICAL: Don't use plans.json fallback - only use database
        # If database update failed, raise error instead of falling back to JSON
        if not database_update_success:
            logger.error(f"[update-plan] Database update failed for plan {plan_id}")
            raise HTTPException(status_code=500, detail=f"Failed to update plan '{plan_id}' in database. Please check database connection.")
        
        # All updates are done in database above - no need for JSON fallback
        logger.info(f"[update-plan] ✅ Plan {plan_id} updated successfully in database (no JSON fallback used)")
        
        return {"success": True, "plan_id": plan_id, "plan_data": updated_plan}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating plan: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/update-broker-membership")
async def update_broker_membership(request: Request, current_user: str = Depends(get_current_user)):
    """Update broker membership template permissions"""
    try:
        body = await request.json()
        membership_data = body.get('membership_data')
        
        if not membership_data:
            raise HTTPException(status_code=400, detail="membership_data is required")
        
        if not supabase:
            raise HTTPException(status_code=503, detail="Supabase not available")
        
        try:
            # Get template selection and limits
            allowed = membership_data.get('allowed_templates') or membership_data.get('can_download')
            template_limits = membership_data.get('template_limits', {})  # {template_id: max_downloads, ...}
            
            if not allowed:
                raise HTTPException(status_code=400, detail="Template selection (can_download) is required")
            
            # Get all active broker memberships - we'll update permissions for all of them
            # (since broker membership is a single entity in CMS)
            broker_memberships_res = supabase.table('broker_memberships').select('id').eq('payment_status', 'paid').eq('membership_status', 'active').execute()
            
            if not broker_memberships_res.data:
                logger.warning("No active broker memberships found")
                # Still create permissions structure for future memberships
                broker_membership_ids = []
            else:
                broker_membership_ids = [bm['id'] for bm in broker_memberships_res.data]
            
            # Get all templates
            templates_res = supabase.table('document_templates').select('id, file_name').eq('is_active', True).execute()
            
            if not templates_res.data:
                raise HTTPException(status_code=404, detail="No active templates found")
            
            # Delete existing broker permissions for all memberships
            if broker_membership_ids:
                for membership_id in broker_membership_ids:
                    supabase.table('broker_template_permissions').delete().eq('broker_membership_id', membership_id).execute()
            
            # Create new permissions
            inserted_count = 0
            
            if allowed == '*' or allowed == ['*'] or (isinstance(allowed, list) and '*' in allowed):
                # Allow all templates for all broker memberships
                for membership_id in broker_membership_ids:
                    for template in templates_res.data:
                        template_id = template['id']
                        max_downloads = template_limits.get(str(template_id)) if isinstance(template_limits, dict) else None
                        if max_downloads is not None:
                            try:
                                max_downloads = int(max_downloads) if max_downloads != '' else None
                            except (ValueError, TypeError):
                                max_downloads = None
                        
                        permission_data = {
                            'broker_membership_id': membership_id,
                            'template_id': template_id,
                            'can_download': True
                        }
                        if max_downloads is not None:
                            permission_data['max_downloads_per_template'] = max_downloads
                        
                        supabase.table('broker_template_permissions').insert(permission_data).execute()
                        inserted_count += 1
                
                logger.info(f"Set all templates permission for broker membership ({len(broker_membership_ids)} memberships)")
            elif isinstance(allowed, list):
                # Normalize template names
                template_names_normalized = set()
                for t in allowed:
                    if t != '*':
                        normalized = ensure_docx_filename(t)
                        template_names_normalized.add(normalise_template_key(normalized))
                        template_names_normalized.add(normalise_template_key(t.replace('.docx', '').replace('.DOCX', '')))
                
                # Match templates and create permissions
                for membership_id in broker_membership_ids:
                    for template in templates_res.data:
                        template_name = template.get('file_name', '').strip()
                        if not template_name:
                            continue
                        
                        normalized_template_name = normalise_template_key(ensure_docx_filename(template_name))
                        normalized_template_name_no_ext = normalise_template_key(template_name.replace('.docx', '').replace('.DOCX', ''))
                        
                        if normalized_template_name in template_names_normalized or normalized_template_name_no_ext in template_names_normalized:
                            try:
                                template_id = template['id']
                                max_downloads = None
                                if isinstance(template_limits, dict):
                                    max_downloads = template_limits.get(str(template_id)) or template_limits.get(template_id)
                                    if max_downloads is not None:
                                        try:
                                            max_downloads = int(max_downloads) if max_downloads != '' else None
                                        except (ValueError, TypeError):
                                            max_downloads = None
                                
                                permission_data = {
                                    'broker_membership_id': membership_id,
                                    'template_id': template_id,
                                    'can_download': True
                                }
                                if max_downloads is not None:
                                    permission_data['max_downloads_per_template'] = max_downloads
                                
                                supabase.table('broker_template_permissions').insert(permission_data).execute()
                                inserted_count += 1
                                logger.debug(f"Added permission for template {template_name} (ID: {template_id}) to broker membership with limit {max_downloads}")
                            except Exception as insert_exc:
                                logger.warning(f"Failed to insert permission for template {template_name}: {insert_exc}")
                
                logger.info(f"Set {inserted_count} template permissions for broker membership")
            
            # Get updated permissions for response
            template_limits_response = {}
            if broker_membership_ids:
                perms_res = supabase.table('broker_template_permissions').select('template_id, max_downloads_per_template').eq('broker_membership_id', broker_membership_ids[0]).execute()
                for perm in (perms_res.data or []):
                    template_id = perm['template_id']
                    max_downloads = perm.get('max_downloads_per_template')
                    if max_downloads is not None:
                        template_limits_response[str(template_id)] = max_downloads
            
            # Convert template IDs to file names for response
            all_templates = supabase.table('document_templates').select('id, file_name').eq('is_active', True).execute()
            template_id_to_name = {t['id']: t.get('file_name', '') for t in (all_templates.data or [])}
            
            if broker_membership_ids:
                perms_res = supabase.table('broker_template_permissions').select('template_id').eq('broker_membership_id', broker_membership_ids[0]).execute()
                template_ids = [p['template_id'] for p in (perms_res.data or [])]
                template_file_names = [ensure_docx_filename(template_id_to_name.get(tid, '')) for tid in template_ids if tid and template_id_to_name.get(tid)]
            else:
                template_file_names = []
            
            return {
                "success": True,
                "membership_data": {
                    "id": "broker-membership",
                    "name": "Broker Membership",
                    "plan_tier": "broker",
                    "can_download": template_file_names if template_file_names else ['*'],
                    "template_limits": template_limits_response if template_limits_response else None
                }
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error updating broker membership: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise HTTPException(status_code=500, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating broker membership: {e}")
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
        
        # Get all plans that can download this template
        permissions_res = supabase.table('plan_template_permissions').select(
            'plan_id, can_download'
        ).eq('template_id', template_id).eq('can_download', True).execute()
        
        plan_ids = [p['plan_id'] for p in (permissions_res.data or [])]
        
        # CRITICAL: If template has NO plan permissions, it's available to ALL plans
        if not plan_ids or len(plan_ids) == 0:
            # Template has no plan restrictions - available to all active plans
            logger.info(f"Template {template_id} has no plan permissions - available to all plans")
            all_plans_res = supabase.table('subscription_plans').select(
                'id, plan_name, plan_tier, name'
            ).eq('is_active', True).execute()
            
            plans = []
            if all_plans_res.data:
                for plan in all_plans_res.data:
                    plans.append({
                        "plan_id": str(plan['id']),
                        "plan_name": plan.get('plan_name') or plan.get('name') or plan.get('plan_tier'),
                        "plan_tier": plan.get('plan_tier')
                    })
            
            return {
                "success": True,
                "template_id": str(template_id),
                "template_name": template_record.get('file_name') if template_record else template_identifier,
                "plans": plans,
                "plan_name": "All Plans" if plans else None,
                "plan_tier": None,
                "source": "database",
                "available_to_all": True  # Flag to indicate template is available to all plans
            }
        
        # Template has specific plan permissions
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
            "source": "database",
            "available_to_all": False  # Template has specific plan restrictions
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
        
        # Get deleted templates list to filter them out
        deleted_templates = get_deleted_templates()
        if deleted_templates:
            logger.info(f"Filtering out {len(deleted_templates)} deleted templates: {list(deleted_templates)[:5]}")
        
        # Call database function
        try:
            templates_res = supabase.rpc('get_user_downloadable_templates', {
                'p_user_id': user_id
            }).execute()
            
            # Check for RPC errors
            if hasattr(templates_res, 'error') and templates_res.error:
                logger.error(f"RPC error: {templates_res.error}")
                raise Exception(f"Database function error: {templates_res.error}")
        except Exception as rpc_error:
            logger.error(f"Error calling get_user_downloadable_templates RPC: {rpc_error}")
            # Fallback: return empty list or try alternative query
            logger.warning("Falling back to direct template query")
            try:
                # Fallback: get all active templates and mark as downloadable
                templates_res_data = []
                fallback_templates = supabase.table('document_templates').select('id, title, description, file_name, placeholders').eq('is_active', True).execute()
                if fallback_templates.data:
                    # Get deleted templates for filtering
                    deleted_templates_fallback = get_deleted_templates()
                    normalized_deleted = {ensure_docx_filename(name) for name in deleted_templates_fallback} if deleted_templates_fallback else set()
                    
                    for t in fallback_templates.data:
                        file_name = t.get('file_name', '')
                        docx_file_name = ensure_docx_filename(file_name) if file_name else ''
                        
                        # Skip deleted templates
                        if normalized_deleted and docx_file_name:
                            if docx_file_name in normalized_deleted or docx_file_name.lower() in {name.lower() for name in normalized_deleted}:
                                logger.debug(f"Skipping deleted template in fallback: {docx_file_name}")
                                continue
                        
                        templates_res_data.append({
                            'template_id': t['id'],
                            'template_name': t.get('title') or t.get('file_name', ''),
                            'can_download': True,  # Default to true for fallback
                            'max_downloads': 10,
                            'current_downloads': 0,
                            'remaining_downloads': 10
                        })
                templates_res = type('obj', (object,), {'data': templates_res_data})()
            except Exception as fallback_error:
                logger.error(f"Fallback query also failed: {fallback_error}")
                return {
                    "success": True,
                    "templates": [],
                    "source": "error_fallback",
                    "error": str(fallback_error)
                }
        
        if templates_res.data:
            # Enhance with template details
            template_ids = [t['template_id'] for t in templates_res.data]
            details_res = supabase.table('document_templates').select('id, title, description, file_name, placeholders, font_family, font_size').in_('id', template_ids).execute()
            
            details_map = {d['id']: d for d in (details_res.data or [])}
            
            # Get user's plan info INCLUDING max_downloads_per_month
            user_plan_info = None
            user_max_downloads = None
            try:
                user_res = supabase.table('subscribers').select('subscription_plan, plan_tier').eq('user_id', user_id).limit(1).execute()
                if user_res.data and user_res.data[0]:
                    plan_tier = user_res.data[0].get('plan_tier') or user_res.data[0].get('subscription_plan')
                    if plan_tier:
                        plan_res = supabase.table('subscription_plans').select('id, plan_name, plan_tier, name, max_downloads_per_month').eq('plan_tier', plan_tier).limit(1).execute()
                        if plan_res.data:
                            plan_data = plan_res.data[0]
                            user_plan_info = {
                                "plan_name": plan_data.get('plan_name') or plan_data.get('name') or plan_tier,
                                "plan_tier": plan_tier
                            }
                            # Get max_downloads_per_month from user's plan
                            max_downloads_value = plan_data.get('max_downloads_per_month')
                            if max_downloads_value == -1:
                                user_max_downloads = -1  # -1 means unlimited
                            elif max_downloads_value is not None:
                                user_max_downloads = max_downloads_value
                            logger.info(f"User plan: {user_plan_info['plan_name']}, max_downloads: {user_max_downloads}")
            except Exception as e:
                logger.warning(f"Could not fetch user plan info: {e}")
            
            enhanced_templates = []
            for t in templates_res.data:
                template_id = t['template_id']
                details = details_map.get(template_id, {})
                
                # Get file_name and normalize for metadata lookup
                file_name = details.get('file_name', '')
                docx_file_name = ensure_docx_filename(file_name) if file_name else ''
                
                # CRITICAL: Skip deleted templates
                if deleted_templates and docx_file_name:
                    normalized_deleted = {ensure_docx_filename(name) for name in deleted_templates}
                    if docx_file_name in normalized_deleted or docx_file_name.lower() in {name.lower() for name in normalized_deleted}:
                        logger.debug(f"Skipping deleted template: {docx_file_name}")
                        continue
                
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
                
                # Check if template requires broker membership
                requires_broker = details.get('requires_broker_membership') or metadata_entry.get('requires_broker_membership', False)
                if requires_broker:
                    # Check if user has broker membership
                    try:
                        broker_check = supabase.rpc('check_broker_membership_status', {'user_id_param': user_id}).execute()
                        has_broker = broker_check.data if broker_check.data else False
                        if not has_broker:
                            logger.debug(f"Template {template_id} requires broker membership, but user {user_id} doesn't have it - skipping")
                            continue
                    except Exception as broker_exc:
                        logger.warning(f"Could not check broker membership for user {user_id}: {broker_exc}")
                        # If we can't check, skip templates that require broker membership for safety
                        if requires_broker:
                            continue
                
                # CRITICAL: Always use user's actual plan name and max_downloads
                # Don't show template's plan restrictions - show user's current plan
                plan_name = None
                plan_tier_val = None
                final_max_downloads = t.get('max_downloads', 10)  # Default from RPC function
                
                # Always use user's plan info if available
                if user_plan_info:
                    plan_name = user_plan_info['plan_name']
                    plan_tier_val = user_plan_info['plan_tier']
                    # Override max_downloads with user's plan max_downloads_per_month
                    if user_max_downloads is not None:
                        if user_max_downloads == -1:
                            final_max_downloads = -1  # Unlimited
                        else:
                            final_max_downloads = user_max_downloads
                        logger.info(f"Using user's plan max_downloads: {final_max_downloads} for template {template_id}")
                else:
                    # If no user plan info, check template permissions to show required plan
                    try:
                        perm_res = supabase.table('plan_template_permissions').select('plan_id').eq('template_id', template_id).limit(1).execute()
                        
                        if not perm_res.data or len(perm_res.data) == 0:
                            # Template has NO plan permissions - available to ALL plans
                            plan_name = "All Plans"
                            logger.info(f"Template {template_id} has no plan permissions - available to all plans")
                        elif not t['can_download']:
                            # User cannot download - get which plan allows this template
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
                        # Default: if can_download is true, assume available to all
                        if t['can_download']:
                            plan_name = "All Plans"
                
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
                    "max_downloads": final_max_downloads,  # Use user's plan max_downloads, not template's
                    "current_downloads": t['current_downloads'],
                    "remaining_downloads": t['remaining_downloads'],
                    "plan_name": plan_name if plan_name else (user_plan_info['plan_name'] if user_plan_info else None),  # Always show user's plan name
                    "plan_tier": plan_tier_val if plan_tier_val else (user_plan_info['plan_tier'] if user_plan_info else None),
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
async def get_csv_files(request: Request):
    """Get list of available CSV files"""
    # Allow unauthenticated access for CMS editor
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
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/csv-fields/{csv_id}")
async def get_csv_fields(csv_id: str, request: Request):
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

def get_data_from_table(table_name: str, lookup_field: str, lookup_value: str) -> Optional[Dict]:
    """
    Get data from any database table using a lookup field and value.
    
    Args:
        table_name: Name of the table (e.g., 'vessels', 'ports', 'refineries')
        lookup_field: Field name to search by (e.g., 'imo', 'id', 'name')
        lookup_value: Value to search for
    
    Returns:
        Dictionary with table data or None if not found
    """
    if not supabase:
        logger.warning(f"Supabase not available, cannot fetch data from {table_name}")
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
    
    source = setting.get('source', 'random')
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

def generate_ai_random_data(placeholder: str, vessel_imo: str = None, context: str = None) -> str:
    """Generate realistic random data using OpenAI AI"""
    if not OPENAI_ENABLED or not openai_client:
        logger.warning("OpenAI not available, falling back to standard random data")
        # Use 'auto' mode to prevent infinite recursion (don't call AI again)
        return generate_realistic_random_data(placeholder, vessel_imo, 'auto')
    
    try:
        # Build context for AI prompt
        prompt_context = f"Generate a realistic value for the placeholder '{placeholder}'"
        if vessel_imo:
            prompt_context += f" related to vessel IMO {vessel_imo}"
        if context:
            prompt_context += f". Context: {context}"
        prompt_context += ". Return ONLY the value, no explanation. Make it realistic and professional for oil trading/maritime industry documents."
        
        # Call OpenAI API
        response = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a data generator for oil trading and maritime industry documents. Generate realistic, professional values for placeholders."},
                {"role": "user", "content": prompt_context}
            ],
            max_tokens=100,
            temperature=0.7
        )
        
        ai_value = response.choices[0].message.content.strip()
        logger.info(f"🤖 AI generated value for '{placeholder}': {ai_value}")
        return ai_value
        
    except Exception as e:
        logger.error(f"Error generating AI data for '{placeholder}': {e}")
        logger.info("Falling back to standard random data generation")
        # Use 'auto' mode to prevent infinite recursion (don't call AI again)
        return generate_realistic_random_data(placeholder, vessel_imo, 'auto')

def generate_realistic_random_data(placeholder: str, vessel_imo: str = None, random_option: str = 'ai') -> str:
    """Generate realistic random data for placeholders
    
    Args:
        placeholder: The placeholder name
        vessel_imo: Optional vessel IMO for context
        random_option: 'ai' (default), 'auto', or 'fixed' - determines generation method
    """
    # If AI option is selected, use AI generation
    if random_option == 'ai':
        if OPENAI_ENABLED:
            logger.info(f"🤖 Attempting AI generation for placeholder: '{placeholder}'")
            return generate_ai_random_data(placeholder, vessel_imo)
        else:
            logger.warning(f"⚠️  AI requested for '{placeholder}' but OpenAI is not enabled. Check OPENAI_API_KEY environment variable.")
            logger.info(f"   Falling back to realistic random data generation")
            # Fall through to realistic random data generation below
    
    import random
    import hashlib
    
    # Create unique seed for consistent data (only if not 'fixed')
    if vessel_imo and random_option != 'fixed':
        seed_input = f"{vessel_imo}_{placeholder.lower()}"
        random.seed(int(hashlib.md5(seed_input.encode()).hexdigest()[:8], 16))
    
    placeholder_lower = placeholder.lower().replace('_', '').replace(' ', '').replace('-', '')
    
    # Handle specific common placeholder types first
    if placeholder_lower == 'via' or placeholder_lower.startswith('via'):
        companies = ['Maritime Solutions Ltd', 'Ocean Trading Co', 'Global Shipping Inc', 'Marine Services Group', 'International Vessel Corp']
        return random.choice(companies)
    elif 'position' in placeholder_lower or placeholder_lower == 'pos':
        positions = ['Director', 'Manager', 'Senior Manager', 'Vice President', 'President', 'CEO', 'CFO', 'COO', 'General Manager', 'Operations Manager']
        return random.choice(positions)
    elif placeholder_lower == 'bin' or placeholder_lower.startswith('bin'):
        # Business Identification Number (Kazakhstan format: 12 digits)
        return f"{random.randint(100000000000, 999999999999)}"
    elif placeholder_lower == 'okpo' or placeholder_lower.startswith('okpo'):
        # OKPO code (Russian business registration, 8-10 digits)
        return f"{random.randint(10000000, 9999999999)}"
    elif 'invoice' in placeholder_lower or 'inv' in placeholder_lower:
        prefixes = ['INV', 'CI', 'IN', 'DOC']
        return f"{random.choice(prefixes)}-{random.randint(100000, 999999)}"
    elif 'commercial' in placeholder_lower and 'invoice' in placeholder_lower:
        return f"INV-{random.randint(100000, 999999)}"
    
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
        elif 'company' in placeholder_lower or 'firm' in placeholder_lower or 'corporation' in placeholder_lower:
            companies = [
                'Maritime Solutions Ltd', 'Ocean Trading Co', 'Global Shipping Inc', 
                'Marine Services Group', 'International Vessel Corp', 'Petroleum Trading LLC',
                'Maritime Logistics Co', 'Shipping Partners Ltd', 'Ocean Freight Services',
                'Marine Transport Inc', 'International Shipping Group', 'Global Maritime Corp'
            ]
            return random.choice(companies)
        elif 'address' in placeholder_lower or 'location' in placeholder_lower:
            addresses = [
                '123 Maritime Street, London, UK', '456 Harbor Road, Singapore', 
                '789 Port Avenue, Dubai, UAE', '321 Dock Lane, Rotterdam, NL',
                '555 Shipping Boulevard, Houston, TX, USA', '888 Portside Drive, Shanghai, China',
                '777 Harbor View, Hamburg, Germany', '999 Maritime Plaza, Tokyo, Japan'
            ]
            return random.choice(addresses)
        elif 'person' in placeholder_lower or 'contact' in placeholder_lower or 'name' in placeholder_lower:
            names = [
                'John Smith', 'Maria Garcia', 'Ahmed Hassan', 'Li Wei', 
                'David Johnson', 'Sarah Brown', 'Michael Chen', 'Emma Wilson',
                'James Anderson', 'Sophie Martin', 'Robert Taylor', 'Anna Schmidt'
            ]
            return random.choice(names)
        elif 'email' in placeholder_lower or 'mail' in placeholder_lower:
            domains = ['example.com', 'maritime.com', 'shipping.com', 'trading.com', 'oil.com']
            name = random.choice(['john', 'maria', 'david', 'sarah', 'michael', 'emma', 'james', 'sophie'])
            return f"{name}{random.randint(1, 99)}@{random.choice(domains)}"
        elif 'phone' in placeholder_lower or 'tel' in placeholder_lower or 'mobile' in placeholder_lower:
            return f"+{random.randint(1, 99)} {random.randint(100, 999)} {random.randint(100000, 999999)}"
        elif 'ref' in placeholder_lower or 'reference' in placeholder_lower or 'number' in placeholder_lower or 'id' in placeholder_lower:
            prefixes = ['REF', 'PO', 'SO', 'INV', 'LC', 'BL', 'COA', 'SGS', 'DOC', 'ORD']
            return f"{random.choice(prefixes)}-{random.randint(100000, 999999)}"
        elif 'date' in placeholder_lower or 'time' in placeholder_lower:
            from datetime import timedelta
            return (datetime.now() - timedelta(days=random.randint(1, 30))).strftime('%Y-%m-%d')
        else:
            # Generate context-aware realistic data based on placeholder name
            # Try to infer what type of data is needed from the placeholder name
            if any(word in placeholder_lower for word in ['buyer', 'seller', 'client', 'customer']):
                companies = ['Maritime Solutions Ltd', 'Ocean Trading Co', 'Global Shipping Inc']
                return random.choice(companies)
            elif any(word in placeholder_lower for word in ['port', 'harbor', 'dock']):
                ports = ['Rotterdam', 'Singapore', 'Dubai', 'Houston', 'Shanghai', 'Hamburg', 'Tokyo']
                return random.choice(ports)
            elif any(word in placeholder_lower for word in ['vessel', 'ship', 'boat']):
                vessel_names = ['MV Atlantic Star', 'SS Ocean Breeze', 'MV Pacific Wave', 'SS Maritime Express']
                return random.choice(vessel_names)
            elif any(word in placeholder_lower for word in ['quantity', 'volume', 'capacity', 'tonnage', 'weight']):
                return f"{random.randint(1000, 50000):,} MT"
            elif any(word in placeholder_lower for word in ['price', 'cost', 'value', 'amount']):
                return f"${random.randint(10000, 5000000):,}"
            else:
                # Last resort: generate context-aware realistic data
                # Never use "Value-XXXX" format - always generate meaningful data
                placeholder_words = placeholder_lower.replace('_', ' ').replace('-', ' ').split()
                
                # Try to infer from placeholder name
                if len(placeholder_words) == 1:
                    # Single word placeholder - try common business fields
                    word = placeholder_words[0]
                    if len(word) <= 4:  # Short codes like BIN, OKPO, VIA
                        if word in ['via', 'bin', 'okpo', 'pos']:
                            # Already handled above, but fallback
                            if word == 'via':
                                return random.choice(['Maritime Solutions Ltd', 'Ocean Trading Co', 'Global Shipping Inc'])
                            elif word == 'bin':
                                return f"{random.randint(100000000000, 999999999999)}"
                            elif word == 'okpo':
                                return f"{random.randint(10000000, 9999999999)}"
                            elif word == 'pos':
                                return random.choice(['Director', 'Manager', 'Senior Manager'])
                    
                    # For other short codes, generate a number
                    return f"{random.randint(100000, 999999)}"
                else:
                    # Multi-word placeholder - use first meaningful word
                    first_word = next((w for w in placeholder_words if len(w) > 2), 'REF')
                    # Generate based on word type
                    if first_word in ['company', 'firm', 'corp', 'ltd']:
                        return random.choice(['Maritime Solutions Ltd', 'Ocean Trading Co', 'Global Shipping Inc'])
                    elif first_word in ['number', 'num', 'no', 'nr', 'ref', 'id', 'code']:
                        prefixes = ['REF', 'PO', 'SO', 'INV', 'LC', 'BL', 'COA', 'SGS']
                        return f"{random.choice(prefixes)}-{random.randint(100000, 999999)}"
                    elif first_word in ['name', 'person', 'contact']:
                        return random.choice(['John Smith', 'Maria Garcia', 'Ahmed Hassan', 'David Johnson'])
                    else:
                        # Generate a professional reference number
                        prefixes = ['REF', 'DOC', 'ORD', 'INV']
                        return f"{random.choice(prefixes)}-{random.randint(100000, 999999)}"

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
                    logger.warning(f"   No similar keys found. This placeholder will use random data.")
            else:
                matched_placeholders.append(placeholder)
                logger.debug(f"✅ Found CMS setting for '{placeholder}' (matched key: '{setting_key}')")

            if setting:
                # Validate setting structure
                is_valid, validation_errors = validate_placeholder_setting(setting)
                if not is_valid:
                    logger.warning(f"⚠️  Invalid placeholder setting for '{placeholder}': {', '.join(validation_errors)}")
                    logger.warning(f"   Will use random data as fallback")
                
                source = setting.get('source', 'random')
                logger.info(f"\n🔍 Processing placeholder: '{placeholder}' (CMS key: '{setting_key}', source: {source})")
                logger.info(f"📋 FULL CMS SETTING for '{placeholder}':")
                logger.info(f"   source: '{source}'")
                logger.info(f"   customValue: '{setting.get('customValue')}'")
                logger.info(f"   databaseTable: '{setting.get('databaseTable')}'")
                logger.info(f"   databaseField: '{setting.get('databaseField')}'")
                logger.info(f"   csvId: '{setting.get('csvId')}', csvField: '{setting.get('csvField')}', csvRow: {setting.get('csvRow')}")
                logger.info(f"   randomOption: '{setting.get('randomOption')}'")

                try:
                    # IMPORTANT: Respect the user's explicit CMS settings
                    # Only use intelligent matching if source is 'random' AND no databaseField is configured
                    if source == 'random':
                        database_field = (setting.get('databaseField') or '').strip()
                        database_table = (setting.get('databaseTable') or '').strip()
                        random_option = setting.get('randomOption', 'ai')
                        
                        # If user explicitly set databaseField or databaseTable, they want random data
                        # Don't override their choice with intelligent matching
                        if database_field or database_table:
                            logger.info(f"  🎲 Source is 'random' with explicit databaseField='{database_field}' or databaseTable='{database_table}'")
                            logger.info(f"  🎲 RESPECTING USER CHOICE: Will use random data (user explicitly configured this)")
                            # Generate random data immediately with the correct randomOption
                            seed_imo = None if random_option == 'fixed' else vessel_imo
                            data_mapping[placeholder] = generate_realistic_random_data(placeholder, seed_imo, random_option)
                            found = True
                            logger.info(f"  {placeholder} -> '{data_mapping[placeholder]}' (RANDOM data, mode: {random_option}, vessel IMO: {vessel_imo})")
                        elif not database_field:
                            # Only try intelligent matching if user didn't configure anything
                            logger.info(f"  🎲 Source is 'random' with NO databaseField configured, trying intelligent matching first...")
                            matched_field, matched_value = _intelligent_field_match(placeholder, vessel)
                            if matched_field and matched_value:
                                data_mapping[placeholder] = matched_value
                                found = True
                                logger.info(f"  ✅✅✅ AUTO-MATCHED (from random source): {placeholder} = '{matched_value}' (from vessel field '{matched_field}')")
                                logger.info(f"  💡 TIP: Change source to 'database' and set databaseField='{matched_field}' in CMS for explicit control")
                            else:
                                logger.info(f"  ⚠️  Intelligent matching failed, will use random data as configured (randomOption: {random_option})")
                                # Generate random data immediately with the correct randomOption
                                seed_imo = None if random_option == 'fixed' else vessel_imo
                                data_mapping[placeholder] = generate_realistic_random_data(placeholder, seed_imo, random_option)
                                found = True
                                logger.info(f"  {placeholder} -> '{data_mapping[placeholder]}' (RANDOM data, mode: {random_option}, vessel IMO: {vessel_imo})")
                    
                    elif source == 'custom':
                        custom_value = str(setting.get('customValue', '')).strip()
                        if custom_value:
                            data_mapping[placeholder] = custom_value
                            found = True
                            logger.info(f"✅ {placeholder} -> '{custom_value}' (CMS custom value)")
                        else:
                            logger.warning(f"⚠️  Placeholder '{placeholder}' has custom source but customValue is empty")

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

                        # If database_table is specified and it's not 'vessels', fetch data from that table
                        if database_table and database_table.lower() != 'vessels':
                            logger.info(f"  🔍 Fetching data from table '{database_table}'...")
                            
                            # Determine lookup field and value based on table
                            # For now, we'll try common lookup strategies
                            lookup_field = None
                            lookup_value = None
                            
                            if database_table.lower() == 'ports':
                                # Try to get port_id from vessel data
                                lookup_field = 'id'
                                if 'departure_port' in vessel and vessel.get('departure_port'):
                                    # If vessel has port name, we might need to look it up by name first
                                    # For now, assume we have port_id
                                    lookup_value = vessel.get('port_id') or vessel.get('departure_port_id')
                                elif 'currentport' in vessel:
                                    lookup_value = vessel.get('port_id')
                            elif database_table.lower() == 'refineries':
                                lookup_field = 'id'
                                lookup_value = vessel.get('refinery_id') or vessel.get('target_refinery_id')
                            elif database_table.lower() == 'companies':
                                lookup_field = 'id'
                                lookup_value = vessel.get('company_id') or vessel.get('owner_company_id')
                            elif database_table.lower() == 'brokers':
                                lookup_field = 'id'
                                lookup_value = vessel.get('broker_id')
                            else:
                                # Generic lookup - try 'id' field
                                lookup_field = 'id'
                                lookup_value = vessel.get(f'{database_table.lower()}_id')
                            
                            if lookup_field and lookup_value:
                                source_data = get_data_from_table(database_table, lookup_field, str(lookup_value))
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

                        if source_data:
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
                                data_mapping[placeholder] = matched_value
                                found = True
                                table_info = f" from {database_table}" if database_table and database_table.lower() != 'vessels' else ""
                                logger.info(f"  ✅✅✅ SUCCESS: {placeholder} = '{matched_value}' (from database field '{matched_field}'{table_info})")
                            else:
                                logger.error(f"  ❌❌❌ FAILED: Could not match '{placeholder}' to any field in {database_table or 'vessels'}!")
                                if database_field:
                                    logger.error(f"  ❌ Explicit field '{database_field}' not found in data")
                                logger.error(f"  ❌ Available fields: {list(source_data.keys())[:20]}...")  # Show first 20
                                logger.error(f"  ❌ This will use RANDOM data!")
                                logger.error(f"  💡 TIP: Check if databaseField in CMS matches field names exactly (case-insensitive)")
                        else:
                            logger.error(f"  ❌❌❌ FAILED: No data available from {database_table or 'vessels'} table!")
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

                except Exception as resolve_exc:
                    logger.error(f"  ❌❌❌ ERROR resolving data source for '{placeholder}': {resolve_exc}")
                    import traceback
                    logger.error(traceback.format_exc())
                    logger.warning(f"   Will use random data as fallback")

            if not found:
                # Try intelligent matching even if not configured in CMS
                # This helps match common vessel fields automatically
                logger.info(f"  🔍 {placeholder}: Not found in configured sources, trying intelligent database matching...")
                intelligent_field, intelligent_value = _intelligent_field_match(placeholder, vessel)
                
                if intelligent_field and intelligent_value:
                    data_mapping[placeholder] = intelligent_value
                    found = True
                    logger.info(f"  ✅✅✅ AUTO-MATCHED: {placeholder} = '{intelligent_value}' (from vessel field '{intelligent_field}')")
                    logger.info(f"  💡 TIP: Configure this in CMS for more control over data source")
                else:
                    # Fall back to random data
                    if setting:
                        random_option = setting.get('randomOption', 'ai')
                        source = setting.get('source', 'random')
                        logger.warning(f"  ⚠⚠⚠ {placeholder}: Using RANDOM data (source in CMS: '{source}', found: {found})")
                    else:
                        random_option = 'ai'
                        logger.warning(f"  ⚠⚠⚠ {placeholder}: Not configured in CMS and no intelligent match found, using random data")

                    seed_imo = None if random_option == 'fixed' else vessel_imo
                    data_mapping[placeholder] = generate_realistic_random_data(placeholder, seed_imo, random_option)
                    logger.info(f"  {placeholder} -> '{data_mapping[placeholder]}' (RANDOM data, mode: {random_option}, vessel IMO: {vessel_imo})")
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
        logger.info(f"⚠️  Unmatched (using random data): {len(unmatched_placeholders)} placeholders")
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
                    # Check per-template download limit before recording
                    try:
                        permission_result = supabase.rpc('can_user_download_template', {
                            'p_user_id': user_id,
                            'p_template_id': template_id
                        }).execute()
                        
                        if permission_result.data:
                            perm_data = permission_result.data
                            can_download = perm_data.get('can_download', False)
                            limit_reached = perm_data.get('limit_reached', False)
                            
                            if not can_download:
                                logger.warning(f"User {user_id} does not have permission to download template {template_id}")
                                # Don't block the download, but log it
                            elif limit_reached:
                                logger.warning(f"User {user_id} has reached per-template download limit for template {template_id}")
                                # Don't block the download, but log it
                            else:
                                # Record the download
                                download_record = {
                                    'user_id': user_id,
                                    'template_id': template_id,
                                    'vessel_imo': vessel_imo,
                                    'download_type': 'pdf' if pdf_path.endswith('.pdf') else 'docx',
                                    'file_size': len(file_content)
                                }
                                supabase.table('user_document_downloads').insert(download_record).execute()
                                logger.info(f"Recorded download for user {user_id}, template {template_id}")
                    except Exception as perm_check_error:
                        logger.warning(f"Could not check download permission, recording anyway: {perm_check_error}")
                        # Fallback: record download anyway if permission check fails
                        download_record = {
                            'user_id': user_id,
                            'template_id': template_id,
                            'vessel_imo': vessel_imo,
                            'download_type': 'pdf' if pdf_path.endswith('.pdf') else 'docx',
                            'file_size': len(file_content)
                        }
                        supabase.table('user_document_downloads').insert(download_record).execute()
                        logger.info(f"Recorded download for user {user_id}, template {template_id} (permission check failed)")
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

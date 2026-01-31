"""
PetroDealHub Document Processing API
Handles Word document processing with payload-driven data fetching from Supabase.
Implements strict prefix-based placeholder mapping for 500+ placeholders.
"""

import os
import uuid
import shutil
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Union
from fastapi import FastAPI, HTTPException, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
from supabase import create_client, Client
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
import re

# Initialize FastAPI app
app = FastAPI(title="PetroDealHub Document Processor API", version="2.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Supabase client
SUPABASE_URL = "https://ozjhdxvwqbzcvcywhwjg.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im96amhkeHZ3cWJ6Y3ZjeXdod2pnIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTU5MDAyNzUsImV4cCI6MjA3MTQ3NjI3NX0.KLAo1KIRR9ofapXPHenoi-ega0PJtkNhGnDHGtniA-Q"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Directories
TEMPLATES_DIR = "./templates"
TEMP_DIR = "./temp"
os.makedirs(TEMPLATES_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

# =============================================================================
# PREFIX-TO-TABLE MAPPING (CRITICAL FOR PLACEHOLDER REPLACEMENT)
# =============================================================================
# Supports 10 core tables with 455+ official placeholders
PREFIX_TABLE_MAPPING = {
    "vessel_": {"table": "vessels", "id_type": "integer"},
    "port_": {"table": "ports", "id_type": "integer"},
    "departure_port_": {"table": "ports", "id_type": "integer"},
    "destination_port_": {"table": "ports", "id_type": "integer"},
    "company_": {"table": "companies", "id_type": "integer"},
    "buyer_": {"table": "buyer_companies", "id_type": "uuid"},
    "seller_": {"table": "seller_companies", "id_type": "uuid"},
    "refinery_": {"table": "refineries", "id_type": "uuid"},
    "product_": {"table": "oil_products", "id_type": "uuid"},
    "broker_": {"table": "broker_profiles", "id_type": "uuid"},
    "deal_": {"table": "broker_deals", "id_type": "uuid"},
    "buyer_bank_": {"table": "buyer_company_bank_accounts", "id_type": "uuid"},
    "seller_bank_": {"table": "seller_company_bank_accounts", "id_type": "uuid"},
    "company_bank_": {"table": "company_bank_accounts", "id_type": "uuid"},
}

# =============================================================================
# FIELD ALIASES - Maps placeholder field names to actual DB column names
# Only needed when placeholder field name differs from database column name
# Format: normalized_field_name -> actual_db_column_name
# =============================================================================
FIELD_ALIASES = {
    "swift": "swift_code",
    "accountname": "account_name",
    "accountnumber": "account_number",
    "bankname": "bank_name",
    "bankaddress": "bank_address",
    "beneficiaryaddress": "beneficiary_address",
    "companyname": "name",
    "fullname": "full_name",
    "tradename": "trade_name",
}

# =============================================================================
# PYDANTIC MODELS FOR REQUEST VALIDATION
# =============================================================================
class DocumentProcessRequest(BaseModel):
    template_name: str
    vessel_id: Optional[int] = None
    departure_port_id: Optional[int] = None
    destination_port_id: Optional[int] = None
    company_id: Optional[int] = None
    buyer_id: Optional[str] = None
    seller_id: Optional[str] = None
    product_id: Optional[str] = None
    refinery_id: Optional[str] = None
    broker_id: Optional[str] = None
    deal_id: Optional[str] = None
    buyer_bank_id: Optional[str] = None
    seller_bank_id: Optional[str] = None
    company_bank_id: Optional[str] = None
    output_format: Optional[str] = "pdf"

# =============================================================================
# MODULAR FETCH FUNCTIONS (Task 1)
# =============================================================================

def fetch_vessel(vessel_id: int) -> Optional[Dict]:
    """Fetch vessel by ID from vessels table"""
    try:
        response = supabase.table("vessels").select("*").eq("id", vessel_id).single().execute()
        return response.data
    except Exception as e:
        print(f"Error fetching vessel {vessel_id}: {e}")
        return None

def fetch_port(port_id: int) -> Optional[Dict]:
    """Fetch port by ID from ports table"""
    try:
        response = supabase.table("ports").select("*").eq("id", port_id).single().execute()
        return response.data
    except Exception as e:
        print(f"Error fetching port {port_id}: {e}")
        return None

def fetch_company(company_id: int) -> Optional[Dict]:
    """Fetch company by ID from companies table (real companies)"""
    try:
        response = supabase.table("companies").select("*").eq("id", company_id).single().execute()
        return response.data
    except Exception as e:
        print(f"Error fetching company {company_id}: {e}")
        return None

def fetch_buyer(buyer_id: str) -> Optional[Dict]:
    """Fetch buyer company by UUID from buyer_companies table"""
    try:
        response = supabase.table("buyer_companies").select("*").eq("id", buyer_id).single().execute()
        return response.data
    except Exception as e:
        print(f"Error fetching buyer {buyer_id}: {e}")
        return None

def fetch_seller(seller_id: str) -> Optional[Dict]:
    """Fetch seller company by UUID from seller_companies table"""
    try:
        response = supabase.table("seller_companies").select("*").eq("id", seller_id).single().execute()
        return response.data
    except Exception as e:
        print(f"Error fetching seller {seller_id}: {e}")
        return None

def fetch_refinery(refinery_id: str) -> Optional[Dict]:
    """Fetch refinery by UUID from refineries table"""
    try:
        response = supabase.table("refineries").select("*").eq("id", refinery_id).single().execute()
        return response.data
    except Exception as e:
        print(f"Error fetching refinery {refinery_id}: {e}")
        return None

def fetch_product(product_id: str) -> Optional[Dict]:
    """Fetch oil product by UUID from oil_products table"""
    try:
        response = supabase.table("oil_products").select("*").eq("id", product_id).single().execute()
        return response.data
    except Exception as e:
        print(f"Error fetching product {product_id}: {e}")
        return None

def fetch_broker(broker_id: str) -> Optional[Dict]:
    """Fetch broker profile by UUID from broker_profiles table"""
    try:
        response = supabase.table("broker_profiles").select("*").eq("id", broker_id).single().execute()
        return response.data
    except Exception as e:
        print(f"Error fetching broker {broker_id}: {e}")
        return None

def fetch_deal(deal_id: str) -> Optional[Dict]:
    """Fetch deal by UUID from broker_deals table"""
    try:
        response = supabase.table("broker_deals").select("*").eq("id", deal_id).single().execute()
        return response.data
    except Exception as e:
        print(f"Error fetching deal {deal_id}: {e}")
        return None

def fetch_buyer_bank(buyer_bank_id: Optional[str] = None, buyer_id: Optional[str] = None) -> Optional[Dict]:
    """
    Fetch buyer bank account.
    If buyer_bank_id provided: fetch exact record.
    Otherwise: fetch primary bank account for buyer_id.
    """
    try:
        if buyer_bank_id:
            response = supabase.table("buyer_company_bank_accounts").select("*").eq("id", buyer_bank_id).single().execute()
            return response.data
        elif buyer_id:
            response = supabase.table("buyer_company_bank_accounts").select("*").eq("company_id", buyer_id).eq("is_primary", True).limit(1).execute()
            if response.data:
                return response.data[0]
            response = supabase.table("buyer_company_bank_accounts").select("*").eq("company_id", buyer_id).limit(1).execute()
            return response.data[0] if response.data else None
        return None
    except Exception as e:
        print(f"Error fetching buyer bank: {e}")
        return None

def fetch_seller_bank(seller_bank_id: Optional[str] = None, seller_id: Optional[str] = None) -> Optional[Dict]:
    """
    Fetch seller bank account.
    If seller_bank_id provided: fetch exact record.
    Otherwise: fetch primary bank account for seller_id.
    """
    try:
        if seller_bank_id:
            response = supabase.table("seller_company_bank_accounts").select("*").eq("id", seller_bank_id).single().execute()
            return response.data
        elif seller_id:
            response = supabase.table("seller_company_bank_accounts").select("*").eq("company_id", seller_id).eq("is_primary", True).limit(1).execute()
            if response.data:
                return response.data[0]
            response = supabase.table("seller_company_bank_accounts").select("*").eq("company_id", seller_id).limit(1).execute()
            return response.data[0] if response.data else None
        return None
    except Exception as e:
        print(f"Error fetching seller bank: {e}")
        return None

def fetch_company_bank(company_bank_id: Optional[str] = None, company_id: Optional[int] = None) -> Optional[Dict]:
    """
    Fetch company bank account (for real companies).
    If company_bank_id provided: fetch exact record.
    Otherwise: fetch primary bank account for company_id.
    """
    try:
        if company_bank_id:
            response = supabase.table("company_bank_accounts").select("*").eq("id", company_bank_id).single().execute()
            return response.data
        elif company_id:
            response = supabase.table("company_bank_accounts").select("*").eq("company_id", company_id).eq("is_primary", True).limit(1).execute()
            if response.data:
                return response.data[0]
            response = supabase.table("company_bank_accounts").select("*").eq("company_id", company_id).limit(1).execute()
            return response.data[0] if response.data else None
        return None
    except Exception as e:
        print(f"Error fetching company bank: {e}")
        return None

# =============================================================================
# MAIN FETCH FUNCTION - ORCHESTRATES ALL DATA FETCHING (Task 2)
# =============================================================================

def fetch_document_data(payload: DocumentProcessRequest) -> Dict[str, Optional[Dict]]:
    """
    Fetch all document data based on payload IDs.
    Only fetches data for tables where IDs are explicitly provided.
    Returns a structured dictionary with prefixed keys.
    """
    data = {}
    
    if payload.vessel_id:
        data["vessel"] = fetch_vessel(payload.vessel_id)
        print(f"Fetched vessel: {payload.vessel_id}")
    
    if payload.departure_port_id:
        data["departure_port"] = fetch_port(payload.departure_port_id)
        print(f"Fetched departure_port: {payload.departure_port_id}")
    
    if payload.destination_port_id:
        data["destination_port"] = fetch_port(payload.destination_port_id)
        print(f"Fetched destination_port: {payload.destination_port_id}")
    
    if payload.company_id:
        data["company"] = fetch_company(payload.company_id)
        print(f"Fetched company: {payload.company_id}")
    
    if payload.buyer_id:
        data["buyer"] = fetch_buyer(payload.buyer_id)
        print(f"Fetched buyer: {payload.buyer_id}")
    
    if payload.seller_id:
        data["seller"] = fetch_seller(payload.seller_id)
        print(f"Fetched seller: {payload.seller_id}")
    
    if payload.product_id:
        data["product"] = fetch_product(payload.product_id)
        print(f"Fetched product: {payload.product_id}")
    
    if payload.refinery_id:
        data["refinery"] = fetch_refinery(payload.refinery_id)
        print(f"Fetched refinery: {payload.refinery_id}")
    
    if payload.broker_id:
        data["broker"] = fetch_broker(payload.broker_id)
        print(f"Fetched broker: {payload.broker_id}")
    
    if payload.deal_id:
        data["deal"] = fetch_deal(payload.deal_id)
        print(f"Fetched deal: {payload.deal_id}")
    
    # Bank accounts with is_primary fallback (Task 3)
    data["buyer_bank"] = fetch_buyer_bank(payload.buyer_bank_id, payload.buyer_id)
    if data["buyer_bank"]:
        print(f"Fetched buyer_bank")
    
    data["seller_bank"] = fetch_seller_bank(payload.seller_bank_id, payload.seller_id)
    if data["seller_bank"]:
        print(f"Fetched seller_bank")
    
    data["company_bank"] = fetch_company_bank(payload.company_bank_id, payload.company_id)
    if data["company_bank"]:
        print(f"Fetched company_bank")
    
    return data

# =============================================================================
# PLACEHOLDER DETECTION AND NORMALIZATION (Task 4 & 5)
# =============================================================================

def normalize_placeholder(placeholder: str) -> str:
    """
    Normalize a placeholder for consistent matching.
    Converts to lowercase and removes spaces, dashes, underscores.
    Example: 'Buyer Bank Swift' -> 'buyerbankswift'
    """
    return placeholder.lower().replace(' ', '').replace('-', '').replace('_', '')

def find_placeholders(text: str) -> List[str]:
    """Find placeholders in text using various patterns"""
    patterns = [
        r'\{\{([^}]+)\}\}',    # {{placeholder}}
        r'\{([^}]+)\}',        # {placeholder}
        r'\[\[([^\]]+)\]\]',   # [[placeholder]]
        r'%([^%]+)%',          # %placeholder%
        r'<([^>]+)>',          # <placeholder>
    ]
    
    placeholders = []
    for pattern in patterns:
        matches = re.findall(pattern, text)
        placeholders.extend(matches)
    
    cleaned = []
    for placeholder in placeholders:
        p = placeholder.strip()
        if (p and 
            len(p) < 200 and 
            not p.startswith('{') and 
            not p.endswith('}') and
            p not in cleaned):
            cleaned.append(p)
    
    return cleaned

def identify_prefix(placeholder: str) -> Optional[str]:
    """
    Identify which prefix a placeholder belongs to.
    Returns the matching prefix or None.
    """
    normalized = placeholder.lower().replace(' ', '_')
    
    # Check prefixes in order of specificity (longer prefixes first)
    prefixes_ordered = sorted(PREFIX_TABLE_MAPPING.keys(), key=len, reverse=True)
    
    for prefix in prefixes_ordered:
        if normalized.startswith(prefix):
            return prefix
    
    return None

def extract_field_from_placeholder(placeholder: str, prefix: str) -> str:
    """
    Extract the field name from a placeholder after removing the prefix.
    Example: 'buyer_bank_swift' with prefix 'buyer_bank_' -> 'swift'
    """
    normalized = placeholder.lower().replace(' ', '_')
    if normalized.startswith(prefix):
        field = normalized[len(prefix):]
        return field
    return normalized

# =============================================================================
# VALUE FORMATTING (Task 8)
# =============================================================================

def format_value(value: Any) -> str:
    """
    Format a value for document replacement.
    - NULL -> empty string
    - Arrays -> comma-joined string
    - Others -> string representation
    """
    if value is None:
        return ""
    
    if isinstance(value, list):
        return ", ".join(str(v) for v in value if v is not None)
    
    if isinstance(value, bool):
        return "Yes" if value else "No"
    
    if isinstance(value, (int, float)):
        return str(value)
    
    return str(value)

# =============================================================================
# PREFIX-BASED PLACEHOLDER REPLACEMENT (Task 6)
# =============================================================================

_LEGACY_PLACEHOLDER_MAPPING_RAW = {
    "imo_number": ("vessel", "imo"),
    "flag_state": ("vessel", "flag"),
    "vessel_type": ("vessel", "vessel_type"),
    "call_sign": ("vessel", "callsign"),
    "callsign": ("vessel", "callsign"),
    "year_built": ("vessel", "built"),
    "built": ("vessel", "built"),
    "vessel_owner": ("vessel", "owner_name"),
    "owner": ("vessel", "owner_name"),
    "owner_name": ("vessel", "owner_name"),
    "length_overall": ("vessel", "length"),
    "length": ("vessel", "length"),
    "vessel_operator": ("vessel", "operator_name"),
    "operator": ("vessel", "operator_name"),
    "operator_name": ("vessel", "operator_name"),
    "beam": ("vessel", "beam"),
    "width": ("vessel", "width"),
    "draft": ("vessel", "draft"),
    "draught": ("vessel", "draught"),
    "gross_tonnage": ("vessel", "gross_tonnage"),
    "deadweight": ("vessel", "deadweight"),
    "cargo_capacity": ("vessel", "cargo_capacity"),
    "cargo_capacity_bbl": ("vessel", "cargo_capacity_bbl"),
    "cargo_type": ("vessel", "cargo_type"),
    "engine_power": ("vessel", "engine_power"),
    "fuel_consumption": ("vessel", "fuel_consumption"),
    "speed": ("vessel", "speed"),
    "service_speed": ("vessel", "service_speed"),
    "mmsi": ("vessel", "mmsi"),
    "crew_size": ("vessel", "crew_size"),
    "nav_status": ("vessel", "nav_status"),
    "course": ("vessel", "course"),
    "current_region": ("vessel", "current_region"),
    "company_name": ("company", "name"),
    "refinery_name": ("refinery", "name"),
    "principal_buyer_name": ("buyer", "representative_name"),
    "principal_buyer_designation": ("buyer", "representative_title"),
    "principal_buyer_company": ("buyer", "name"),
    "buyer_company_name": ("buyer", "name"),
    "buyer_company_name2": ("buyer", "name"),
    "buyer_attention": ("buyer", "representative_name"),
    "buyer_attention2": ("buyer", "representative_name"),
    "buyer_designations2": ("buyer", "representative_title"),
    "buyer_telfax": ("buyer", "phone"),
    "buyer_email": ("buyer", "email"),
    "buyer_passport_no": ("buyer", "passport_number"),
    "buyer_bin": ("buyer", "registration_number"),
    "seller_name": ("seller", "representative_name"),
    "seller_designation": ("seller", "representative_title"),
    "seller_company": ("seller", "name"),
    "seller_address": ("seller", "address"),
    "seller_address2": ("seller", "legal_address"),
    "seller_refinery": ("seller", "refinery_name"),
    "seller_company_reg": ("seller", "registration_number"),
    "seller_representative": ("seller", "representative_name"),
    "seller_passport_no": ("seller", "passport_number"),
    "seller_company_no": ("seller", "registration_number"),
    "seller_emails": ("seller", "email"),
    "product_description": ("product", "commodity_name"),
    "country_of_origin": ("product", "origin_country"),
    "quantity": ("deal", "quantity"),
    "price": ("deal", "price_per_unit"),
    "total_product_value": ("deal", "total_value"),
    "delivery_port": ("destination_port", "name"),
    "address": ("company", "address"),
    "bin": ("company", "bin"),
    "okpo": ("company", "okpo"),
    "tel": ("company", "phone"),
    "email": ("company", "email"),
    "to": ("buyer", "name"),
    "designations": ("buyer", "representative_title"),
    "via": ("broker", "full_name"),
    "broker_name": ("broker", "full_name"),
    "broker_company": ("broker", "company_name"),
    "broker_email": ("broker", "email"),
    "broker_phone": ("broker", "phone"),
    "position": ("deal", "deal_type"),
    "deal_type": ("deal", "deal_type"),
    "deal_status": ("deal", "status"),
    "deal_date": ("deal", "deal_date"),
    "deal_value": ("deal", "total_value"),
    "commission": ("deal", "commission_amount"),
    "commercial_invoice_no": ("deal", "id"),
    "issued_date": ("deal", "deal_date"),
    "validity": ("deal", "deal_validity"),
    "laycan_start": ("deal", "laycan_start"),
    "laycan_end": ("deal", "laycan_end"),
    "density": ("product", "density_kg_m3"),
    "viscosity": ("product", "viscosity_cst"),
    "sulfur": ("product", "sulphur_content_ppm"),
    "sulphur": ("product", "sulphur_content_ppm"),
    "cetane": ("product", "cetane_number_min"),
    "color": ("product", "color_max"),
    "ash": ("product", "ash_content_max"),
    "oxidation": ("product", "oxidation_stability"),
    "lubricity": ("product", "lubricity_um"),
    "distillation": ("product", "distillation_range"),
    "flash_point": ("product", "flash_point_min_c"),
    "pour_point": ("product", "pour_point_c"),
    "cloud_point": ("product", "cloud_point_c"),
    "grade": ("product", "grade"),
    "origin": ("product", "origin"),
    "commodity_name": ("product", "commodity_name"),
    "commodity_type": ("product", "commodity_type"),
}

# Create normalized lookup for legacy mappings (removes underscores, dashes, lowercase)
LEGACY_PLACEHOLDER_MAPPING = {
    normalize_placeholder(k): v for k, v in _LEGACY_PLACEHOLDER_MAPPING_RAW.items()
}

def build_replacement_mapping(data: Dict[str, Optional[Dict]], placeholders: List[str]) -> Dict[str, str]:
    """
    Build a mapping from placeholders to their replacement values.
    Uses strict prefix-based matching to prevent cross-entity contamination.
    Also supports legacy placeholder names for backward compatibility.
    """
    mapping = {}
    
    # Map data keys to their prefixes
    data_key_to_prefix = {
        "vessel": "vessel_",
        "departure_port": "departure_port_",
        "destination_port": "destination_port_",
        "port": "port_",
        "company": "company_",
        "buyer": "buyer_",
        "seller": "seller_",
        "refinery": "refinery_",
        "product": "product_",
        "broker": "broker_",
        "deal": "deal_",
        "buyer_bank": "buyer_bank_",
        "seller_bank": "seller_bank_",
        "company_bank": "company_bank_",
    }
    
    for placeholder in placeholders:
        normalized_placeholder = normalize_placeholder(placeholder)
        
        # FIRST: Check legacy mapping for backward compatibility
        if normalized_placeholder in LEGACY_PLACEHOLDER_MAPPING:
            data_key, field_name = LEGACY_PLACEHOLDER_MAPPING[normalized_placeholder]
            entity_data = data.get(data_key)
            if entity_data is not None:
                if field_name in entity_data:
                    mapping[placeholder] = format_value(entity_data[field_name])
                    print(f"Mapped (legacy): {placeholder} -> {mapping[placeholder][:50] if len(mapping[placeholder]) > 50 else mapping[placeholder]}...")
                    continue
                else:
                    for key, value in entity_data.items():
                        if normalize_placeholder(key) == normalize_placeholder(field_name):
                            mapping[placeholder] = format_value(value)
                            print(f"Mapped (legacy normalized): {placeholder} -> {mapping[placeholder][:50] if len(mapping[placeholder]) > 50 else mapping[placeholder]}...")
                            break
                    else:
                        print(f"Warning: Legacy field '{field_name}' not found in {data_key}")
                    continue
            else:
                print(f"Warning: No data for legacy placeholder '{placeholder}' (entity: {data_key})")
                continue
        
        # SECOND: Try prefix-based matching
        prefix = identify_prefix(placeholder)
        
        if not prefix:
            print(f"Warning: No prefix match for placeholder '{placeholder}'")
            continue
        
        # Find which data key this prefix corresponds to
        data_key = None
        for key, p in data_key_to_prefix.items():
            if p == prefix:
                data_key = key
                break
        
        if not data_key or data_key not in data or data[data_key] is None:
            print(f"Warning: No data available for placeholder '{placeholder}' (prefix: {prefix})")
            continue
        
        # Extract field name and look up value
        field = extract_field_from_placeholder(placeholder, prefix)
        entity_data = data.get(data_key)
        
        if entity_data is None:
            continue
        
        # Try exact field match first
        if field in entity_data:
            mapping[placeholder] = format_value(entity_data[field])
            print(f"Mapped: {placeholder} -> {mapping[placeholder][:50]}...")
        else:
            # Try with entity prefix prepended (e.g., "type" -> "vessel_type" for vessel entity)
            prefixed_field = f"{data_key}_{field}" if not field.startswith(data_key) else field
            if prefixed_field in entity_data:
                mapping[placeholder] = format_value(entity_data[prefixed_field])
                print(f"Mapped (prefixed): {placeholder} -> {mapping[placeholder][:50]}...")
            else:
                # Try normalized field matching
                normalized_field = normalize_placeholder(field)
                found = False
                for key, value in entity_data.items():
                    if normalize_placeholder(key) == normalized_field:
                        mapping[placeholder] = format_value(value)
                        print(f"Mapped (normalized): {placeholder} -> {mapping[placeholder][:50]}...")
                        found = True
                        break
                
                if not found:
                    if normalized_field in FIELD_ALIASES:
                        alias = FIELD_ALIASES[normalized_field]
                        if alias in entity_data:
                            mapping[placeholder] = format_value(entity_data[alias])
                            print(f"Mapped (alias): {placeholder} -> {mapping[placeholder][:50]}...")
                        else:
                            print(f"Warning: Field '{field}' not found in {data_key}")
                    else:
                        print(f"Warning: Field '{field}' not found in {data_key}")
    
    return mapping

# =============================================================================
# DOCUMENT REPLACEMENT FUNCTIONS
# =============================================================================

def replace_in_paragraph(paragraph, mapping: Dict[str, str]) -> int:
    """Replace placeholders in a paragraph, returns count of replacements"""
    replacements = 0
    
    for placeholder, value in mapping.items():
        formats = [
            f"{{{{{placeholder}}}}}",    # {{placeholder}}
            f"{{{placeholder}}}",        # {placeholder}
            f"[[{placeholder}]]",        # [[placeholder]]
            f"%{placeholder}%",          # %placeholder%
            f"<{placeholder}>",          # <placeholder>
        ]
        
        for fmt in formats:
            if fmt in paragraph.text:
                paragraph.text = paragraph.text.replace(fmt, value)
                replacements += 1
    
    return replacements

def replace_placeholders_in_docx(docx_path: str, mapping: Dict[str, str]) -> str:
    """Replace placeholders in a Word document and return output path"""
    try:
        doc = Document(docx_path)
        total_replacements = 0
        
        # Replace in paragraphs
        for paragraph in doc.paragraphs:
            total_replacements += replace_in_paragraph(paragraph, mapping)
        
        # Replace in tables
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        total_replacements += replace_in_paragraph(paragraph, mapping)
        
        # Replace in headers and footers
        for section in doc.sections:
            for header in [section.header, section.first_page_header, section.even_page_header]:
                if header:
                    for paragraph in header.paragraphs:
                        total_replacements += replace_in_paragraph(paragraph, mapping)
            for footer in [section.footer, section.first_page_footer, section.even_page_footer]:
                if footer:
                    for paragraph in footer.paragraphs:
                        total_replacements += replace_in_paragraph(paragraph, mapping)
        
        print(f"Total replacements made: {total_replacements}")
        
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
        
        libreoffice_paths = [
            '/usr/bin/libreoffice',
            '/usr/local/bin/libreoffice',
            '/opt/libreoffice/program/soffice',
            'libreoffice'
        ]
        
        libreoffice_found = None
        for path in libreoffice_paths:
            try:
                result = subprocess.run([path, '--version'], 
                                      capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    libreoffice_found = path
                    break
            except:
                continue
        
        if not libreoffice_found:
            print("LibreOffice not found, returning DOCX")
            return docx_path
        
        cmd = [
            libreoffice_found,
            '--headless',
            '--convert-to', 'pdf',
            '--outdir', os.path.dirname(pdf_path),
            docx_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        if result.returncode == 0:
            expected_pdf = os.path.join(os.path.dirname(pdf_path), 
                                      os.path.splitext(os.path.basename(docx_path))[0] + '.pdf')
            if os.path.exists(expected_pdf):
                os.rename(expected_pdf, pdf_path)
            return pdf_path
        else:
            return docx_path
            
    except Exception as e:
        print(f"PDF conversion failed: {e}")
        return docx_path

# =============================================================================
# API ENDPOINTS
# =============================================================================

@app.get("/")
async def root():
    return {"message": "PetroDealHub Document Processor API v2.0 is running!"}

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "version": "2.0.0",
        "templates_count": len([f for f in os.listdir(TEMPLATES_DIR) if f.endswith('.docx')]),
        "timestamp": datetime.now().isoformat()
    }

@app.get("/templates")
async def get_templates():
    """Get list of available templates with placeholder analysis"""
    try:
        templates = []
        for filename in os.listdir(TEMPLATES_DIR):
            if filename.lower().endswith('.docx'):
                file_path = os.path.join(TEMPLATES_DIR, filename)
                file_size = os.path.getsize(file_path)
                
                doc = Document(file_path)
                full_text = ""
                for paragraph in doc.paragraphs:
                    full_text += paragraph.text + "\n"
                for table in doc.tables:
                    for row in table.rows:
                        for cell in row.cells:
                            full_text += cell.text + "\n"
                
                placeholders = find_placeholders(full_text)
                
                # Analyze placeholders by prefix
                prefix_counts = {}
                for p in placeholders:
                    prefix = identify_prefix(p)
                    if prefix:
                        prefix_counts[prefix] = prefix_counts.get(prefix, 0) + 1
                    else:
                        prefix_counts["unknown"] = prefix_counts.get("unknown", 0) + 1
                
                templates.append({
                    "id": str(uuid.uuid4()),
                    "name": filename.replace('.docx', ''),
                    "file_name": filename,
                    "file_size": file_size,
                    "placeholder_count": len(placeholders),
                    "placeholders": placeholders,
                    "prefix_analysis": prefix_counts,
                    "is_active": True
                })
        
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

@app.get("/buyers")
async def get_buyers():
    """Get list of buyer companies"""
    try:
        response = supabase.table('buyer_companies').select('id, name, country, city').limit(50).execute()
        return {"success": True, "buyers": response.data, "count": len(response.data)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch buyers: {str(e)}")

@app.get("/sellers")
async def get_sellers():
    """Get list of seller companies"""
    try:
        response = supabase.table('seller_companies').select('id, name, country, city').limit(50).execute()
        return {"success": True, "sellers": response.data, "count": len(response.data)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch sellers: {str(e)}")

@app.get("/products")
async def get_products():
    """Get list of oil products"""
    try:
        response = supabase.table('oil_products').select('id, commodity_name, commodity_type, grade').limit(50).execute()
        return {"success": True, "products": response.data, "count": len(response.data)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch products: {str(e)}")

@app.get("/refineries")
async def get_refineries():
    """Get list of refineries"""
    try:
        response = supabase.table('refineries').select('id, name, country, capacity').limit(50).execute()
        return {"success": True, "refineries": response.data, "count": len(response.data)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch refineries: {str(e)}")

@app.get("/ports")
async def get_ports():
    """Get list of ports"""
    try:
        response = supabase.table('ports').select('id, name, country, port_type').limit(50).execute()
        return {"success": True, "ports": response.data, "count": len(response.data)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch ports: {str(e)}")

@app.get("/brokers")
async def get_brokers():
    """Get list of broker profiles"""
    try:
        response = supabase.table('broker_profiles').select('id, full_name, company_name, country').limit(50).execute()
        return {"success": True, "brokers": response.data, "count": len(response.data)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch brokers: {str(e)}")

@app.get("/placeholder-schema")
async def get_placeholder_schema():
    """
    Get the official placeholder schema showing all available placeholders by entity.
    Returns prefix → table mapping and sample column names for each table.
    Generates correct placeholder names based on official format: {{prefix_fieldname}}
    """
    try:
        schema = {
            "total_entities": len(PREFIX_TABLE_MAPPING),
            "entities": {}
        }
        
        for prefix, config in PREFIX_TABLE_MAPPING.items():
            table_name = config["table"]
            id_type = config["id_type"]
            entity_name = prefix.rstrip('_')
            
            try:
                response = supabase.table(table_name).select('*').limit(1).execute()
                columns = []
                placeholders = []
                
                if response.data:
                    columns = list(response.data[0].keys())
                    
                    for col in columns:
                        if col == 'id':
                            placeholders.append(f"{entity_name}_id")
                        elif col.startswith(f"{entity_name}_"):
                            placeholders.append(col)
                        else:
                            placeholders.append(f"{prefix}{col}")
                
                schema["entities"][entity_name] = {
                    "prefix": prefix,
                    "table": table_name,
                    "id_type": id_type,
                    "placeholder_count": len(placeholders),
                    "sample_placeholders": placeholders[:15],
                    "all_columns": columns,
                    "usage_example": f"{{{{" + placeholders[1] + "}}}}" if len(placeholders) > 1 else f"{{{{{entity_name}_name}}}}"
                }
            except Exception as e:
                schema["entities"][entity_name] = {
                    "prefix": prefix,
                    "table": table_name,
                    "id_type": id_type,
                    "error": str(e)
                }
        
        return {"success": True, "schema": schema}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get schema: {str(e)}")

# =============================================================================
# MAIN DOCUMENT PROCESSING ENDPOINT (Task 7)
# =============================================================================

@app.post("/process-document")
async def process_document_v2(request: DocumentProcessRequest):
    """
    Process a document template with payload-driven data.
    
    Required: template_name
    Optional: vessel_id, buyer_id, seller_id, product_id, refinery_id, 
              broker_id, deal_id, departure_port_id, destination_port_id,
              buyer_bank_id, seller_bank_id, company_id, company_bank_id
    """
    try:
        # Find template file
        template_path = os.path.join(TEMPLATES_DIR, request.template_name)
        if not os.path.exists(template_path):
            template_path = os.path.join(TEMPLATES_DIR, f"{request.template_name}.docx")
            if not os.path.exists(template_path):
                raise HTTPException(status_code=404, detail=f"Template not found: {request.template_name}")
        
        print(f"\n{'='*60}")
        print(f"Processing document: {request.template_name}")
        print(f"{'='*60}")
        
        # Fetch all required data based on payload
        data = fetch_document_data(request)
        
        # Extract placeholders from template
        doc = Document(template_path)
        full_text = ""
        for paragraph in doc.paragraphs:
            full_text += paragraph.text + "\n"
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    full_text += cell.text + "\n"
        
        placeholders = find_placeholders(full_text)
        print(f"\nFound {len(placeholders)} placeholders in template")
        
        # Detect required IDs based on placeholders and check what's missing
        required_ids = set()
        missing_ids = []
        
        for placeholder in placeholders:
            normalized = normalize_placeholder(placeholder)
            
            # Check legacy mapping first
            if normalized in LEGACY_PLACEHOLDER_MAPPING:
                entity, _ = LEGACY_PLACEHOLDER_MAPPING[normalized]
                if entity == "vessel" and not request.vessel_id:
                    required_ids.add("vessel_id")
                elif entity == "buyer" and not request.buyer_id:
                    required_ids.add("buyer_id")
                elif entity == "seller" and not request.seller_id:
                    required_ids.add("seller_id")
                elif entity == "product" and not request.product_id:
                    required_ids.add("product_id")
                elif entity == "refinery" and not request.refinery_id:
                    required_ids.add("refinery_id")
                elif entity == "broker" and not request.broker_id:
                    required_ids.add("broker_id")
                elif entity == "deal" and not request.deal_id:
                    required_ids.add("deal_id")
                elif entity == "company" and not request.company_id:
                    required_ids.add("company_id")
                elif entity == "destination_port" and not request.destination_port_id:
                    required_ids.add("destination_port_id")
                elif entity == "departure_port" and not request.departure_port_id:
                    required_ids.add("departure_port_id")
            else:
                # Check prefix-based
                prefix = identify_prefix(placeholder)
                if prefix:
                    if prefix == "vessel_" and not request.vessel_id:
                        required_ids.add("vessel_id")
                    elif prefix == "buyer_" and not request.buyer_id:
                        required_ids.add("buyer_id")
                    elif prefix == "seller_" and not request.seller_id:
                        required_ids.add("seller_id")
                    elif prefix == "product_" and not request.product_id:
                        required_ids.add("product_id")
                    elif prefix == "refinery_" and not request.refinery_id:
                        required_ids.add("refinery_id")
                    elif prefix == "broker_" and not request.broker_id:
                        required_ids.add("broker_id")
                    elif prefix == "deal_" and not request.deal_id:
                        required_ids.add("deal_id")
                    elif prefix == "company_" and not request.company_id:
                        required_ids.add("company_id")
                    elif prefix == "destination_port_" and not request.destination_port_id:
                        required_ids.add("destination_port_id")
                    elif prefix == "departure_port_" and not request.departure_port_id:
                        required_ids.add("departure_port_id")
                    elif prefix == "buyer_bank_" and not request.buyer_bank_id and not request.buyer_id:
                        required_ids.add("buyer_bank_id (or buyer_id)")
                    elif prefix == "seller_bank_" and not request.seller_bank_id and not request.seller_id:
                        required_ids.add("seller_bank_id (or seller_id)")
                    elif prefix == "company_bank_" and not request.company_bank_id and not request.company_id:
                        required_ids.add("company_bank_id (or company_id)")
                    elif prefix == "port_" and not request.destination_port_id and not request.departure_port_id:
                        required_ids.add("port_id (destination_port_id or departure_port_id)")
        
        missing_ids = sorted(list(required_ids))
        if missing_ids:
            print(f"Warning: Missing IDs for complete replacement: {', '.join(missing_ids)}")
        
        # Build replacement mapping
        mapping = build_replacement_mapping(data, placeholders)
        print(f"\nBuilt mapping for {len(mapping)} placeholders")
        
        # Calculate replacement rate
        replacement_rate = (len(mapping) / len(placeholders) * 100) if placeholders else 0
        print(f"Replacement rate: {replacement_rate:.1f}%")
        
        # Replace placeholders in document
        processed_path = replace_placeholders_in_docx(template_path, mapping)
        
        # Convert to PDF if requested
        output_format = request.output_format or "pdf"
        if output_format.lower() == "pdf":
            output_path = convert_docx_to_pdf(processed_path)
        else:
            output_path = processed_path
        
        # Read and return file
        with open(output_path, 'rb') as f:
            content = f.read()
        
        # Cleanup temp files
        if os.path.exists(processed_path) and processed_path != output_path:
            os.remove(processed_path)
        if os.path.exists(output_path):
            os.remove(output_path)
        
        content_type = "application/pdf" if output_format.lower() == "pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        filename = f"processed_{request.template_name.replace('.docx', '')}.{output_format.lower()}"
        
        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Replacement-Rate": f"{replacement_rate:.1f}%",
            "X-Placeholders-Found": str(len(placeholders)),
            "X-Placeholders-Replaced": str(len(mapping))
        }
        
        if missing_ids:
            headers["X-Missing-IDs"] = ",".join(missing_ids)
            headers["X-Warning"] = f"Missing {len(missing_ids)} IDs for complete placeholder replacement"
        
        return Response(
            content=content,
            media_type=content_type,
            headers=headers
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error processing document: {e}")
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")

@app.post("/upload-template")
async def upload_template(
    name: str = Form(...),
    description: str = Form(""),
    file: UploadFile = File(...)
):
    """Upload a new template"""
    try:
        if not file.filename.lower().endswith('.docx'):
            raise HTTPException(status_code=400, detail="Only .docx files are allowed")
        
        file_path = os.path.join(TEMPLATES_DIR, file.filename)
        with open(file_path, 'wb') as f:
            content = await file.read()
            f.write(content)
        
        return {
            "success": True,
            "message": "Template uploaded successfully",
            "template": {
                "name": name,
                "description": description,
                "file_name": file.filename,
                "file_size": len(content)
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@app.post("/analyze-template")
async def analyze_template(template_name: str = Form(...)):
    """Analyze a template and return required IDs based on placeholders"""
    try:
        template_path = os.path.join(TEMPLATES_DIR, template_name)
        if not os.path.exists(template_path):
            template_path = os.path.join(TEMPLATES_DIR, f"{template_name}.docx")
            if not os.path.exists(template_path):
                raise HTTPException(status_code=404, detail=f"Template not found: {template_name}")
        
        doc = Document(template_path)
        full_text = ""
        for paragraph in doc.paragraphs:
            full_text += paragraph.text + "\n"
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    full_text += cell.text + "\n"
        
        placeholders = find_placeholders(full_text)
        
        # Analyze required IDs
        required_ids = set()
        prefix_to_id = {
            "vessel_": "vessel_id",
            "departure_port_": "departure_port_id",
            "destination_port_": "destination_port_id",
            "port_": "port_id",
            "company_": "company_id",
            "buyer_": "buyer_id",
            "seller_": "seller_id",
            "refinery_": "refinery_id",
            "product_": "product_id",
            "broker_": "broker_id",
            "deal_": "deal_id",
            "buyer_bank_": "buyer_bank_id (or buyer_id for auto-fetch)",
            "seller_bank_": "seller_bank_id (or seller_id for auto-fetch)",
            "company_bank_": "company_bank_id (or company_id for auto-fetch)",
        }
        
        prefix_counts = {}
        for p in placeholders:
            prefix = identify_prefix(p)
            if prefix:
                prefix_counts[prefix] = prefix_counts.get(prefix, 0) + 1
                if prefix in prefix_to_id:
                    required_ids.add(prefix_to_id[prefix])
        
        return {
            "success": True,
            "template_name": template_name,
            "total_placeholders": len(placeholders),
            "placeholders": placeholders,
            "prefix_analysis": prefix_counts,
            "required_payload_ids": list(required_ids),
            "example_payload": {
                "template_name": template_name,
                **{id_name.split(" ")[0]: "<provide_id>" for id_name in required_ids}
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)

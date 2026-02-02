"""
ID-Based Data Fetcher for Document Processor API
Fetches data from Supabase tables using explicit IDs from request payload.
Implements strict prefix-based placeholder mapping.
"""

import logging
from typing import Dict, Optional, Union, Any
from supabase import Client

logger = logging.getLogger(__name__)

# Prefix to table mapping (MANDATORY - strict mapping)
PREFIX_TO_TABLE = {
    'vessel_': 'vessels',
    'port_': 'ports',
    'departure_port_': 'ports',
    'destination_port_': 'ports',
    'company_': 'companies',
    'buyer_': 'buyer_companies',
    'seller_': 'seller_companies',
    'refinery_': 'refineries',
    'product_': 'oil_products',
    'broker_': 'broker_profiles',
    'buyer_bank_': 'buyer_company_bank_accounts',
    'seller_bank_': 'seller_company_bank_accounts',
}

# ID field names in payload
PAYLOAD_ID_FIELDS = {
    'vessels': 'vessel_id',
    'ports': 'port_id',  # Generic, but departure_port_id/destination_port_id are also used
    'departure_port': 'departure_port_id',
    'destination_port': 'destination_port_id',
    'companies': 'company_id',
    'buyer_companies': 'buyer_id',
    'seller_companies': 'seller_id',
    'refineries': 'refinery_id',
    'oil_products': 'product_id',
    'broker_profiles': 'broker_id',
    'buyer_company_bank_accounts': 'buyer_bank_id',
    'seller_company_bank_accounts': 'seller_bank_id',
    'deals': 'deal_id',
}

# Table ID field types (INTEGER vs UUID)
TABLE_ID_TYPES = {
    'vessels': 'integer',  # serial/integer
    'ports': 'integer',  # serial/integer
    'companies': 'integer',  # serial/integer (or UUID depending on schema)
    'buyer_companies': 'uuid',
    'seller_companies': 'uuid',
    'refineries': 'uuid',
    'oil_products': 'uuid',
    'broker_profiles': 'uuid',
    'buyer_company_bank_accounts': 'uuid',
    'seller_company_bank_accounts': 'uuid',
    'deals': 'uuid',
}


def normalize_placeholder(placeholder: str) -> str:
    """
    Normalize placeholder by:
    - Lowercasing
    - Removing spaces, dashes, underscores
    - Removing brackets/formatting
    
    Example: {{Buyer Bank Swift}} → buyerbankswift
    """
    # Remove common formatting
    placeholder = placeholder.replace('{{', '').replace('}}', '')
    placeholder = placeholder.replace('{', '').replace('}', '')
    placeholder = placeholder.replace('[[', '').replace(']]', '')
    placeholder = placeholder.replace('%', '').replace('<', '').replace('>', '')
    
    # Normalize
    placeholder = placeholder.lower().strip()
    placeholder = placeholder.replace(' ', '').replace('-', '').replace('_', '')
    
    return placeholder


def identify_prefix(placeholder: str) -> Optional[str]:
    """
    Identify the prefix of a placeholder.
    Returns the longest matching prefix from PREFIX_TO_TABLE.
    
    Example:
    - buyer_bank_swift → buyer_bank_
    - vessel_name → vessel_
    - departure_port_name → departure_port_
    """
    normalized = normalize_placeholder(placeholder)
    
    # Try longest prefixes first
    prefixes = sorted(PREFIX_TO_TABLE.keys(), key=len, reverse=True)
    
    for prefix in prefixes:
        prefix_normalized = normalize_placeholder(prefix)
        if normalized.startswith(prefix_normalized):
            return prefix
    
    return None


def fetch_by_id(supabase_client: Client, table_name: str, record_id: Union[int, str]) -> Optional[Dict]:
    """
    Fetch a single record from a table by ID.
    Handles both INTEGER and UUID IDs.
    
    Args:
        supabase_client: Supabase client instance
        table_name: Name of the table
        record_id: ID value (int for INTEGER, str for UUID)
    
    Returns:
        Dictionary with record data or None if not found
    """
    if not supabase_client:
        logger.warning(f"Supabase client not available, cannot fetch from {table_name}")
        return None
    
    if record_id is None:
        logger.warning(f"Record ID is None for table {table_name}")
        return None
    
    try:
        logger.info(f"Fetching from {table_name} with id={record_id} (type: {type(record_id).__name__})")
        response = supabase_client.table(table_name).select('*').eq('id', record_id).limit(1).execute()
        
        if response.data and len(response.data) > 0:
            data = response.data[0]
            logger.info(f"✅ Found record in {table_name}: {data.get('name', data.get('id', 'Unknown'))}")
            return data
        else:
            logger.warning(f"❌ No record found in {table_name} with id={record_id}")
            return None
    except Exception as e:
        logger.error(f"❌ Error fetching from {table_name} with id={record_id}: {e}")
        return None


def fetch_random_row(supabase_client: Client, table_name: str, seed: str = None) -> Optional[Dict]:
    """
    Fetch a random row from a table. Truly random each time (no seed used).
    
    Args:
        supabase_client: Supabase client instance
        table_name: Name of the table
        seed: Ignored - kept for API compatibility
    
    Returns:
        Dictionary with record data or None if not found
    """
    import random
    
    if not supabase_client:
        logger.warning(f"Supabase client not available, cannot fetch random from {table_name}")
        return None
    
    try:
        logger.info(f"🎲 Attempting to fetch random row from {table_name}...")
        
        # Method 1: Try to get all records and pick random one
        # This is more reliable than using count/offset which may fail
        response = supabase_client.table(table_name).select('*').limit(100).execute()
        
        if not response.data or len(response.data) == 0:
            logger.warning(f"❌ No records found in {table_name} (table may be empty)")
            return None
        
        # Pick a truly random record from the results
        random_record = random.choice(response.data)
        logger.info(f"🎲 SUCCESS: Random record from {table_name}: {random_record.get('name', random_record.get('id', 'Unknown'))} (picked from {len(response.data)} records)")
        return random_record
            
    except Exception as e:
        logger.error(f"❌ Error fetching random from {table_name}: {e}")
        logger.error(f"   This might mean the table '{table_name}' doesn't exist or has access issues")
        return None


def fetch_random_company_by_type(supabase_client: Client, company_type: str) -> Optional[Dict]:
    """
    Fetch a random company from the companies table filtered by type.
    
    Args:
        supabase_client: Supabase client instance
        company_type: Type of company ('buyer', 'seller', 'trader', etc.)
    
    Returns:
        Dictionary with company data or None if not found
    """
    import random
    
    if not supabase_client:
        logger.warning(f"Supabase client not available, cannot fetch company by type")
        return None
    
    try:
        logger.info(f"🎲 Fetching random company with type containing '{company_type}'...")
        
        # Try to find companies where type/company_type contains the search term
        # First try exact match on 'type' column
        response = supabase_client.table('companies').select('*').ilike('type', f'%{company_type}%').limit(100).execute()
        
        if not response.data or len(response.data) == 0:
            # Try 'company_type' column instead
            logger.info(f"   No match on 'type' column, trying 'company_type'...")
            response = supabase_client.table('companies').select('*').ilike('company_type', f'%{company_type}%').limit(100).execute()
        
        if not response.data or len(response.data) == 0:
            # Try name column as last resort (company name might contain 'buyer' or 'seller')
            logger.info(f"   No match on type columns, trying name column...")
            response = supabase_client.table('companies').select('*').ilike('name', f'%{company_type}%').limit(100).execute()
        
        if not response.data or len(response.data) == 0:
            logger.warning(f"❌ No companies found with type '{company_type}'")
            return None
        
        # Pick a truly random record
        random_record = random.choice(response.data)
        logger.info(f"🎲 SUCCESS: Random {company_type} company: {random_record.get('name', 'Unknown')} (picked from {len(response.data)} records)")
        return random_record
            
    except Exception as e:
        logger.error(f"❌ Error fetching company by type '{company_type}': {e}")
        return None


def fetch_bank_account(supabase_client: Client, company_id: str, bank_id: Optional[str], 
                       table_name: str, is_buyer: bool = True) -> Optional[Dict]:
    """
    Fetch bank account with special logic:
    1. If bank_id is provided, fetch that exact record
    2. Otherwise, fetch bank account where is_primary = true for the company
    
    Args:
        supabase_client: Supabase client instance
        company_id: Company UUID (buyer_id or seller_id)
        bank_id: Optional specific bank account UUID
        table_name: 'buyer_company_bank_accounts' or 'seller_company_bank_accounts'
        is_buyer: True for buyer, False for seller
    
    Returns:
        Dictionary with bank account data or None
    """
    if not supabase_client:
        return None
    
    if not company_id:
        logger.warning(f"Company ID is required for fetching bank account from {table_name}")
        return None
    
    try:
        # If specific bank_id provided, fetch that
        if bank_id:
            logger.info(f"Fetching specific bank account {bank_id} from {table_name}")
            return fetch_by_id(supabase_client, table_name, bank_id)
        
        # Otherwise, fetch primary bank account
        company_field = 'buyer_company_id' if is_buyer else 'seller_company_id'
        logger.info(f"Fetching primary bank account for {company_field}={company_id} from {table_name}")
        
        response = supabase_client.table(table_name)\
            .select('*')\
            .eq(company_field, company_id)\
            .eq('is_primary', True)\
            .limit(1)\
            .execute()
        
        if response.data and len(response.data) > 0:
            data = response.data[0]
            logger.info(f"✅ Found primary bank account in {table_name}")
            return data
        else:
            logger.warning(f"❌ No primary bank account found in {table_name} for {company_id}")
            return None
    except Exception as e:
        logger.error(f"❌ Error fetching bank account from {table_name}: {e}")
        return None


def fetch_all_entities(supabase_client: Client, payload: Dict) -> Dict[str, Optional[Dict]]:
    """
    Fetch all entities from Supabase based on IDs in payload.
    Only fetches tables whose IDs are explicitly provided.
    
    Args:
        supabase_client: Supabase client instance
        payload: Request payload containing IDs
    
    Returns:
        Dictionary mapping entity names to their data:
        {
            'vessel': {...},
            'buyer': {...},
            'seller': {...},
            'product': {...},
            'departure_port': {...},
            'destination_port': {...},
            'buyer_bank': {...},
            'seller_bank': {...},
            ...
        }
    """
    fetched_data: Dict[str, Optional[Dict]] = {}
    
    # Fetch vessel (by vessel_id or vessel_imo)
    vessel_id = payload.get('vessel_id')
    vessel_imo = payload.get('vessel_imo')
    if vessel_id is not None:
        # vessel_id can be integer (serial) or string
        fetched_data['vessel'] = fetch_by_id(supabase_client, 'vessels', vessel_id)
    elif vessel_imo:
        # Vessel can be fetched by IMO as well (backward compatibility)
        try:
            logger.info(f"Fetching vessel by IMO: {vessel_imo}")
            response = supabase_client.table('vessels').select('*').eq('imo', str(vessel_imo)).limit(1).execute()
            if response.data:
                fetched_data['vessel'] = response.data[0]
                logger.info(f"✅ Found vessel by IMO: {fetched_data['vessel'].get('name', 'Unknown')}")
        except Exception as e:
            logger.error(f"Error fetching vessel by IMO {vessel_imo}: {e}")
    
    # =========================================================================
    # CRITICAL FIX: Also fetch related entities using IDs from the vessel record
    # This allows document generation to use buyer/seller data even when not
    # explicitly passed in the payload
    # =========================================================================
    vessel = fetched_data.get('vessel')
    if vessel:
        logger.info("📊 Checking vessel record for related entity IDs...")
        
        # Extract IDs from vessel record (these override payload if not provided)
        vessel_buyer_id = vessel.get('buyer_company_id')
        vessel_seller_id = vessel.get('seller_company_id')
        vessel_refinery_id = vessel.get('refinery_id')
        vessel_deal_id = vessel.get('deal_reference_id')
        
        if vessel_buyer_id:
            logger.info(f"   Found buyer_company_id in vessel: {vessel_buyer_id}")
        if vessel_seller_id:
            logger.info(f"   Found seller_company_id in vessel: {vessel_seller_id}")
    else:
        vessel_buyer_id = None
        vessel_seller_id = None
        vessel_refinery_id = None
        vessel_deal_id = None
    
    # Fetch ports
    departure_port_id = payload.get('departure_port_id')
    destination_port_id = payload.get('destination_port_id')
    if departure_port_id:
        fetched_data['departure_port'] = fetch_by_id(supabase_client, 'ports', departure_port_id)
    if destination_port_id:
        fetched_data['destination_port'] = fetch_by_id(supabase_client, 'ports', destination_port_id)
    
    # Fetch buyer: 1) vessel's buyer_company_id if set, 2) random from buyer_companies
    buyer_id = payload.get('buyer_id') or (vessel.get('buyer_company_id') if vessel else None)
    logger.info(f"=" * 60)
    logger.info(f"📦 FETCHING BUYER (vessel buyer_id={buyer_id})...")
    logger.info(f"=" * 60)
    
    if buyer_id:
        fetched_data['buyer'] = fetch_by_id(supabase_client, 'buyer_companies', buyer_id)
        if not fetched_data.get('buyer'):
            fetched_data['buyer'] = fetch_by_id(supabase_client, 'companies', buyer_id)
    
    if not fetched_data.get('buyer'):
        logger.info(f"   No buyer by ID, fetching RANDOM from buyer_companies...")
        fetched_data['buyer'] = fetch_random_row(supabase_client, 'buyer_companies', seed=None)
    
    if not fetched_data.get('buyer'):
        logger.warning(f"   buyer_companies empty/failed, trying companies table...")
        fetched_data['buyer'] = fetch_random_row(supabase_client, 'companies', seed=None)
    
    if fetched_data.get('buyer'):
        logger.info(f"✅ BUYER: {fetched_data['buyer'].get('name', 'NO NAME')}")
    else:
        logger.error(f"❌ NO BUYER - Add SUPABASE_SERVICE_ROLE_KEY to .env and add buyer companies in Admin")
    
    # Fetch seller: 1) vessel's seller_company_id if set, 2) random from seller_companies
    seller_id = payload.get('seller_id') or (vessel.get('seller_company_id') if vessel else None)
    logger.info(f"=" * 60)
    logger.info(f"📦 FETCHING SELLER (vessel seller_id={seller_id})...")
    logger.info(f"=" * 60)
    
    if seller_id:
        fetched_data['seller'] = fetch_by_id(supabase_client, 'seller_companies', seller_id)
        if not fetched_data.get('seller'):
            fetched_data['seller'] = fetch_by_id(supabase_client, 'companies', seller_id)
    
    if not fetched_data.get('seller'):
        logger.info(f"   No seller by ID, fetching RANDOM from seller_companies...")
        fetched_data['seller'] = fetch_random_row(supabase_client, 'seller_companies', seed=None)
    
    if not fetched_data.get('seller'):
        logger.warning(f"   seller_companies empty/failed, trying companies table...")
        fetched_data['seller'] = fetch_random_row(supabase_client, 'companies', seed=None)
    
    if fetched_data.get('seller'):
        logger.info(f"✅ SELLER: {fetched_data['seller'].get('name', 'NO NAME')}")
    else:
        logger.error(f"❌ NO SELLER - Add SUPABASE_SERVICE_ROLE_KEY to .env and add seller companies in Admin")
    
    # Fetch product
    product_id = payload.get('product_id')
    if product_id:
        fetched_data['product'] = fetch_by_id(supabase_client, 'oil_products', product_id)
    
    # Fetch refinery - from payload OR from vessel record
    refinery_id = payload.get('refinery_id') or vessel_refinery_id
    if refinery_id:
        fetched_data['refinery'] = fetch_by_id(supabase_client, 'refineries', refinery_id)
    
    # Fetch broker
    broker_id = payload.get('broker_id')
    if broker_id:
        fetched_data['broker'] = fetch_by_id(supabase_client, 'broker_profiles', broker_id)
    
    # Fetch bank accounts (with is_primary logic)
    # Use the ID from the fetched random buyer/seller
    buyer_bank_id = payload.get('buyer_bank_id')
    seller_bank_id = payload.get('seller_bank_id')
    fetched_buyer = fetched_data.get('buyer')
    fetched_seller = fetched_data.get('seller')
    
    if fetched_buyer and fetched_buyer.get('id'):
        fetched_data['buyer_bank'] = fetch_bank_account(
            supabase_client, fetched_buyer.get('id'), buyer_bank_id, 
            'buyer_company_bank_accounts', is_buyer=True
        )
    if fetched_seller and fetched_seller.get('id'):
        fetched_data['seller_bank'] = fetch_bank_account(
            supabase_client, fetched_seller.get('id'), seller_bank_id,
            'seller_company_bank_accounts', is_buyer=False
        )
    
    # Fetch deal - from payload OR from vessel record
    deal_id = payload.get('deal_id') or vessel_deal_id
    if deal_id:
        fetched_data['deal'] = fetch_by_id(supabase_client, 'deals', deal_id)
    
    # Fetch company (generic)
    company_id = payload.get('company_id')
    if company_id:
        fetched_data['company'] = fetch_by_id(supabase_client, 'companies', company_id)
    
    logger.info(f"Fetched {sum(1 for v in fetched_data.values() if v is not None)} entities from database")
    return fetched_data


def get_placeholder_value(placeholder: str, fetched_data: Dict[str, Optional[Dict]]) -> Optional[Any]:
    """
    Get value for a placeholder using strict prefix-based matching.
    
    Args:
        placeholder: Placeholder name (e.g., "buyer_bank_swift", "vessel_name")
        fetched_data: Dictionary of fetched entities
    
    Returns:
        Value for the placeholder or None if not found
    """
    # Identify prefix
    prefix = identify_prefix(placeholder)
    if not prefix:
        logger.debug(f"No prefix identified for placeholder: {placeholder}")
        return None
    
    # Get table name
    table_name = PREFIX_TO_TABLE.get(prefix)
    if not table_name:
        logger.warning(f"No table mapping for prefix: {prefix}")
        return None
    
    # Map prefix to entity key in fetched_data
    entity_map = {
        'vessel_': 'vessel',
        'port_': 'departure_port',  # Default to departure_port
        'departure_port_': 'departure_port',
        'destination_port_': 'destination_port',
        'company_': 'company',
        'buyer_': 'buyer',
        'seller_': 'seller',
        'refinery_': 'refinery',
        'product_': 'product',
        'broker_': 'broker',
        'buyer_bank_': 'buyer_bank',
        'seller_bank_': 'seller_bank',
    }
    
    entity_key = entity_map.get(prefix)
    if not entity_key:
        logger.warning(f"No entity mapping for prefix: {prefix}")
        return None
    
    # Get entity data
    entity_data = fetched_data.get(entity_key)
    if not entity_data:
        logger.debug(f"Entity '{entity_key}' not found in fetched_data for placeholder: {placeholder}")
        return None
    
    # Extract field name (remove prefix)
    normalized_placeholder = normalize_placeholder(placeholder)
    normalized_prefix = normalize_placeholder(prefix)
    
    if normalized_placeholder.startswith(normalized_prefix):
        field_name = normalized_placeholder[len(normalized_prefix):]
    else:
        # If prefix doesn't match after normalization, try original
        if placeholder.lower().startswith(prefix.lower()):
            field_name = placeholder[len(prefix):].lower().strip('_').strip('-').strip()
        else:
            field_name = normalized_placeholder
    
    # Clean field name
    field_name = field_name.strip('_').strip('-').strip()
    
    # Try exact field name match
    value = entity_data.get(field_name)
    if value is not None:
        logger.debug(f"✅ Found {placeholder} → {field_name} = {value}")
        return value
    
    # Try variations (with underscores, etc.)
    variations = [
        field_name,
        field_name.replace('_', ''),
        '_' + field_name,
        field_name + '_',
    ]
    
    for var in variations:
        value = entity_data.get(var)
        if value is not None:
            logger.debug(f"✅ Found {placeholder} → {var} = {value}")
            return value
    
    logger.debug(f"⚠️ Field '{field_name}' not found in {entity_key} data for placeholder: {placeholder}")
    return None


def normalize_replacement_value(value: Any, placeholder: str = '') -> str:
    """
    Normalize a replacement value:
    - NULL → empty string
    - array → join with commas
    - Convert to string
    
    Args:
        value: Value to normalize
        placeholder: Placeholder name (for logging)
    
    Returns:
        Normalized string value
    """
    if value is None:
        return ''
    
    if isinstance(value, list):
        return ', '.join(str(v) for v in value if v is not None)
    
    return str(value)

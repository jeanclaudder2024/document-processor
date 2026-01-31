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
    
    # Fetch ports
    departure_port_id = payload.get('departure_port_id')
    destination_port_id = payload.get('destination_port_id')
    if departure_port_id:
        fetched_data['departure_port'] = fetch_by_id(supabase_client, 'ports', departure_port_id)
    if destination_port_id:
        fetched_data['destination_port'] = fetch_by_id(supabase_client, 'ports', destination_port_id)
    
    # Fetch buyer company
    buyer_id = payload.get('buyer_id')
    if buyer_id:
        fetched_data['buyer'] = fetch_by_id(supabase_client, 'buyer_companies', buyer_id)
    
    # Fetch seller company
    seller_id = payload.get('seller_id')
    if seller_id:
        fetched_data['seller'] = fetch_by_id(supabase_client, 'seller_companies', seller_id)
    
    # Fetch product
    product_id = payload.get('product_id')
    if product_id:
        fetched_data['product'] = fetch_by_id(supabase_client, 'oil_products', product_id)
    
    # Fetch refinery
    refinery_id = payload.get('refinery_id')
    if refinery_id:
        fetched_data['refinery'] = fetch_by_id(supabase_client, 'refineries', refinery_id)
    
    # Fetch broker
    broker_id = payload.get('broker_id')
    if broker_id:
        fetched_data['broker'] = fetch_by_id(supabase_client, 'broker_profiles', broker_id)
    
    # Fetch bank accounts (with is_primary logic)
    buyer_bank_id = payload.get('buyer_bank_id')
    seller_bank_id = payload.get('seller_bank_id')
    if buyer_id:
        fetched_data['buyer_bank'] = fetch_bank_account(
            supabase_client, buyer_id, buyer_bank_id, 
            'buyer_company_bank_accounts', is_buyer=True
        )
    if seller_id:
        fetched_data['seller_bank'] = fetch_bank_account(
            supabase_client, seller_id, seller_bank_id,
            'seller_company_bank_accounts', is_buyer=False
        )
    
    # Fetch deal
    deal_id = payload.get('deal_id')
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

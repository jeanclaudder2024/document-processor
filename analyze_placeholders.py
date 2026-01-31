"""
Analyze all placeholders linked to database tables
This script shows which placeholders are mapped to which tables
"""

import json
from typing import Dict, List, Tuple

# Current placeholder mappings from main.py
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
    'companyname': ('companies', 'name'), 'company_name': ('companies', 'name'),
    'sellercompanyname': ('companies', 'name'), 'seller_company_name': ('companies', 'name'), 'buyercompanyname': ('companies', 'name'), 'buyer_company_name': ('companies', 'name'),
    'registrationcountry': ('companies', 'country'), 'registration_country': ('companies', 'country'),
    'sellercountry': ('companies', 'country'), 'seller_country': ('companies', 'country'), 'buyercountry': ('companies', 'country'), 'buyer_country': ('companies', 'country'),
    'sellerregistrationcountry': ('companies', 'country'), 'seller_registration_country': ('companies', 'country'),
    'buyerregistrationcountry': ('companies', 'country'), 'buyer_registration_country': ('companies', 'country'),
    'legaladdress': ('companies', 'address'), 'legal_address': ('companies', 'address'),
    'sellerlegaladdress': ('companies', 'address'), 'seller_legal_address': ('companies', 'address'), 'buyerlegaladdress': ('companies', 'address'), 'buyer_legal_address': ('companies', 'address'),
    'selleraddress': ('companies', 'address'), 'seller_address': ('companies', 'address'), 'buyeraddress': ('companies', 'address'), 'buyer_address': ('companies', 'address'),
    'selleremail': ('companies', 'email'), 'seller_email': ('companies', 'email'), 'buyeremail': ('companies', 'email'), 'buyer_email': ('companies', 'email'),
    'sellerphone': ('companies', 'phone'), 'seller_phone': ('companies', 'phone'), 'buyerphone': ('companies', 'phone'), 'buyer_phone': ('companies', 'phone'),
}

# Predefined columns from main.py
PREDEFINED_COLUMNS = {
    'vessels': [
        'id', 'name', 'imo', 'mmsi', 'vessel_type', 'flag', 'built', 'deadweight', 'cargo_capacity',
        'cargo_capacity_bbl', 'length', 'width', 'beam', 'draft', 'draught', 'gross_tonnage',
        'owner_name', 'operator_name', 'callsign', 'currentport', 'loading_port', 'discharge_port',
        'departure_port', 'destination_port', 'destination', 'eta', 'nav_status', 'status',
        'vesselstatus', 'fuel_consumption', 'engine_power', 'speed', 'service_speed',
        'deal_value', 'dealvalue', 'deal_status', 'price', 'market_price', 'cargo_type',
        'cargo_quantity', 'oil_type', 'oil_source', 'quantity', 'buyer_name', 'seller_name',
        'email', 'phone', 'address'
    ],
    'ports': [
        'id', 'name', 'country', 'city', 'latitude', 'longitude', 'port_type', 'timezone',
        'harbor_size', 'harbor_type', 'shelter', 'entrance_width', 'max_vessel_length',
        'max_vessel_beam', 'max_vessel_draft', 'anchorage_depth', 'cargo_pier_depth',
        'oil_terminal_depth', 'container_terminal_depth', 'max_tide', 'min_tide'
    ],
    'companies': [
        'id', 'name', 'email', 'phone', 'country', 'address', 'city', 'website', 'company_type',
        'registration_number', 'tax_id', 'legal_name', 'contact_person', 'contact_email',
        'contact_phone', 'industry', 'established_year', 'employee_count', 'annual_revenue'
    ],
    'refineries': [
        'id', 'name', 'location', 'capacity', 'products', 'country', 'city', 'latitude',
        'longitude', 'refinery_type', 'crude_capacity', 'distillation_capacity',
        'cracking_capacity', 'reforming_capacity', 'owner', 'operator', 'established_year'
    ]
}

def analyze_placeholders():
    """Analyze and group placeholders by table"""
    
    # Group placeholders by table
    table_placeholders: Dict[str, Dict[str, List[str]]] = {}
    
    for placeholder, (table, column) in _UPLOAD_FIELD_MAPPINGS.items():
        if table not in table_placeholders:
            table_placeholders[table] = {}
        if column not in table_placeholders[table]:
            table_placeholders[table][column] = []
        table_placeholders[table][column].append(placeholder)
    
    # Print analysis
    print("=" * 80)
    print("PLACEHOLDER ANALYSIS BY TABLE")
    print("=" * 80)
    print()
    
    total_placeholders = 0
    
    for table in sorted(table_placeholders.keys()):
        columns = table_placeholders[table]
        table_total = sum(len(placeholders) for placeholders in columns.values())
        total_placeholders += table_total
        
        print(f"[TABLE] {table.upper()}")
        print(f"   Total Placeholders: {table_total}")
        print(f"   Total Columns Used: {len(columns)}")
        print()
        
        for column in sorted(columns.keys()):
            placeholders = columns[column]
            print(f"   - Column: {column}")
            print(f"      Placeholders ({len(placeholders)}): {', '.join(placeholders)}")
            print()
        
        print("-" * 80)
        print()
    
    print(f"TOTAL PLACEHOLDERS ACROSS ALL TABLES: {total_placeholders}")
    print()
    
    # Show missing tables
    print("=" * 80)
    print("MISSING TABLES (Not Currently Linked)")
    print("=" * 80)
    print()
    
    missing_tables = [
        'buyer_companies',
        'vessel_companies', 
        'real_companies',
        'products',
        'brokers',
        'deals',
        'contracts',
        'invoices',
        'payments',
        'bank_accounts',
        'contacts',
        'vessel_positions',
        'cargo',
        'inspections',
        'certificates'
    ]
    
    for table in missing_tables:
        print(f"[MISSING] {table} - Not currently mapped")
    
    print()
    
    # Show available columns per table
    print("=" * 80)
    print("AVAILABLE COLUMNS PER TABLE (From Database Schema)")
    print("=" * 80)
    print()
    
    for table, columns in PREDEFINED_COLUMNS.items():
        print(f"[SCHEMA] {table.upper()}")
        print(f"   Total Columns: {len(columns)}")
        print(f"   Columns: {', '.join(columns)}")
        print()
    
    # Generate JSON report
    report = {
        'summary': {
            'total_placeholders': total_placeholders,
            'tables_with_mappings': len(table_placeholders),
            'tables_missing': missing_tables
        },
        'table_mappings': {},
        'available_columns': PREDEFINED_COLUMNS
    }
    
    for table, columns in table_placeholders.items():
        report['table_mappings'][table] = {
            'total_placeholders': sum(len(placeholders) for placeholders in columns.values()),
            'columns': {
                column: {
                    'placeholder_count': len(placeholders),
                    'placeholders': placeholders
                }
                for column, placeholders in columns.items()
            }
        }
    
    # Save report
    with open('placeholder_analysis_report.json', 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print("=" * 80)
    print("[SUCCESS] Report saved to: placeholder_analysis_report.json")
    print("=" * 80)

if __name__ == "__main__":
    analyze_placeholders()

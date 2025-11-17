#!/usr/bin/env python3
"""
Test script to diagnose placeholder replacement issues.
Tests placeholder extraction, CMS settings loading, and data mapping.

Usage:
    # Use venv Python directly (recommended):
    venv/bin/python3 test_placeholder_replacement.py "ICPO TEMPLATE.docx"
    
    # OR activate venv first:
    source venv/bin/activate
    python3 test_placeholder_replacement.py "ICPO TEMPLATE.docx"
"""

import os
import sys
import json
import requests
from pathlib import Path

# Check if we're in a venv, if not, try to use venv Python
if not hasattr(sys, 'real_prefix') and not (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
    # Not in venv, check if venv exists
    script_dir = os.path.dirname(os.path.abspath(__file__))
    venv_python = os.path.join(script_dir, 'venv', 'bin', 'python3')
    if os.path.exists(venv_python):
        print("⚠️  Not running in virtual environment.")
        print(f"   Please run: {venv_python} {sys.argv[0]} {' '.join(sys.argv[1:])}")
        print("   OR activate venv: source venv/bin/activate")
        sys.exit(1)

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Try to import functions from main.py
try:
    from main import (
        extract_placeholders_from_docx,
        fetch_template_placeholders,
        resolve_template_record,
        get_vessel_data,
        resolve_placeholder_setting,
        normalise_placeholder_key,
        normalize_template_name,
        read_json_file,
        PLACEHOLDER_SETTINGS_PATH,
        TEMPLATES_DIR
    )
    DIRECT_IMPORTS_AVAILABLE = True
except ImportError as e:
    print(f"❌ Error: Cannot import from main.py: {e}")
    print("\nThis usually means:")
    print("  1. Virtual environment is not activated")
    print("  2. Dependencies are not installed (run: pip install -r requirements.txt)")
    print("\nTo fix:")
    print("  source venv/bin/activate")
    print("  pip install -r requirements.txt")
    print(f"  python3 {sys.argv[0]} {' '.join(sys.argv[1:])}")
    sys.exit(1)

def test_placeholder_extraction(template_name):
    """Test placeholder extraction from a template"""
    print("=" * 80)
    print("TEST 1: Placeholder Extraction")
    print("=" * 80)
    
    template_path = os.path.join(TEMPLATES_DIR, template_name)
    if not os.path.exists(template_path):
        print(f"❌ Template not found: {template_path}")
        return []
    
    placeholders = extract_placeholders_from_docx(template_path)
    print(f"✅ Extracted {len(placeholders)} placeholders:")
    for i, ph in enumerate(placeholders[:50], 1):  # Show first 50
        print(f"   {i}. {ph}")
    if len(placeholders) > 50:
        print(f"   ... and {len(placeholders) - 50} more")
    
    return placeholders

def test_cms_settings_loading(template_name):
    """Test CMS settings loading"""
    print("\n" + "=" * 80)
    print("TEST 2: CMS Settings Loading")
    print("=" * 80)
    
    # Try to resolve template record
    template_record = resolve_template_record(template_name)
    if template_record:
        template_id = template_record['id']
        template_hint = template_record.get('file_name')
        print(f"✅ Template found in database:")
        print(f"   ID: {template_id}")
        print(f"   File name: {template_hint}")
        
        settings = fetch_template_placeholders(template_id, template_hint)
        print(f"✅ Loaded {len(settings)} placeholder settings from CMS")
        if settings:
            print("   Configured placeholders:")
            for i, (ph, cfg) in enumerate(list(settings.items())[:20], 1):
                source = cfg.get('source', 'random')
                db_field = cfg.get('databaseField', '')
                csv_id = cfg.get('csvId', '')
                custom = cfg.get('customValue', '')
                print(f"   {i}. {ph}: source={source}, db={db_field}, csv={csv_id}, custom={custom[:30] if custom else ''}")
            if len(settings) > 20:
                print(f"   ... and {len(settings) - 20} more")
        else:
            print("   ⚠️  No settings found in CMS")
    else:
        print(f"⚠️  Template not found in database, checking disk settings...")
        disk_settings = read_json_file(PLACEHOLDER_SETTINGS_PATH, {})
        
        # Try different template name formats
        candidates = [
            template_name,
            normalize_template_name(template_name, with_extension=True, for_key=False),
            normalize_template_name(template_name, with_extension=False, for_key=False),
        ]
        
        settings = {}
        for candidate in candidates:
            if candidate in disk_settings:
                settings = disk_settings[candidate]
                print(f"✅ Found settings using key: '{candidate}'")
                break
        
        if not settings:
            print("   ❌ No settings found in disk storage either")
        else:
            print(f"✅ Loaded {len(settings)} placeholder settings from disk")
    
    return settings if 'settings' in locals() else {}

def test_placeholder_matching(placeholders, cms_settings):
    """Test placeholder matching between extracted and CMS settings"""
    print("\n" + "=" * 80)
    print("TEST 3: Placeholder Matching")
    print("=" * 80)
    
    matched = []
    unmatched = []
    
    for placeholder in placeholders:
        setting_key, setting = resolve_placeholder_setting(cms_settings, placeholder)
        if setting:
            matched.append((placeholder, setting_key, setting.get('source', 'random')))
        else:
            unmatched.append(placeholder)
    
    print(f"✅ Matched: {len(matched)} placeholders")
    if matched:
        print("   Matched placeholders:")
        for ph, key, source in matched[:20]:
            print(f"   - '{ph}' -> CMS key: '{key}' (source: {source})")
        if len(matched) > 20:
            print(f"   ... and {len(matched) - 20} more")
    
    print(f"\n⚠️  Unmatched: {len(unmatched)} placeholders")
    if unmatched:
        print("   Unmatched placeholders (will use random/intelligent matching):")
        for ph in unmatched[:30]:
            ph_norm = normalise_placeholder_key(ph)
            print(f"   - '{ph}' (normalized: '{ph_norm}')")
            
            # Try to find similar keys
            similar = []
            for key in cms_settings.keys():
                key_norm = normalise_placeholder_key(key)
                if ph_norm == key_norm:
                    similar.append(f"'{key}' (exact normalized match)")
                elif ph_norm in key_norm or key_norm in ph_norm:
                    similarity = len(set(ph_norm) & set(key_norm)) / max(len(ph_norm), len(key_norm))
                    if similarity > 0.5:
                        similar.append(f"'{key}' (similarity: {similarity:.2f})")
            
            if similar:
                print(f"      💡 Similar CMS keys: {', '.join(similar[:3])}")
        if len(unmatched) > 30:
            print(f"   ... and {len(unmatched) - 30} more")
    
    return matched, unmatched

def test_vessel_data_matching(placeholders, vessel_imo="TEST001"):
    """Test matching placeholders to vessel database fields"""
    print("\n" + "=" * 80)
    print("TEST 4: Vessel Data Matching")
    print("=" * 80)
    
    vessel = get_vessel_data(vessel_imo)
    if not vessel:
        print(f"⚠️  Vessel {vessel_imo} not found, using sample data")
        vessel = {
            'imo': vessel_imo,
            'name': 'Test Vessel',
            'deadweight': '50000',
            'owner_name': 'Test Owner',
            'vessel_owner': 'Test Owner',
            'flag': 'Panama',
            'vessel_type': 'Tanker'
        }
    
    print(f"✅ Vessel data loaded: {vessel.get('name', 'Unknown')} (IMO: {vessel.get('imo', 'N/A')})")
    print(f"   Available vessel fields: {list(vessel.keys())[:20]}...")
    
    # Test intelligent matching for unmatched placeholders
    from main import _intelligent_field_match
    
    matched_fields = []
    unmatched_fields = []
    
    for placeholder in placeholders[:30]:  # Test first 30
        field, value = _intelligent_field_match(placeholder, vessel)
        if field and value:
            matched_fields.append((placeholder, field, value))
        else:
            unmatched_fields.append(placeholder)
    
    print(f"\n✅ Intelligent matching results:")
    print(f"   Matched to vessel fields: {len(matched_fields)}")
    if matched_fields:
        for ph, field, val in matched_fields[:15]:
            print(f"   - '{ph}' -> '{field}' = '{val}'")
        if len(matched_fields) > 15:
            print(f"   ... and {len(matched_fields) - 15} more")
    
    print(f"\n⚠️  No vessel field match: {len(unmatched_fields)}")
    if unmatched_fields:
        print("   These will use random data:")
        for ph in unmatched_fields[:15]:
            print(f"   - '{ph}'")
        if len(unmatched_fields) > 15:
            print(f"   ... and {len(unmatched_fields) - 15} more")
    
    return matched_fields, unmatched_fields

def test_full_document_generation(template_name, vessel_imo="TEST001"):
    """Test full document generation via API"""
    print("\n" + "=" * 80)
    print("TEST 5: Full Document Generation (API Test)")
    print("=" * 80)
    
    api_url = os.getenv('API_URL', 'http://localhost:8000')
    
    try:
        print(f"Testing API at: {api_url}")
        response = requests.post(
            f"{api_url}/generate-document",
            json={
                "template_name": template_name,
                "vessel_imo": vessel_imo
            },
            timeout=30
        )
        
        if response.status_code == 200:
            print("✅ Document generated successfully!")
            content_type = response.headers.get('Content-Type', '')
            content_length = len(response.content)
            print(f"   Content-Type: {content_type}")
            print(f"   Size: {content_length} bytes")
            
            # Save test file
            output_file = f"test_output_{template_name.replace('.docx', '')}_{vessel_imo}.pdf"
            with open(output_file, 'wb') as f:
                f.write(response.content)
            print(f"   Saved to: {output_file}")
        else:
            print(f"❌ API Error: {response.status_code}")
            try:
                error_data = response.json()
                print(f"   Error: {error_data.get('detail', 'Unknown error')}")
            except:
                print(f"   Response: {response.text[:200]}")
    except requests.exceptions.ConnectionError:
        print(f"❌ Cannot connect to API at {api_url}")
        print("   Make sure the API is running: uvicorn main:app --host 0.0.0.0 --port 8000")
    except Exception as e:
        print(f"❌ Error: {e}")

def main():
    """Run all tests"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Test placeholder replacement system')
    parser.add_argument('template', help='Template name (e.g., "ICPO TEMPLATE.docx")')
    parser.add_argument('--vessel-imo', default='TEST001', help='Vessel IMO to test with')
    parser.add_argument('--api-url', help='API URL (default: http://localhost:8000)')
    
    args = parser.parse_args()
    
    if args.api_url:
        os.environ['API_URL'] = args.api_url
    
    template_name = normalize_template_name(args.template, with_extension=True, for_key=False)
    
    print("\n" + "=" * 80)
    print("PLACEHOLDER REPLACEMENT DIAGNOSTIC TEST")
    print("=" * 80)
    print(f"Template: {template_name}")
    print(f"Vessel IMO: {args.vessel_imo}")
    print("=" * 80 + "\n")
    
    # Run tests
    placeholders = test_placeholder_extraction(template_name)
    if not placeholders:
        print("\n❌ No placeholders found. Cannot continue tests.")
        return
    
    cms_settings = test_cms_settings_loading(template_name)
    matched, unmatched = test_placeholder_matching(placeholders, cms_settings)
    vessel_matched, vessel_unmatched = test_vessel_data_matching(placeholders, args.vessel_imo)
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total placeholders extracted: {len(placeholders)}")
    print(f"✅ Matched with CMS settings: {len(matched)}")
    print(f"⚠️  Unmatched (will use intelligent/random): {len(unmatched)}")
    print(f"✅ Can match to vessel fields: {len(vessel_matched)}")
    print(f"⚠️  Cannot match to vessel fields: {len(vessel_unmatched)}")
    print("=" * 80)
    
    # Test API if requested
    if args.api_url or os.getenv('API_URL'):
        test_full_document_generation(template_name, args.vessel_imo)

if __name__ == '__main__':
    main()


#!/usr/bin/env python3
"""
Test script for template deletion functionality
Tests all aspects of template deletion to identify issues
"""

import os
import sys
import json
import requests
import tempfile
from pathlib import Path

# Add parent directory to path to import main
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, 'templates')
STORAGE_DIR = os.path.join(BASE_DIR, 'storage')
DELETED_TEMPLATES_PATH = os.path.join(STORAGE_DIR, 'deleted_templates.json')

def print_section(title):
    """Print a section header"""
    print("\n" + "="*60)
    print(f"  {title}")
    print("="*60)

def check_file_exists(filepath):
    """Check if a file exists"""
    exists = os.path.exists(filepath)
    print(f"  {'✓' if exists else '✗'} {filepath}: {exists}")
    if exists:
        size = os.path.getsize(filepath)
        print(f"    Size: {size} bytes")
    return exists

def check_json_file(filepath, key=None):
    """Check JSON file and its contents"""
    print(f"\n  Checking: {filepath}")
    if not os.path.exists(filepath):
        print(f"    ✗ File does not exist")
        return None
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if key:
            value = data.get(key)
            print(f"    ✓ File exists")
            print(f"    {key}: {value}")
            return value
        else:
            print(f"    ✓ File exists")
            print(f"    Content: {json.dumps(data, indent=4)}")
            return data
    except Exception as e:
        print(f"    ✗ Error reading file: {e}")
        return None

def list_templates_in_dir():
    """List all templates in templates directory"""
    print("\n  Templates in templates/ directory:")
    if not os.path.exists(TEMPLATES_DIR):
        print(f"    ✗ Directory does not exist: {TEMPLATES_DIR}")
        return []
    
    templates = []
    for filename in os.listdir(TEMPLATES_DIR):
        if filename.lower().endswith('.docx'):
            filepath = os.path.join(TEMPLATES_DIR, filename)
            size = os.path.getsize(filepath)
            templates.append(filename)
            print(f"    - {filename} ({size} bytes)")
    
    if not templates:
        print("    (No .docx files found)")
    
    return templates

def test_api_delete(template_name, api_url="http://localhost:8000", session_cookie=None):
    """Test API delete endpoint"""
    print(f"\n  Testing API DELETE: /templates/{template_name}")
    url = f"{api_url}/templates/{template_name}"
    
    headers = {
        'Content-Type': 'application/json'
    }
    
    if session_cookie:
        headers['Cookie'] = session_cookie
    
    try:
        response = requests.delete(url, headers=headers)
        print(f"    Status Code: {response.status_code}")
        print(f"    Response: {response.text}")
        
        if response.status_code == 200:
            try:
                data = response.json()
                print(f"    Success: {data.get('success', False)}")
                print(f"    Message: {data.get('message', '')}")
                if 'warnings' in data:
                    print(f"    Warnings: {data['warnings']}")
            except:
                pass
            return True
        else:
            return False
    except Exception as e:
        print(f"    ✗ Error: {e}")
        return False

def test_api_get_templates(api_url="http://localhost:8000"):
    """Test API get templates endpoint"""
    print(f"\n  Testing API GET: /templates")
    url = f"{api_url}/templates"
    
    try:
        response = requests.get(url)
        print(f"    Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            templates = data.get('templates', [])
            print(f"    Templates count: {len(templates)}")
            
            # Show first few templates
            for i, template in enumerate(templates[:5]):
                name = template.get('name') or template.get('file_name') or template.get('id', 'Unknown')
                print(f"      {i+1}. {name}")
            
            return templates
        else:
            print(f"    ✗ Error: {response.text}")
            return []
    except Exception as e:
        print(f"    ✗ Error: {e}")
        return []

def main():
    """Main test function"""
    print("\n" + "="*60)
    print("  TEMPLATE DELETION TEST SCRIPT")
    print("="*60)
    
    # Test 1: Check directories
    print_section("1. Checking Directories")
    os.makedirs(TEMPLATES_DIR, exist_ok=True)
    os.makedirs(STORAGE_DIR, exist_ok=True)
    print(f"  ✓ TEMPLATES_DIR: {TEMPLATES_DIR}")
    print(f"  ✓ STORAGE_DIR: {STORAGE_DIR}")
    
    # Test 2: Check deleted_templates.json
    print_section("2. Checking deleted_templates.json")
    deleted_templates = check_json_file(DELETED_TEMPLATES_PATH)
    if deleted_templates:
        deleted_list = deleted_templates.get('deleted_templates', [])
        print(f"\n  Deleted templates count: {len(deleted_list)}")
        for template in deleted_list[:10]:
            print(f"    - {template}")
    else:
        print("\n  ✗ deleted_templates.json does not exist or is invalid")
    
    # Test 3: List templates in directory
    print_section("3. Templates in templates/ directory")
    templates = list_templates_in_dir()
    
    # Test 4: Check other storage files
    print_section("4. Checking other storage files")
    check_file_exists(os.path.join(STORAGE_DIR, 'template_metadata.json'))
    check_file_exists(os.path.join(STORAGE_DIR, 'placeholder_settings.json'))
    check_file_exists(os.path.join(STORAGE_DIR, 'plans.json'))
    
    # Test 5: Test API (if available)
    print_section("5. Testing API Endpoints")
    api_url = os.getenv('API_URL', 'http://localhost:8000')
    print(f"  API URL: {api_url}")
    
    # Test health endpoint
    try:
        response = requests.get(f"{api_url}/health", timeout=2)
        if response.status_code == 200:
            print(f"  ✓ API is running")
            
            # Get templates from API
            api_templates = test_api_get_templates(api_url)
            
            # Compare with local files
            print_section("6. Comparing Local vs API Templates")
            local_names = {t.lower() for t in templates}
            api_names = {t.get('name', '').lower() or t.get('file_name', '').lower() for t in api_templates}
            
            print(f"\n  Local templates: {len(local_names)}")
            print(f"  API templates: {len(api_names)}")
            
            # Find discrepancies
            only_local = local_names - api_names
            only_api = api_names - local_names
            
            if only_local:
                print(f"\n  Templates only in local (not in API):")
                for name in only_local:
                    print(f"    - {name}")
            
            if only_api:
                print(f"\n  Templates only in API (not in local):")
                for name in list(only_api)[:10]:
                    print(f"    - {name}")
        else:
            print(f"  ✗ API health check failed: {response.status_code}")
    except Exception as e:
        print(f"  ✗ API not available: {e}")
        print(f"    (This is OK if API is not running)")
    
    # Test 6: Check if deleted templates are in local filesystem
    print_section("7. Checking for Deleted Templates in Filesystem")
    if deleted_templates:
        deleted_list = deleted_templates.get('deleted_templates', [])
        for deleted_name in deleted_list:
            if not deleted_name:
                continue
            # Check multiple variations
            variations = [
                deleted_name,
                deleted_name.lower(),
                deleted_name.upper(),
            ]
            # Add .docx if not present
            if not deleted_name.lower().endswith('.docx'):
                variations.append(f"{deleted_name}.docx")
                variations.append(f"{deleted_name.lower()}.docx")
                variations.append(f"{deleted_name.upper()}.docx")
            
            found = False
            for var in variations:
                filepath = os.path.join(TEMPLATES_DIR, var)
                if os.path.exists(filepath):
                    print(f"  ⚠ WARNING: Deleted template '{deleted_name}' still exists as '{var}'")
                    found = True
            
            if not found:
                print(f"  ✓ Deleted template '{deleted_name}' not found in filesystem")
    
    # Summary
    print_section("SUMMARY")
    print("\n  Recommendations:")
    print("    1. If deleted_templates.json doesn't exist, it will be created on first deletion")
    print("    2. If templates are marked as deleted but still in filesystem, they should be removed")
    print("    3. Check API logs for deletion errors")
    print("    4. Ensure proper permissions on storage/ and templates/ directories")
    
    print("\n" + "="*60)
    print("  Test completed!")
    print("="*60 + "\n")

if __name__ == "__main__":
    main()


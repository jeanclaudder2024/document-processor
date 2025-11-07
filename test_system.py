"""
System Test Script - Verify all endpoints and functionality
"""
import requests
import json
import os
from pathlib import Path

BASE_URL = "http://localhost:8000"
CMS_URL = "http://127.0.0.1:8080"

def test_endpoint(name, method, url, data=None, files=None, session=None, expected_status=200):
    """Test an API endpoint"""
    try:
        if method == "GET":
            response = session.get(url) if session else requests.get(url)
        elif method == "POST":
            if files:
                response = session.post(url, files=files) if session else requests.post(url, files=files)
            else:
                response = session.post(url, json=data) if session else requests.post(url, json=data)
        elif method == "DELETE":
            response = session.delete(url) if session else requests.delete(url)
        
        status = response.status_code
        success = status == expected_status
        
        print(f"{'✓' if success else '✗'} {name}: {status}")
        
        if not success:
            print(f"  Expected {expected_status}, got {status}")
            try:
                print(f"  Error: {response.json()}")
            except:
                print(f"  Response: {response.text[:100]}")
        
        return success, response
    except Exception as e:
        print(f"✗ {name}: ERROR - {str(e)}")
        return False, None

def main():
    print("=" * 60)
    print("SYSTEM TEST - Document Processor API & CMS")
    print("=" * 60)
    
    results = {"passed": 0, "failed": 0}
    session = requests.Session()
    
    # Test 1: Health Check
    print("\n[1] Testing Health & Basic Endpoints")
    print("-" * 60)
    success, _ = test_endpoint("GET /health", "GET", f"{BASE_URL}/health")
    if success:
        results["passed"] += 1
    else:
        results["failed"] += 1
    
    success, _ = test_endpoint("GET /", "GET", f"{BASE_URL}/")
    if success:
        results["passed"] += 1
    else:
        results["failed"] += 1
    
    # Test 2: Authentication
    print("\n[2] Testing Authentication")
    print("-" * 60)
    success, resp = test_endpoint("POST /auth/login", "POST", f"{BASE_URL}/auth/login", 
                                   data={"username": "admin", "password": "admin123"}, 
                                   session=session)
    if success:
        results["passed"] += 1
    else:
        results["failed"] += 1
    
    if success:
        success, _ = test_endpoint("GET /auth/me", "GET", f"{BASE_URL}/auth/me", session=session)
        if success:
            results["passed"] += 1
        else:
            results["failed"] += 1
    else:
        print("  ⚠ Skipping /auth/me test (login failed)")
        results["failed"] += 1
    
    # Test 3: Templates API
    print("\n[3] Testing Templates API")
    print("-" * 60)
    success, resp = test_endpoint("GET /templates", "GET", f"{BASE_URL}/templates")
    if success:
        results["passed"] += 1
        if resp:
            data = resp.json()
            templates = data.get("templates", [])
            print(f"  Found {len(templates)} templates")
    else:
        results["failed"] += 1
    
    # Test 4: Plans API
    print("\n[4] Testing Plans API")
    print("-" * 60)
    success, resp = test_endpoint("GET /plans", "GET", f"{BASE_URL}/plans")
    if success:
        results["passed"] += 1
        if resp:
            data = resp.json()
            plans = data.get("plans", {})
            print(f"  Found {len(plans)} plans: {', '.join(plans.keys())}")
    else:
        results["failed"] += 1
    
    success, _ = test_endpoint("POST /check-download-permission", "POST", 
                               f"{BASE_URL}/check-download-permission",
                               data={"user_id": "basic", "template_name": "test.docx"},
                               session=session)
    if success:
        results["passed"] += 1
    else:
        results["failed"] += 1
    
    # Test 5: Placeholder Settings API
    print("\n[5] Testing Placeholder Settings API")
    print("-" * 60)
    success, _ = test_endpoint("GET /placeholder-settings", "GET", 
                                f"{BASE_URL}/placeholder-settings")
    if success:
        results["passed"] += 1
    else:
        results["failed"] += 1
    
    # Test 6: Data Sources API
    print("\n[6] Testing Data Sources API")
    print("-" * 60)
    success, resp = test_endpoint("GET /data/all", "GET", f"{BASE_URL}/data/all")
    if success:
        results["passed"] += 1
        if resp:
            data = resp.json()
            sources = data.get("data_sources", {})
            print(f"  Data sources: {', '.join(sources.keys())}")
    else:
        results["failed"] += 1
    
    # Test 7: Vessels API
    print("\n[7] Testing Vessels API")
    print("-" * 60)
    success, resp = test_endpoint("GET /vessels", "GET", f"{BASE_URL}/vessels")
    if success:
        results["passed"] += 1
        if resp:
            data = resp.json()
            vessels = data.get("vessels", [])
            print(f"  Found {len(vessels)} vessels")
    else:
        results["failed"] += 1
    
    # Test 8: Storage Files
    print("\n[8] Checking Storage Files")
    print("-" * 60)
    storage_dir = Path("storage")
    files_to_check = [
        "placeholder_settings.json",
        "plans.json",
        "users.json"
    ]
    
    for filename in files_to_check:
        filepath = storage_dir / filename
        if filepath.exists():
            print(f"✓ {filename} exists")
            results["passed"] += 1
            try:
                with open(filepath, 'r') as f:
                    data = json.load(f)
                    print(f"  Valid JSON with {len(data)} top-level keys/items")
            except Exception as e:
                print(f"  ⚠ JSON error: {e}")
                results["failed"] += 1
        else:
            print(f"✗ {filename} missing")
            results["failed"] += 1
    
    # Test 9: Templates Directory
    print("\n[9] Checking Templates Directory")
    print("-" * 60)
    templates_dir = Path("templates")
    if templates_dir.exists():
        docx_files = list(templates_dir.glob("*.docx"))
        print(f"✓ Templates directory exists with {len(docx_files)} .docx files")
        results["passed"] += 1
    else:
        print("✗ Templates directory missing")
        results["failed"] += 1
    
    # Test 10: CMS Frontend (if server running)
    print("\n[10] Testing CMS Frontend")
    print("-" * 60)
    try:
        resp = requests.get(f"{CMS_URL}/index.html", timeout=2)
        if resp.status_code == 200:
            print(f"✓ CMS frontend accessible at {CMS_URL}")
            results["passed"] += 1
        else:
            print(f"✗ CMS returned status {resp.status_code}")
            results["failed"] += 1
    except requests.exceptions.ConnectionError:
        print(f"⚠ CMS frontend not running at {CMS_URL}")
        print("  Start it with: cd cms && python -m http.server 8080 --bind 127.0.0.1")
        # Don't count as failure, just info
    except Exception as e:
        print(f"✗ CMS check error: {e}")
        results["failed"] += 1
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"Passed: {results['passed']}")
    print(f"Failed: {results['failed']}")
    print(f"Total: {results['passed'] + results['failed']}")
    print("=" * 60)
    
    if results['failed'] == 0:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print(f"\n⚠️  {results['failed']} test(s) failed")
        return 1

if __name__ == "__main__":
    exit(main())


"""
Test script for ID-based fetching system
"""

from id_based_fetcher import (
    identify_prefix, normalize_placeholder, PREFIX_TO_TABLE,
    get_placeholder_value, normalize_replacement_value
)

def test_prefix_identification():
    """Test prefix identification"""
    print("=" * 80)
    print("TESTING PREFIX IDENTIFICATION")
    print("=" * 80)
    
    test_cases = [
        ("{{buyer_name}}", "buyer_"),
        ("{{buyer_bank_swift}}", "buyer_bank_"),
        ("{{seller_email}}", "seller_"),
        ("{{vessel_name}}", "vessel_"),
        ("{{departure_port_name}}", "departure_port_"),
        ("{{destination_port_country}}", "destination_port_"),
        ("{{product_name}}", "product_"),
        ("{{refinery_location}}", "refinery_"),
        ("{{broker_phone}}", "broker_"),
        ("{{company_address}}", "company_"),
    ]
    
    passed = 0
    failed = 0
    
    for placeholder, expected_prefix in test_cases:
        prefix = identify_prefix(placeholder)
        normalized = normalize_placeholder(placeholder)
        table = PREFIX_TO_TABLE.get(prefix) if prefix else None
        
        if prefix == expected_prefix:
            print(f"[OK] {placeholder:30} -> prefix: {prefix:20} -> table: {table}")
            passed += 1
        else:
            print(f"[FAIL] {placeholder:30} -> Expected: {expected_prefix}, Got: {prefix}")
            failed += 1
    
    print("=" * 80)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 80)
    return failed == 0

def test_normalization():
    """Test placeholder normalization"""
    print("\n" + "=" * 80)
    print("TESTING PLACEHOLDER NORMALIZATION")
    print("=" * 80)
    
    test_cases = [
        ("{{Buyer Bank Swift}}", "buyerbankswift"),
        ("{{buyer_bank_swift}}", "buyerbankswift"),
        ("{{buyer-bank-swift}}", "buyerbankswift"),
        ("{Vessel Name}", "vesselname"),
        ("[[Product Type]]", "producttype"),
        ("%Refinery Capacity%", "refinerycapacity"),
        ("<Seller Email>", "selleremail"),
    ]
    
    passed = 0
    failed = 0
    
    for placeholder, expected_normalized in test_cases:
        normalized = normalize_placeholder(placeholder)
        if normalized == expected_normalized:
            print(f"[OK] {placeholder:30} -> {normalized}")
            passed += 1
        else:
            print(f"[FAIL] {placeholder:30} -> Expected: {expected_normalized}, Got: {normalized}")
            failed += 1
    
    print("=" * 80)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 80)
    return failed == 0

def test_prefix_table_mapping():
    """Test prefix to table mapping"""
    print("\n" + "=" * 80)
    print("TESTING PREFIX TO TABLE MAPPING")
    print("=" * 80)
    
    expected_mappings = {
        'vessel_': 'vessels',
        'buyer_': 'buyer_companies',
        'seller_': 'seller_companies',
        'buyer_bank_': 'buyer_company_bank_accounts',
        'seller_bank_': 'seller_company_bank_accounts',
        'product_': 'oil_products',
        'refinery_': 'refineries',
        'broker_': 'broker_profiles',
        'port_': 'ports',
        'departure_port_': 'ports',
        'destination_port_': 'ports',
        'company_': 'companies',
    }
    
    passed = 0
    failed = 0
    
    for prefix, expected_table in expected_mappings.items():
        actual_table = PREFIX_TO_TABLE.get(prefix)
        if actual_table == expected_table:
            print(f"[OK] {prefix:25} -> {actual_table}")
            passed += 1
        else:
            print(f"[FAIL] {prefix:25} -> Expected: {expected_table}, Got: {actual_table}")
            failed += 1
    
    print("=" * 80)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 80)
    return failed == 0

if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("ID-BASED FETCHING SYSTEM - TEST SUITE")
    print("=" * 80)
    
    results = []
    results.append(("Prefix Identification", test_prefix_identification()))
    results.append(("Placeholder Normalization", test_normalization()))
    results.append(("Prefix to Table Mapping", test_prefix_table_mapping()))
    
    print("\n" + "=" * 80)
    print("FINAL RESULTS")
    print("=" * 80)
    
    for test_name, passed in results:
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{status}: {test_name}")
    
    all_passed = all(result[1] for result in results)
    print("=" * 80)
    if all_passed:
        print("[SUCCESS] ALL TESTS PASSED!")
    else:
        print("[WARNING] SOME TESTS FAILED")
    print("=" * 80)

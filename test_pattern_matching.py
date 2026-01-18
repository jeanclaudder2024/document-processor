#!/usr/bin/env python3
"""
Quick test to verify placeholder pattern matching works correctly
"""
import re

def _build_placeholder_pattern(placeholder: str):
    """Test version of pattern building"""
    if not placeholder:
        return []
    
    normalized = placeholder.strip()
    normalized = re.sub(r'^[{\[<%#_]+|[}\])%>#_]+$', '', normalized).strip()
    if not normalized:
        return []
    
    pattern_parts = []
    for char in normalized:
        if char in {' ', '\u00A0', '_', '-'}:
            pattern_parts.append(r'[\s_\-]+')
        else:
            pattern_parts.append(re.escape(char))
    
    inner_pattern = ''.join(pattern_parts)
    
    # Build patterns - need to escape braces properly
    double_brace = r"\{\{" + r"\s*" + inner_pattern + r"\s*" + r"\}\}"
    single_brace = r"\{" + r"\s*" + inner_pattern + r"\s*" + r"\}"
    
    wrappers = [
        double_brace,  # {{placeholder}} - DOUBLE BRACES
        single_brace,  # {placeholder} - MOST COMMON
    ]
    
    return [re.compile(wrap, re.IGNORECASE) for wrap in wrappers]

# Test cases
test_cases = [
    ("deadweight", "{deadweight}", True),
    ("deadweight", "{{deadweight}}", True),
    ("owner", "{owner}", True),
    ("owner", "{{owner}}", True),
    ("imo_number", "{imo_number}", True),
    ("imo_number", "{{imo_number}}", True),
    ("vessel_owner", "{vessel_owner}", True),
    ("vessel_owner", "{{vessel_owner}}", True),
]

print("Testing placeholder pattern matching:")
print("=" * 60)

all_passed = True
for placeholder, text_to_match, should_match in test_cases:
    patterns = _build_placeholder_pattern(placeholder)
    matched = False
    for pattern in patterns:
        if pattern.search(text_to_match):
            matched = True
            break
    
    status = "✅ PASS" if matched == should_match else "❌ FAIL"
    if matched != should_match:
        all_passed = False
    
    print(f"{status}: '{placeholder}' pattern matching '{text_to_match}' -> {matched} (expected: {should_match})")
    if patterns:
        print(f"   Patterns: {[p.pattern for p in patterns]}")
    print()

print("=" * 60)
if all_passed:
    print("✅ All tests passed!")
else:
    print("❌ Some tests failed!")


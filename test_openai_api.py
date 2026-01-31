#!/usr/bin/env python3
"""Test OpenAI API connectivity and functionality"""

import os
import sys
from dotenv import load_dotenv
from supabase import create_client

# Load environment
load_dotenv()

print("=" * 60)
print("  OpenAI API Test")
print("=" * 60)

# Check Supabase connection
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://ozjhdxvwqbzcvcywhwjg.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

print("\n1. Checking for OpenAI API key...")
print("-" * 60)

# Try to get key from Supabase
openai_key_from_supabase = None
try:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    response = supabase.table('system_settings').select('setting_value').eq('setting_key', 'openai_api_key').limit(1).execute()
    
    if response.data and len(response.data) > 0:
        openai_key_from_supabase = response.data[0].get('setting_value', '').strip()
        if openai_key_from_supabase:
            print(f"✅ Found OpenAI key in Supabase system_settings")
            print(f"   Key starts with: {openai_key_from_supabase[:10]}...")
        else:
            print("❌ OpenAI key in Supabase is empty")
    else:
        print("❌ No OpenAI key in Supabase system_settings table")
        print("   Row with setting_key='openai_api_key' doesn't exist")
except Exception as e:
    print(f"❌ Error accessing Supabase: {e}")

# Try environment variable
openai_key_from_env = os.getenv("OPENAI_API_KEY", "").strip()
if openai_key_from_env:
    print(f"✅ Found OpenAI key in environment variable")
    print(f"   Key starts with: {openai_key_from_env[:10]}...")
else:
    print("❌ No OpenAI key in environment variable")

# Determine which key to use
OPENAI_API_KEY = openai_key_from_supabase or openai_key_from_env

if not OPENAI_API_KEY:
    print("\n" + "=" * 60)
    print("❌ NO OPENAI API KEY CONFIGURED")
    print("=" * 60)
    print("\nThe system will use rule-based mapping (less accurate).")
    print("\nTo add OpenAI key:")
    print("1. Get key from: https://platform.openai.com/api-keys")
    print("2. Add to Supabase system_settings:")
    print("   INSERT INTO system_settings (setting_key, setting_value)")
    print("   VALUES ('openai_api_key', 'sk-proj-...');")
    print("\n3. Or add to .env file:")
    print("   echo 'OPENAI_API_KEY=sk-proj-...' >> .env")
    sys.exit(1)

# Test OpenAI API
print("\n2. Testing OpenAI API connection...")
print("-" * 60)

try:
    from openai import OpenAI
    
    client = OpenAI(api_key=OPENAI_API_KEY)
    
    # Test with a simple completion
    print("Sending test request to OpenAI...")
    response = client.chat.completions.create(
        model='gpt-4o-mini',
        messages=[
            {'role': 'user', 'content': 'Say "OpenAI API is working!" in exactly 5 words.'}
        ],
        max_tokens=20,
        temperature=0.1
    )
    
    result = response.choices[0].message.content.strip()
    print(f"✅ OpenAI API Response: {result}")
    print(f"✅ Model used: {response.model}")
    print(f"✅ Tokens used: {response.usage.total_tokens}")
    
    print("\n" + "=" * 60)
    print("✅ SUCCESS: OpenAI API is working correctly!")
    print("=" * 60)
    print("\nThe system will use AI-powered placeholder mapping.")
    print("This provides the most accurate mappings.")
    
except ImportError:
    print("❌ OpenAI Python package not installed")
    print("   Run: pip install openai")
    sys.exit(1)
except Exception as e:
    print(f"❌ OpenAI API Error: {e}")
    print("\nPossible causes:")
    print("- Invalid API key")
    print("- Network connectivity issue")
    print("- API key doesn't have credits/quota")
    print("\nCheck your OpenAI account at: https://platform.openai.com/")
    sys.exit(1)

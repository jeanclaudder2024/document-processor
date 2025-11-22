#!/bin/bash

# Test script to manually save plan permissions
# This will help us see what's happening

PLAN_TIER="basic"
PLAN_ID="220bfaf1-9e41-4f11-a965-9f1c320986c6"

# Get a template ID from the debug endpoint
TEMPLATE_ID=$(curl -s http://localhost:8000/debug-plan-permissions | python3 -c "import sys, json; data = json.load(sys.stdin); templates = data['data']['templates']; print(list(templates.keys())[0] if templates else '')")

if [ -z "$TEMPLATE_ID" ]; then
    echo "❌ Could not get template ID from debug endpoint"
    exit 1
fi

echo "📋 Testing save plan with:"
echo "   Plan Tier: $PLAN_TIER"
echo "   Plan ID: $PLAN_ID"
echo "   Template ID: $TEMPLATE_ID"
echo ""

# Test payload - send template IDs
PAYLOAD=$(cat <<EOF
{
    "plan_tier": "$PLAN_TIER",
    "can_download": {
        "template_ids": ["$TEMPLATE_ID"],
        "template_names": []
    },
    "max_downloads_per_month": 10
}
EOF
)

echo "📤 Sending request:"
echo "$PAYLOAD" | python3 -m json.tool
echo ""

# Send request
RESPONSE=$(curl -s -X POST http://localhost:8000/update-plan \
    -H "Content-Type: application/json" \
    -d "$PAYLOAD")

echo "📥 Response:"
echo "$RESPONSE" | python3 -m json.tool
echo ""

# Check permissions after save
echo "🔍 Checking permissions after save:"
curl -s http://localhost:8000/debug-plan-permissions | python3 -c "
import sys, json
data = json.load(sys.stdin)
basic = data['data']['permissions']['basic']
print(f\"Basic plan permissions count: {basic['count']}\")
if basic['count'] > 0:
    print(f\"✅ Permissions saved successfully!\")
    for perm in basic['permissions'][:3]:
        print(f\"   - Template ID: {perm.get('template_id', 'N/A')}\")
else:
    print(f\"❌ No permissions found - save failed!\")
"


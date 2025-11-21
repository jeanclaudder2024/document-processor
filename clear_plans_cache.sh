#!/bin/bash
# Clear plans.json cache file
# This script removes the plans.json cache file that might be causing issues

STORAGE_DIR="storage"
PLANS_FILE="$STORAGE_DIR/plans.json"

echo "=========================================="
echo "Clearing plans.json cache file"
echo "=========================================="

if [ -f "$PLANS_FILE" ]; then
    echo "Found plans.json file at: $PLANS_FILE"
    echo "Backing up to: ${PLANS_FILE}.backup"
    cp "$PLANS_FILE" "${PLANS_FILE}.backup" 2>/dev/null || true
    
    echo "Removing plans.json cache file..."
    rm -f "$PLANS_FILE"
    echo "✅ plans.json cache file cleared!"
else
    echo "ℹ️  plans.json file not found (already cleared or doesn't exist)"
fi

echo ""
echo "=========================================="
echo "Cache cleared successfully!"
echo "=========================================="
echo ""
echo "The system will now use database data only."
echo "Restart the backend service to apply changes:"
echo "  sudo systemctl restart document-processor"


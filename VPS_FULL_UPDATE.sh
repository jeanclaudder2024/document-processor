#!/bin/bash
# =============================================================================
# VPS Full Update Script for PetroDealHub Document Processor
# Run this on your VPS: bash VPS_FULL_UPDATE.sh
# =============================================================================

set -e

echo "=============================================="
echo "🚀 PetroDealHub Document Processor - Full Update"
echo "=============================================="

# Configuration
PROJECT_DIR="/opt/petrodealhub"
DOC_PROCESSOR_DIR="$PROJECT_DIR/document-processor"
PM2_PROCESS_NAME="python-api"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo ""
echo "📁 Step 1: Going to project directory..."
cd "$PROJECT_DIR"
echo "   Current directory: $(pwd)"

echo ""
echo "📥 Step 2: Pulling latest code from git..."
git pull origin main || echo "⚠️ Main repo pull failed, continuing..."

echo ""
echo "📥 Step 3: Updating document-processor submodule..."
cd "$DOC_PROCESSOR_DIR"
git pull origin master || echo "⚠️ Submodule pull failed, continuing..."

echo ""
echo "🛑 Step 4: Stopping PM2 process..."
pm2 stop $PM2_PROCESS_NAME 2>/dev/null || echo "   Process not running, skipping..."

echo ""
echo "🔪 Step 5: Killing any process on port 8000..."
sudo fuser -k 8000/tcp 2>/dev/null || echo "   No process on port 8000"

echo ""
echo "📦 Step 6: Setting up Python virtual environment..."
if [ ! -d "venv" ]; then
    echo "   Creating virtual environment..."
    python3 -m venv venv
fi

echo ""
echo "📦 Step 7: Installing Python dependencies..."
source venv/bin/activate

# Upgrade pip first
pip install --upgrade pip

# Install all required packages
# Note: python-docx==0.8.11 is required for compatibility (newer versions have breaking changes)
pip install --upgrade \
    fastapi \
    uvicorn \
    python-multipart \
    "python-docx==0.8.11" \
    supabase \
    python-dotenv \
    httpx \
    openai \
    docx2pdf \
    Pillow \
    aiofiles \
    pydantic

echo ""
echo "✅ Step 8: Verifying OpenAI installation..."
pip list | grep -i openai || echo "❌ OpenAI not found!"

deactivate

echo ""
echo "📝 Step 9: Setting up .env file..."
# Backup existing .env
if [ -f ".env" ]; then
    cp .env .env.backup.$(date +%Y%m%d_%H%M%S)
    echo "   Backed up existing .env"
fi

# Check if OPENAI_API_KEY exists in .env
if grep -q "OPENAI_API_KEY" .env 2>/dev/null; then
    echo "   OPENAI_API_KEY already exists in .env"
else
    echo ""
    echo "⚠️  OPENAI_API_KEY not found in .env!"
    echo "   Please add it manually:"
    echo "   nano .env"
    echo "   Add line: OPENAI_API_KEY=your-api-key-here"
fi

# Clean up .env file (remove duplicate lines and corrupted data)
echo ""
echo "🧹 Step 10: Cleaning .env file (removing duplicates/corruption)..."
# Extract valid lines from existing .env
SUPABASE_URL=$(grep "^SUPABASE_URL=" .env 2>/dev/null | head -1)
SUPABASE_KEY=$(grep "^SUPABASE_KEY=" .env 2>/dev/null | head -1)
OPENAI_KEY=$(grep "^OPENAI_API_KEY=" .env 2>/dev/null | tail -1)

# Create clean .env
cat > .env.clean << ENVEOF
${SUPABASE_URL:-SUPABASE_URL=https://ozjhdxvwqbzcvcywhwjg.supabase.co}
${SUPABASE_KEY:-SUPABASE_KEY=your-supabase-key-here}
FASTAPI_HOST=0.0.0.0
FASTAPI_PORT=8000
${OPENAI_KEY:-OPENAI_API_KEY=your-openai-key-here}
ENVEOF
mv .env.clean .env
echo "   .env file cleaned"

echo ""
echo "📄 Step 11: Current .env contents:"
cat .env

echo ""
echo "🔧 Step 12: Installing LibreOffice for PDF conversion..."
if command -v libreoffice &> /dev/null; then
    echo "   LibreOffice already installed"
else
    echo "   Installing LibreOffice..."
    sudo apt-get update -y
    sudo apt-get install -y libreoffice-core libreoffice-writer || echo "⚠️ LibreOffice installation failed"
fi

echo ""
echo "🚀 Step 13: Starting PM2 process..."
pm2 start $PM2_PROCESS_NAME 2>/dev/null || {
    echo "   Process doesn't exist, creating new one..."
    pm2 start main.py --name $PM2_PROCESS_NAME --interpreter ./venv/bin/python
}

echo ""
echo "💾 Step 14: Saving PM2 configuration..."
pm2 save

echo ""
echo "⏳ Waiting 5 seconds for service to start..."
sleep 5

echo ""
echo "📊 Step 15: Checking PM2 status..."
pm2 list

echo ""
echo "📋 Step 16: Checking logs..."
pm2 logs $PM2_PROCESS_NAME --lines 25 --nostream

echo ""
echo "=============================================="
echo "✅ UPDATE COMPLETE!"
echo "=============================================="
echo ""
echo "Check for these success messages in the logs above:"
echo "  ✅ 'OpenAI client initialized successfully'"
echo "  ✅ 'Uvicorn running on http://0.0.0.0:8000'"
echo ""
echo "If you see 'OpenAI library not installed', run:"
echo "  source venv/bin/activate && pip install openai && deactivate"
echo "  pm2 restart $PM2_PROCESS_NAME"
echo ""
echo "=============================================="

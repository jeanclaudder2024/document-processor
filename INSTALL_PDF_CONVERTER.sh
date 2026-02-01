#!/bin/bash
# =============================================================================
# Install PDF Converter (LibreOffice) on Ubuntu/Debian VPS
# =============================================================================
# This script installs LibreOffice for DOCX to PDF conversion
# Run this on your VPS with: bash INSTALL_PDF_CONVERTER.sh
# =============================================================================

set -e

echo "=============================================="
echo "Installing PDF Converter (LibreOffice)"
echo "=============================================="

# Update package list
echo "📦 Updating package list..."
sudo apt-get update -y

# Install LibreOffice (headless version for server)
echo "📦 Installing LibreOffice (headless)..."
sudo apt-get install -y libreoffice-core libreoffice-writer

# Alternative: Install only the minimal packages needed
# sudo apt-get install -y libreoffice-writer-nogui

# Install unoconv as backup
echo "📦 Installing unoconv (backup converter)..."
sudo apt-get install -y unoconv || echo "⚠️ unoconv installation failed (optional)"

# Verify installation
echo ""
echo "=============================================="
echo "Verifying Installation"
echo "=============================================="

# Check LibreOffice
if command -v libreoffice &> /dev/null; then
    echo "✅ LibreOffice installed:"
    libreoffice --version | head -1
else
    echo "❌ LibreOffice not found"
fi

# Check soffice
if command -v soffice &> /dev/null; then
    echo "✅ soffice command available"
else
    echo "⚠️ soffice command not in PATH"
fi

# Check unoconv
if command -v unoconv &> /dev/null; then
    echo "✅ unoconv installed"
else
    echo "⚠️ unoconv not installed (optional)"
fi

echo ""
echo "=============================================="
echo "Installation Complete!"
echo "=============================================="
echo ""
echo "Now restart your document processor service:"
echo "  sudo systemctl restart petrodealhub-cms"
echo "  # or"
echo "  pm2 restart document-processor"
echo ""
echo "Test PDF conversion by generating a document."
echo "=============================================="

@echo off
echo 🔐 SSL Certificate Generator for Document Processor
echo ==================================================
echo.
echo 📋 Prerequisites:
echo    pip install cryptography
echo.
echo 🎯 Target Server: 161.97.103.172:8443
echo ==================================================
echo.

echo 🔐 Generating SSL certificates for HTTPS...
echo.

python generate-ssl.py

echo.
echo 🎉 SSL setup complete!
echo 🚀 Run your API with: python main.py
echo 🌐 Your API will be available at: https://161.97.103.172:8443
echo.
pause



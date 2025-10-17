@echo off
echo 🚀 Document Processor HTTPS Setup
echo =================================
echo.

echo 📦 Installing required packages...
pip install -r requirements.txt

echo.
echo 🔐 Generating SSL certificates...
python generate-ssl.py

echo.
echo 🎉 Setup complete!
echo.
echo 📋 Next steps:
echo    1. Run: python main.py
echo    2. Your API will be available at: https://161.97.103.172:8443
echo    3. Browser will show security warning (click "Advanced" then "Proceed")
echo.
echo 🔧 Troubleshooting:
echo    - If port 8443 is blocked, check Windows Firewall
echo    - If SSL fails, check that key.pem and cert.pem exist
echo.
pause



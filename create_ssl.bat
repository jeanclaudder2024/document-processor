@echo off
echo 🔐 Creating SSL certificates for HTTPS...
echo.

echo 📝 Creating private key...
openssl genrsa -out key.pem 2048

echo 📜 Creating certificate...
openssl req -new -x509 -key key.pem -out cert.pem -days 365 -subj "/C=US/ST=State/L=City/O=Organization/CN=161.97.103.172"

echo.
echo ✅ SSL certificates created successfully!
echo 📁 Files created:
echo    - key.pem
echo    - cert.pem
echo.
echo 🚀 Your API can now run with HTTPS on port 8443!
echo.
pause


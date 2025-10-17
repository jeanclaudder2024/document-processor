"""
Simple SSL Certificate Generator for Document Processor
Creates self-signed certificates using Python's built-in libraries
"""
import os
from datetime import datetime, timedelta
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

def generate_cert():
    """Generate self-signed SSL certificates using Python's cryptography library"""
    try:
        print("🔐 Generating SSL certificates for HTTPS...")
        print("📝 Creating private key...")
        
        # Generate private key
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )

        print("📜 Creating self-signed certificate...")
        # Create self-signed certificate
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "CA"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, "Local"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Document Processor"),
            x509.NameAttribute(NameOID.COMMON_NAME, "161.97.103.172"),
        ])

        cert = x509.CertificateBuilder().subject_name(
            subject
        ).issuer_name(
            issuer
        ).public_key(
            private_key.public_key()
        ).serial_number(
            x509.random_serial_number()
        ).not_valid_before(
            datetime.utcnow()
        ).not_valid_after(
            datetime.utcnow() + timedelta(days=365)
        ).add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName("161.97.103.172"),
                x509.IPAddress("161.97.103.172"),
                x509.DNSName("localhost")
            ]),
            critical=False,
        ).sign(private_key, hashes.SHA256())

        # Write private key to file
        with open("key.pem", "wb") as f:
            f.write(private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            ))

        # Write certificate to file
        with open("cert.pem", "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))

        print("✅ Certificate files generated successfully!")
        print("📁 Files created:")
        print("   - key.pem")
        print("   - cert.pem")
        print("\n🚀 Your API can now run with HTTPS on port 8443!")
        
        # Update .env file with SSL configuration
        if os.path.exists('.env'):
            with open('.env', 'r') as f:
                env_content = f.read()
            
            if 'SSL_KEYFILE' not in env_content:
                with open('.env', 'a') as f:
                    f.write("\n# SSL Configuration\n")
                    f.write("SSL_KEYFILE=key.pem\n")
                    f.write("SSL_CERTFILE=cert.pem\n")
                    f.write("HTTPS_PORT=8443\n")
                print("📝 Updated .env file with SSL configuration")
        
        return True
    except ImportError as e:
        print("❌ Error: Missing required package!")
        print("💡 Install cryptography package first:")
        print("   pip install cryptography")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == '__main__':
    print("🔐 SSL Certificate Generator for Document Processor")
    print("=" * 50)
    print("📋 Prerequisites:")
    print("   pip install cryptography")
    print("\n🎯 Target Server: 161.97.103.172:8443")
    print("=" * 50)
    
    if generate_cert():
        print("\n🎉 SSL setup complete!")
        print("🚀 Run your API with: python main.py")
        print("🌐 Your API will be available at: https://161.97.103.172:8443")
    else:
        print("\n❌ SSL setup failed!")
        print("💡 Make sure to install: pip install cryptography")


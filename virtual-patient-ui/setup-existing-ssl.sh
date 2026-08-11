#!/bin/bash
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}🔐 Setting up existing SSL certificates for HTTPS deployment${NC}"

# Create SSL directory if it doesn't exist
mkdir -p ssl

echo -e "${YELLOW}📋 Please provide the paths to your SSL certificates:${NC}"
echo ""

# Get certificate file path
read -p "Enter the path to your certificate file (.crt or .pem): " CERT_PATH
if [ ! -f "$CERT_PATH" ]; then
    echo -e "${RED}❌ Certificate file not found: $CERT_PATH${NC}"
    exit 1
fi

# Get private key file path
read -p "Enter the path to your private key file (.key): " KEY_PATH
if [ ! -f "$KEY_PATH" ]; then
    echo -e "${RED}❌ Private key file not found: $KEY_PATH${NC}"
    exit 1
fi

# Copy certificates
echo -e "${BLUE}📁 Copying certificates...${NC}"
cp "$CERT_PATH" ssl/cert.pem
cp "$KEY_PATH" ssl/key.pem

# Set proper permissions
chmod 644 ssl/cert.pem
chmod 600 ssl/key.pem

echo -e "${GREEN}✅ SSL certificates copied successfully${NC}"

# Verify certificates
echo -e "${BLUE}🔍 Verifying certificates...${NC}"
echo ""
echo -e "${YELLOW}Certificate details:${NC}"
openssl x509 -in ssl/cert.pem -text -noout | grep -E "(Subject:|Not Before|Not After|Issuer:)"
echo ""
echo -e "${YELLOW}Private key details:${NC}"
openssl rsa -in ssl/key.pem -text -noout | grep -E "(RSA Private-Key|Public-Key:)"
echo ""

# Check if certificate and key match
echo -e "${BLUE}🔗 Verifying certificate and key match...${NC}"
CERT_HASH=$(openssl x509 -noout -modulus -in ssl/cert.pem | openssl md5)
KEY_HASH=$(openssl rsa -noout -modulus -in ssl/key.pem | openssl md5)

if [ "$CERT_HASH" = "$KEY_HASH" ]; then
    echo -e "${GREEN}✅ Certificate and private key match${NC}"
else
    echo -e "${RED}❌ Certificate and private key do not match${NC}"
    echo -e "${YELLOW}Please check your certificate files${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}🎉 SSL setup complete!${NC}"
echo -e "${BLUE}📋 Your certificates are ready in ssl/ directory${NC}"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "1. Deploy with HTTPS: docker compose -f docker-compose.full.yml up -d"
echo "2. Access your app: https://localhost (or your domain)"
echo "3. Check SSL: openssl s_client -connect localhost:443 -servername localhost"
echo ""
echo -e "${BLUE}📁 Certificate files:${NC}"
ls -la ssl/

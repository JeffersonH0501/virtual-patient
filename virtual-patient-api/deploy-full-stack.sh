#!/bin/bash
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 Deploying Virtual Patient Full Stack (API + UI)${NC}"

# Check if we're in the right directory
if [ ! -f "docker-compose.full.yml" ]; then
    echo -e "${RED}❌ docker-compose.full.yml not found${NC}"
    echo -e "${YELLOW}Please run this script from the virtual-patient-api directory${NC}"
    exit 1
fi

# Check if UI directory exists
if [ ! -d "../virtual-patient-ui" ]; then
    echo -e "${RED}❌ UI directory not found at ../virtual-patient-ui${NC}"
    echo -e "${YELLOW}Please ensure your UI is in the correct location${NC}"
    exit 1
fi

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}⚠️  .env file not found. Creating a sample .env file...${NC}"
    cat > .env << EOF
# Database
POSTGRES_PASSWORD=secure_password_123

# Azure OpenAI
AZURE_OPENAI_API_KEY=your_azure_openai_api_key
AZURE_OPENAI_ENDPOINT=your_azure_openai_endpoint
AZURE_OPENAI_DEPLOYMENT_NAME=your_deployment_name
AZURE_OPENAI_API_VERSION=2024-02-15-preview
AZURE_OPENAI_DEPLOYMENT_NAME_MINI=your_mini_deployment_name
AZURE_OPENAI_API_VERSION_MINI=2024-02-15-preview
AZURE_EMBEDDING_DEPLOYMENT=your_embedding_deployment

# LiveKit (Optional)
LIVEKIT_URL=your_livekit_url
LIVEKIT_API_KEY=your_livekit_api_key
LIVEKIT_API_SECRET=your_livekit_api_secret

# Security
SECRET_KEY=your-secret-key-change-in-production

# Google Cloud Storage (GCS) - Optional for TTS audio storage
GCS_BUCKET_NAME=your-gcs-bucket-name
GCS_CREDENTIALS_PATH=/path/to/gcs-credentials.json

# UI Configuration
VITE_API_HOST=api
VITE_API_PORT=8000
VITE_RECAPTCHA_SITE_KEY=your_recaptcha_site_key
EOF
    echo -e "${YELLOW}Please update the .env file with your actual values${NC}"
fi

# Stop existing containers
echo -e "${BLUE}🛑 Stopping existing containers...${NC}"
docker compose -f docker-compose.full.yml down

# Build images
echo -e "${BLUE}🔨 Building Docker images...${NC}"

# Build API image
echo -e "${YELLOW}Building API image...${NC}"
docker build -t virtual-patient-api:latest .

# Build UI image
echo -e "${YELLOW}Building UI image...${NC}"
cd ../virtual-patient-ui
docker build -f Dockerfile.https -t virtual-patient-ui:latest .

# Return to API directory
cd ../virtual-patient-api

# Start services
echo -e "${BLUE}🚀 Starting services...${NC}"
docker compose -f docker-compose.full.yml up -d

# Wait for database to be healthy
echo -e "${BLUE}⏳ Waiting for database to be healthy...${NC}"
sleep 10

# Run database migrations
echo -e "${BLUE}🔄 Running database migrations...${NC}"
docker compose -f docker-compose.full.yml run --rm migration

# Wait for services to be healthy
echo -e "${BLUE}⏳ Waiting for services to be healthy...${NC}"
sleep 15

# Check service status
echo -e "${BLUE}📊 Checking service status...${NC}"
docker compose -f docker-compose.full.yml ps

# Test API health
echo -e "${BLUE}🧪 Testing API health...${NC}"
if curl -f http://localhost:8000/health > /dev/null 2>&1; then
    echo -e "${GREEN}✅ API is healthy${NC}"
else
    echo -e "${RED}❌ API health check failed${NC}"
fi

# Test UI health
echo -e "${BLUE}🧪 Testing UI health...${NC}"
if curl -f http://localhost:3000/ > /dev/null 2>&1; then
    echo -e "${GREEN}✅ UI is healthy${NC}"
else
    echo -e "${RED}❌ UI health check failed${NC}"
fi

echo -e "${GREEN}🎉 Full Stack Deployment Complete!${NC}"
echo ""
echo -e "${BLUE}📋 Services:${NC}"
echo "  - API: http://localhost:8000"
echo "  - UI: http://localhost:3000"
echo "  - Database: localhost:5432"
echo ""
echo -e "${YELLOW}🔧 Next steps:${NC}"
echo "  1. Update your .env file with actual values"
echo "  2. Database migrations are now run automatically during deployment"
echo "  3. Initialize procedural memory: docker compose -f docker-compose.full.yml exec api python scripts/initialize_procedural_memory.py"
echo ""
echo -e "${YELLOW}📝 To start with LiveKit (optional):${NC}"
echo "  docker compose -f docker-compose.full.yml --profile livekit up -d"
echo ""
echo -e "${BLUE}🌐 Access your application:${NC}"
echo "  - Frontend: http://localhost:3000"
echo "  - API Documentation: http://localhost:8000/docs"

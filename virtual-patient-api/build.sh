#!/bin/bash

# Build script for Virtual Patient API Docker image

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🐳 Building Virtual Patient API Docker Image${NC}"

# Function to build image
build_image() {
    local tag=$1
    local context=${2:-.}
    
    echo -e "${YELLOW}Building $tag...${NC}"
    docker build -t "$tag" "$context"
    echo -e "${GREEN}✅ Successfully built $tag${NC}"
}

# Build production image
echo -e "${BLUE}📦 Building production image...${NC}"
build_image "virtual-patient-api:latest"

echo -e "${GREEN}🎉 Docker image built successfully!${NC}"
echo ""
echo -e "${BLUE}Available image:${NC}"
echo "  - virtual-patient-api:latest (production optimized)"
echo ""
echo -e "${YELLOW}To run the application:${NC}"
echo "  docker run -p 8000:8000 virtual-patient-api:latest"
echo ""
echo -e "${YELLOW}To run with docker-compose:${NC}"
echo "  docker-compose up -d"

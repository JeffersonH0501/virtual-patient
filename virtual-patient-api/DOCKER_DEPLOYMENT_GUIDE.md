# 🐳 Virtual Patient - Docker Deployment Guide

Complete guide to deploy API + UI with Docker Compose v2 and HTTPS support.

## 1) Prerequisites
- Docker (Compose V2)
- Azure OpenAI credentials
- SSL cert + key for UI (for HTTPS)

## 2) Environment Setup

Create `.env` file in the **API directory** (`virtual-patient-api/.env`):
```bash
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
GCS_CREDENTIALS_PATH=/app/gcs-credentials.json

# UI Configuration
VITE_API_HOST=
VITE_API_PORT=
VITE_RECAPTCHA_SITE_KEY=your_recaptcha_site_key
```

**Important**: For production with HTTPS + Nginx proxy:
- Leave `VITE_API_HOST` and `VITE_API_PORT` empty
- The UI will proxy API requests through Nginx at `/api/`

## 3) SSL Certificates Setup

**CRITICAL**: SSL certificates must be in the **UI directory** (`virtual-patient-ui/ssl/`):

```bash
cd virtual-patient-ui
mkdir -p ssl
# Copy your existing certificates
cp /path/to/your/cert.pem ssl/
cp /path/to/your/key.pem ssl/
```

Or use the setup script:
```bash
cd virtual-patient-ui
chmod +x setup-existing-ssl.sh
./setup-existing-ssl.sh
```

The `docker-compose.full.yml` will mount these certificates from `../virtual-patient-ui/ssl/`.

## 3.5) Google Cloud Storage (GCS) Setup (Optional)

If you want to store TTS audio files in GCS:

1. **Create a GCS bucket** (if you haven't already):
   ```bash
   gsutil mb gs://your-bucket-name
   ```

2. **Create a service account and download credentials**:
   - Go to Google Cloud Console → IAM & Admin → Service Accounts
   - Create a service account with Storage Admin role
   - Download the JSON key file

3. **Mount credentials in Docker**:
   - Place the JSON file in your project (e.g., `./gcs-credentials.json`)
   - Update `docker-compose.full.yml` volumes section to mount it:
     ```yaml
     volumes:
       - ./logs:/app/logs
       - ./gcs-credentials.json:/app/gcs-credentials.json:ro
     ```

4. **Set environment variables in `.env`**:
   ```bash
   GCS_BUCKET_NAME=your-bucket-name
   GCS_CREDENTIALS_PATH=/app/gcs-credentials.json
   ```

**Note**: If `GCS_BUCKET_NAME` is not set, GCS uploads will be disabled and TTS audio will not be stored.

## 4) Build & Deploy

### Full Stack Deployment (API + UI):

```bash
cd virtual-patient-api

docker compose -f docker-compose.full.yml down && docker compose -f docker-compose.full.yml build --no-cache ui && docker compose -f docker-compose.full.yml build --no-cache api && docker compose -f docker-compose.full.yml up -d

### Initialize Database:

```bash
# Wait for containers to be healthy (check with docker ps)
docker compose -f docker-compose.full.yml exec api python scripts/setup_db.py
docker compose -f docker-compose.full.yml exec api python scripts/initialize_procedural_memory.py
```

### Database Migrations (Alembic):

If you need to run database migrations (e.g., adding new tables):

```bash
cd .../virtual-patient-api

# Rebuild without cache to ensure migrations are copied
docker compose -f docker-compose.full.yml build --no-cache api
docker compose -f docker-compose.full.yml up -d

# Verify the migration is inside the container
docker compose -f docker-compose.full.yml exec api ls -la alembic/versions

# See if Alembic now detects it
docker compose -f docker-compose.full.yml exec api alembic history

# Apply the migration (creates teacher_feedback)
docker compose -f docker-compose.full.yml exec api alembic upgrade head

# Optional: verify table exists
docker compose -f docker-compose.full.yml exec postgres psql -U postgres -d virtual_patient -c "\dt teacher_feedback"
```

**Note**: Migrations are now automatically run during deployment via the migration service in `docker-compose.full.yml`. The above commands are for manual migration management.

## 5) Verify Deployment

```bash
# Check all containers are running
docker compose -f docker-compose.full.yml ps

# Test API
curl http://localhost:8000/health

# Test UI (HTTPS)
curl -k https://localhost/

# Test UI (HTTP redirects to HTTPS)
curl -L http://localhost:3000/
```

## 6) Access the Application

- **UI (HTTPS)**: https://localhost/ or https://your-domain.com
- **UI (HTTP)**: http://localhost:3000/ (redirects to HTTPS)
- **API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **Database**: localhost:5432

## 7) Common Operations

```bash
# View logs
docker compose -f docker-compose.full.yml logs -f ui
docker compose -f docker-compose.full.yml logs -f api

# Restart a service
docker compose -f docker-compose.full.yml restart ui

# Rebuild and restart
docker compose -f docker-compose.full.yml up -d --build ui

# Stop all services
docker compose -f docker-compose.full.yml down

# Stop and remove volumes
docker compose -f docker-compose.full.yml down -v
```

## 8) Troubleshooting

### UI Container Keeps Restarting

**Problem**: Nginx configuration errors or SSL certificates not found

**Solutions**:
1. Check logs: `docker logs virtual-patient-ui`
2. Common errors:
   - `cannot load certificate "/etc/nginx/ssl/cert.pem"`: SSL certificates not in `virtual-patient-ui/ssl/`
   - `invalid value "must-revalidate"`: Old nginx config cached
   - `listen ... http2 deprecated`: Use `nginx-https-working.conf`

**Fix**:
```bash
# Ensure certificates are in UI directory
ls -la ../virtual-patient-ui/ssl/

# Rebuild with no cache
docker compose -f docker-compose.full.yml build --no-cache ui
docker compose -f docker-compose.full.yml up -d ui
```

### Port Already in Use

**Problem**: `Bind for 0.0.0.0:80 failed: port is already allocated`

**Solution**:
```bash
# Check what's using the port
sudo netstat -tlnp | grep :80

# Stop conflicting container
docker stop $(docker ps -q --filter "publish=80")

# Or change port in docker-compose.full.yml
ports:
  - "3000:80"  # Use different host port
  - "443:443"
```

### SSL Certificate Path Issues

**Problem**: Certificates exist but container can't find them

**Solution**:
The docker-compose.full.yml mounts SSL from: `../virtual-patient-ui/ssl:/etc/nginx/ssl:ro`

Ensure:
1. Certificates are in `virtual-patient-ui/ssl/` (NOT `virtual-patient-api/ssl/`)
2. Files named exactly `cert.pem` and `key.pem`
3. Files have correct permissions (readable by Docker)

### Database Connection Errors

**Problem**: `POSTGRES_PASSWORD` not set

**Solution**:
```bash
# Add to .env file in API directory
echo "POSTGRES_PASSWORD=secure_password_123" >> .env

# Restart services
docker compose -f docker-compose.full.yml restart
```

### store_vectors Table Missing

**Problem**: `relation "store_vectors" does not exist`

**Solution**:
```bash
# Reinitialize procedural memory
docker compose -f docker-compose.full.yml exec api python scripts/initialize_procedural_memory.py
```

### API Not Accessible from UI

**Problem**: UI can't connect to API

**Solution**:
1. Check `VITE_API_HOST` and `VITE_API_PORT` are empty in `.env`
2. Ensure both UI and API are in the same Docker network
3. Test API proxy: `curl -k https://localhost/api/health`

## 9) File Structure

```
virtual-patient-api/
├── .env                          # Environment variables
├── docker-compose.full.yml       # Full stack compose file
├── Dockerfile                    # API Dockerfile
├── deploy-full-stack.sh          # Deployment script
└── ssl/                          # NOT USED (SSL should be in UI dir)

virtual-patient-ui/
├── Dockerfile.https              # UI Dockerfile with HTTPS
├── nginx-https-working.conf      # Working Nginx HTTPS config
├── nginx-basic.conf              # HTTP-only config (fallback)
└── ssl/                          # SSL certificates go here
    ├── cert.pem
    └── key.pem
```

## 10) Remote Testing via SSH Tunnel (PuTTY)

If deploying to a remote server and testing from your local machine:

**PuTTY GUI Setup:**
1. Open PuTTY → Connection → SSH → Tunnels
2. Add port forwards:
   - Source: `443` → Destination: `localhost:443` → Add
   - Source: `3000` → Destination: `localhost:3000` → Add
   - Source: `8000` → Destination: `localhost:8000` → Add
3. Connect to your server

**Command Line (OpenSSH):**
```bash
ssh -L 443:localhost:443 -L 3000:localhost:3000 -L 8000:localhost:8000 user@your-server.com
```

**Access After Tunnel:**
- UI: `https://localhost/` (may need to run PuTTY as Administrator)
- API: `http://localhost:8000/docs`

**Note**: Browser will show security warning for localhost - this is normal. Click "Advanced" → "Proceed".

## 11) Production Deployment Summary

1. Clone both repositories
2. Create `.env` in API directory with credentials
3. Place SSL certificates in `virtual-patient-ui/ssl/`
4. Run from API directory:
   ```bash
   docker compose -f docker-compose.full.yml build --no-cache
   docker compose -f docker-compose.full.yml up -d
   docker compose -f docker-compose.full.yml exec api python scripts/setup_db.py
   docker compose -f docker-compose.full.yml exec api python scripts/initialize_procedural_memory.py
   ```
5. Access: https://your-domain.com

That's it! Your Virtual Patient application is now running with HTTPS support.

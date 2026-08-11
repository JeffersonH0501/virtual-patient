# Deployment Guide

## Docker Deployment

### Prerequisites
- Docker installed on your system
- Environment variables configured

### Build and Run

1. **Build the Docker image:**
   ```bash
   docker build -t virtual-patient-ui .
   ```

2. **Run the container:**
   ```bash
   docker run -p 80:80 \
     -e VITE_RECAPTCHA_SITE_KEY=your_recaptcha_key \
     -e VITE_API_HOST=your_api_host \
     -e VITE_API_PORT=your_api_port \
     virtual-patient-ui
   ```

### Environment Variables

The following environment variables are required for the build process:

- `VITE_RECAPTCHA_SITE_KEY`: Google reCAPTCHA site key
- `VITE_API_HOST`: API host URL
- `VITE_API_PORT`: API port number

### Production Deployment

#### Using Docker Compose

Create a `docker-compose.yml` file:

```yaml
version: '3.8'
services:
  virtual-patient-ui:
    build: .
    ports:
      - "80:80"
    environment:
      - VITE_RECAPTCHA_SITE_KEY=${RECAPTCHA_SITE_KEY}
      - VITE_API_HOST=${API_HOST}
      - VITE_API_PORT=${API_PORT}
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
```

#### Using Kubernetes

Create a `k8s-deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: virtual-patient-ui
spec:
  replicas: 3
  selector:
    matchLabels:
      app: virtual-patient-ui
  template:
    metadata:
      labels:
        app: virtual-patient-ui
    spec:
      containers:
      - name: virtual-patient-ui
        image: virtual-patient-ui:latest
        ports:
        - containerPort: 80
        env:
        - name: VITE_RECAPTCHA_SITE_KEY
          valueFrom:
            secretKeyRef:
              name: app-secrets
              key: recaptcha-site-key
        - name: VITE_API_HOST
          valueFrom:
            configMapKeyRef:
              name: app-config
              key: api-host
        - name: VITE_API_PORT
          valueFrom:
            configMapKeyRef:
              name: app-config
              key: api-port
        livenessProbe:
          httpGet:
            path: /health
            port: 80
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 80
          initialDelaySeconds: 5
          periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: virtual-patient-ui-service
spec:
  selector:
    app: virtual-patient-ui
  ports:
  - port: 80
    targetPort: 80
  type: LoadBalancer
```

### Health Checks

The application includes a health check endpoint at `/health` that returns a simple "healthy" response.

### Security Features

The nginx configuration includes:
- Security headers (X-Frame-Options, X-Content-Type-Options, etc.)
- Content Security Policy
- Gzip compression
- Static asset caching
- Hidden file protection

### Performance Optimizations

- Multi-stage Docker build for smaller image size
- Layer caching for faster builds
- Gzip compression for text assets
- Long-term caching for static assets
- Optimized nginx configuration

### Monitoring

The container includes health checks that can be used with container orchestration platforms like Kubernetes or Docker Swarm.

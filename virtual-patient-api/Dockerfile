# syntax=docker/dockerfile:1

# Multi-stage build for production optimization
FROM python:3.12-slim AS builder

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install build dependencies.
#
# The image/codec -dev libraries and OpenGL/GLib runtime libs are required by
# the MediaPipe/WebEyeTrack computer-vision stack
# so its wheels build and import cleanly. libgl1 / libglib2.0-0 satisfy the
# shared-object imports OpenCV performs at runtime.
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    libpq-dev \
    libssl-dev \
    libffi-dev \
    zlib1g-dev \
    libjpeg-dev \
    libpng-dev \
    libgl1 \
    libegl1 \
    libgles2 \
    libglib2.0-0 \
    git \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements before application code so dependency installation
# remains cached when only source code changes.
COPY requirements.txt .

# Install Python dependencies using a persistent BuildKit pip cache.
#
# IMPORTANT:
# Do NOT use --no-cache-dir here.
# The cache mount allows downloaded wheels (PyTorch, OpenCV, etc.)
# to be reused when requirements.txt changes and this layer must run again.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && \
    # CCDb-HG inference is CPU-only; CUDA is not a runtime requirement.
    pip install \
        --index-url https://download.pytorch.org/whl/cpu \
        torch==2.2.2 && \
    pip install -r requirements.txt && \
    sed -i 's/from dataclasses import dataclass/from dataclasses import dataclass, field/' /usr/local/lib/python3.12/site-packages/webeyetrack/webeyetrack.py && \
    sed -i 's/kalman_config: KalmanFilterConfig = KalmanFilterConfig()/kalman_config: KalmanFilterConfig = field(default_factory=KalmanFilterConfig)/' /usr/local/lib/python3.12/site-packages/webeyetrack/webeyetrack.py && \
    sed -i 's/calib_config: CalibConfig = CalibConfig()/calib_config: CalibConfig = field(default_factory=CalibConfig)/' /usr/local/lib/python3.12/site-packages/webeyetrack/webeyetrack.py && \
    sed -i 's/norm_pog: np.ndarray = np.array(\[0.5, 0.5\])/norm_pog: np.ndarray = field(default_factory=lambda: np.array([0.5, 0.5]))/' /usr/local/lib/python3.12/site-packages/webeyetrack/data_protocols.py


# Shared runtime stage. Local development stops before application source is
# copied because docker-compose bind-mounts it into /app.
FROM python:3.12-slim AS runtime

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    HOME=/tmp \
    MPLCONFIGDIR=/tmp/matplotlib \
    ENV=production

# Install runtime dependencies only.
#
# libgl1 and libglib2.0-0 provide the shared libraries OpenCV loads at import
# time; they are required by OpenCV and MediaPipe at runtime.
RUN apt-get update && apt-get install -y \
    postgresql-client \
    libpq5 \
    libssl3 \
    libffi8 \
    zlib1g \
    libjpeg62-turbo \
    libpng16-16 \
    libgl1 \
    libegl1 \
    libgles2 \
    libglib2.0-0 \
    ffmpeg \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Set work directory
WORKDIR /app

# Copy Python packages from builder stage
COPY --from=builder \
    /usr/local/lib/python3.12/site-packages \
    /usr/local/lib/python3.12/site-packages

COPY --from=builder \
    /usr/local/bin \
    /usr/local/bin

# Create runtime directories with the ownership required by the API process.
RUN mkdir -p /app/logs /app/temp /app/media && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Development image: dependencies only. Source is provided by the bind mount,
# so normal Python edits neither require nor invalidate an image build.
FROM runtime AS development

ENV ENV=development

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]


# Production image: immutable source is baked into the final image.
FROM runtime AS production

COPY --chown=appuser:appuser . .

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health', timeout=10).raise_for_status()" || exit 1

# Production command with uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]

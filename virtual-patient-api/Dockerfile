# syntax=docker/dockerfile:1

# Multi-stage build for production optimization
FROM python:3.12-slim@sha256:b18b261e1b4974b4f321451ad5251ded85abb22c2b8b262da527dda1d031ab30 AS builder

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install build dependencies.
#
# The image/codec -dev libraries and OpenGL/GLib runtime libs are required by
# the MediaPipe computer-vision stack
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
COPY requirements.txt requirements.constraints.txt ./

# Install Python dependencies using a persistent BuildKit pip cache.
#
# IMPORTANT:
# Do NOT use --no-cache-dir here.
# The cache mount allows downloaded wheels (PyTorch, OpenCV, etc.)
# to be reused when requirements.txt changes and this layer must run again.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip==26.2.1 && \
    # CCDb-HG inference is CPU-only; CUDA is not a runtime requirement.
    pip install \
        --index-url https://download.pytorch.org/whl/cpu \
        --extra-index-url https://pypi.org/simple \
        -c requirements.constraints.txt \
        torch==2.2.2 && \
    pip install -r requirements.txt -c requirements.constraints.txt

# Metadata checks alone do not catch native NumPy/Arrow import incompatibility.
RUN pip check && python -c "import opensmile, pyarrow"

RUN python -c "import hashlib,pathlib,urllib.request; p=pathlib.Path('/tmp/silero_vad.onnx'); p.write_bytes(urllib.request.urlopen('https://raw.githubusercontent.com/snakers4/silero-vad/60b7ffa243625ebdc1070275a29f18c87843786a/src/silero_vad/data/silero_vad.onnx').read()); assert hashlib.sha256(p.read_bytes()).hexdigest() == '1a153a22f4509e292a94e67d6f9b85e8deb25b4988682b7e174c65279d8788e3'"


# Shared runtime stage. Local development stops before application source is
# copied because docker-compose bind-mounts it into /app.
FROM python:3.12-slim@sha256:b18b261e1b4974b4f321451ad5251ded85abb22c2b8b262da527dda1d031ab30 AS runtime

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

COPY --from=builder /tmp/silero_vad.onnx /usr/local/share/silero-vad/silero_vad.onnx

# Create runtime directories with the ownership required by the API process.
RUN mkdir -p /app/logs /app/temp /app/media && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Development image: dependencies only. Source is provided by the bind mount,
# so normal Python edits neither require nor invalidate an image build.
FROM runtime AS development

USER root
COPY requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt
USER appuser

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

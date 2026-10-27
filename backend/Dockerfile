# ==========================================
# Stage 1: Build Dependencies (Builder Stage)
# ==========================================
FROM python:3.12-slim AS builder

WORKDIR /build

# Install compilation build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create isolated virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies into virtual environment
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ==========================================
# Stage 2: Production Runtime
# ==========================================
FROM python:3.12-slim AS runner

WORKDIR /app

# Install minimal runtime dependencies (curl for container health probes)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Security: Create dedicated unprivileged non-root user and group
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /bin/bash -m appuser

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Set runtime environment variables
ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FASTEMBED_CACHE_PATH="/home/appuser/.cache/fastembed" \
    FLASHRANK_CACHE_DIR="/home/appuser/.cache/flashrank" \
    PORT=8000

# Pre-warm & cache neural models during build to prevent cold-start latency
RUN mkdir -p /home/appuser/.cache/fastembed /home/appuser/.cache/flashrank && \
    python -c "from fastembed import TextEmbedding; list(TextEmbedding(model_name='sentence-transformers/all-MiniLM-L6-v2', cache_dir='/home/appuser/.cache/fastembed').embed(['warmup']))" && \
    python -c "from flashrank import Ranker; Ranker(model_name='ms-marco-TinyBERT-L-2-v2', cache_dir='/home/appuser/.cache/flashrank')"

# Copy application source code
COPY . /app

# Ensure proper ownership of application files and user cache
RUN mkdir -p /app/storage && \
    chown -R appuser:appgroup /app /home/appuser

# Switch to non-root user
USER appuser

# Container Healthcheck probe
HEALTHCHECK --interval=20s --timeout=5s --start-period=15s --retries=3 \
    CMD sh -c "curl -f http://localhost:${PORT:-8000}/health || exit 1"

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]


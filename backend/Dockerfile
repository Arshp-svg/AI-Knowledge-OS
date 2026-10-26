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

# Install python dependencies to user directory
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

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

# Copy installed python wheels from builder to appuser
COPY --from=builder /root/.local /home/appuser/.local

# Set runtime environment variables
ENV PATH="/home/appuser/.local/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME="/home/appuser/.cache/huggingface" \
    PORT=8000

# Pre-warm & cache neural models during build to prevent cold-start latency
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')" && \
    python -c "from flashrank import Ranker; Ranker(model_name='ms-marco-TinyBERT-L-2-v2', cache_dir='/home/appuser/.cache/flashrank')"

# Copy application source code
COPY . /app

# Ensure proper ownership of application files and storage directory
RUN mkdir -p /app/storage && \
    chown -R appuser:appgroup /app /home/appuser/.cache

# Switch to non-root user
USER appuser

# Container Healthcheck probe
HEALTHCHECK --interval=20s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

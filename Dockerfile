# ──────────────────────────────────────────────────────────────────────────────
#  AutoJobAgent — Dockerfile
#  Target: Hugging Face Spaces (Docker) — free 16GB RAM, 2 vCPU
#  Port:   7860  (HF Spaces default)
# ──────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim

# System dependencies (needed for psycopg2, lxml, and general builds)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Working directory inside the container
WORKDIR /app

# Copy the full project
COPY . .

# Install Python dependencies from backend/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r backend/requirements.txt

# Hugging Face Spaces runs as a non-root user — create upload dirs in /tmp
RUN mkdir -p /tmp/uploads

# Expose Hugging Face Spaces default port
EXPOSE 7860

# Health-check so HF knows when the app is ready
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
  CMD curl -f http://localhost:7860/ || exit 1

# Start the Flask app with Gunicorn
# - 2 workers (fits within free-tier memory limits)
# - bind to 0.0.0.0:7860
# - timeout 120s for slower DB cold-starts on Supabase
CMD ["gunicorn", \
     "--chdir", "backend", \
     "--bind", "0.0.0.0:7860", \
     "--workers", "2", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "run:app"]

# Use Python 3.11 slim image for smaller size
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}

# Install system dependencies if needed
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY code/ ./code/
COPY mypy.ini .

# Copy default configs in two locations:
# 1) /app/config is the live path (may be overlaid by a volume)
# 2) /app/.defaults/config is preserved in the image for first-run seeding when a volume is mounted
COPY config/ ./config/
COPY config/ /.defaults/config/
RUN mkdir -p owned_cards

# Copy similarity cache if available (pre-built during CI)
# Store in /.defaults/card_files so it persists after volume mount  
RUN mkdir -p /.defaults/card_files
# Copy entire card_files directory (will include cache if present, empty if not)
COPY card_files/ /.defaults/card_files/

# Create necessary directories as mount points
RUN mkdir -p deck_files logs csv_files card_files config /.defaults

# Create volumes for persistent data
VOLUME ["/app/deck_files", "/app/logs", "/app/csv_files", "/app/card_files", "/app/config", "/app/owned_cards"]

# Create symbolic links BEFORE changing working directory
# These will point to the mounted volumes
RUN cd /app/code && \
    ln -sf /app/deck_files ./deck_files && \
    ln -sf /app/logs ./logs && \
    ln -sf /app/csv_files ./csv_files && \
    ln -sf /app/card_files ./card_files && \
    ln -sf /app/config ./config && \
    ln -sf /app/owned_cards ./owned_cards

# Verify symbolic links were created
RUN cd /app/code && ls -la deck_files logs csv_files card_files config owned_cards

# Set the working directory to code for proper imports
WORKDIR /app/code

# Add a tiny entrypoint to select Web UI (default) or CLI
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
# Normalize line endings in case the file was checked out with CRLF on Windows
RUN sed -i 's/\r$//' /usr/local/bin/entrypoint.sh && \
    chmod +x /usr/local/bin/entrypoint.sh
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

# Expose web port for the optional Web UI
EXPOSE 8080

# Container health check: verify Web UI health endpoint (skip if APP_MODE=cli)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os,sys,json,urllib.request;\
m=os.getenv('APP_MODE','web');\
\
\
\
sys.exit(0) if m=='cli' else None;\
d=urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=3).read();\
sys.exit(0 if json.loads(d.decode()).get('status')=='ok' else 1)"

# Note: For the Web UI, start uvicorn in your orchestrator (compose/run) like:
#   (now default) container starts Web UI automatically; to run CLI set APP_MODE=cli
# Phase 9: enable web list virtualization with env WEB_VIRTUALIZE=1

# Use Python 3.11 slim image for smaller size
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

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
COPY config/ ./config/
RUN mkdir -p owned_cards

# Create necessary directories as mount points
RUN mkdir -p deck_files logs csv_files config

# Create volumes for persistent data
VOLUME ["/app/deck_files", "/app/logs", "/app/csv_files", "/app/config", "/app/owned_cards"]

# Create symbolic links BEFORE changing working directory
# These will point to the mounted volumes
RUN cd /app/code && \
    ln -sf /app/deck_files ./deck_files && \
    ln -sf /app/logs ./logs && \
    ln -sf /app/csv_files ./csv_files && \
    ln -sf /app/config ./config && \
    ln -sf /app/owned_cards ./owned_cards

# Verify symbolic links were created
RUN cd /app/code && ls -la deck_files logs csv_files config owned_cards

# Set the working directory to code for proper imports
WORKDIR /app/code

# Run the application
CMD ["python", "main.py"]

# Note: For the Web UI, start uvicorn in your orchestrator (compose/run) like:
#   uvicorn code.web.app:app --host 0.0.0.0 --port 8080
# Phase 9: enable web list virtualization with env WEB_VIRTUALIZE=1

# Use official Python runtime slim image
FROM python:3.11-slim

# Set environment variables
# Prevent Python from writing .pyc files & enable unbuffered stdout/stderr for Cloud Logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    FLASK_ENV=production

WORKDIR /app

# Install system dependencies (curl for healthchecks)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python packages
COPY backend/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY backend/ /app/backend/
COPY app.py /app/app.py
COPY gunicorn.conf.py /app/gunicorn.conf.py

# Ensure uploads directory exists
RUN mkdir -p /app/backend/uploads

# Create non-root user and set permissions for security best practices
RUN adduser --disabled-password --gecos "" appuser && chown -R appuser:appuser /app
USER appuser

# Document exposed port (Google Cloud Run binds to $PORT dynamically)
EXPOSE 8080

# Healthcheck endpoint (Cloud Run monitors container health via HTTP)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Start Gunicorn server using Cloud Run configuration
CMD ["gunicorn", "--config", "gunicorn.conf.py", "app:app"]

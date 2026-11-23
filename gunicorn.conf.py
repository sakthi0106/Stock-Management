import os

# Google Cloud Run injects PORT (defaults to 8080)
port = os.environ.get("PORT", "8080")
bind = f"0.0.0.0:{port}"

# Concurrency configuration for Google Cloud Run
# gthread worker class enables multi-threaded concurrency for I/O bound Google Sheets API calls
workers = int(os.environ.get("WEB_CONCURRENCY", "2"))
threads = int(os.environ.get("GUNICORN_THREADS", "4"))
worker_class = "gthread"

# Connection & request timeouts
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "120"))
graceful_timeout = 30
keepalive = 5

# Memory management
max_requests = 1000
max_requests_jitter = 100

# Standardized logging to stdout/stderr (captured directly by Google Cloud Logging)
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("LOG_LEVEL", "info")

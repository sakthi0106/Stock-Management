import os

# Google Cloud Run injects PORT (defaults to 8080)
port = os.environ.get("PORT", "8080")
bind = f"0.0.0.0:{port}"

# Concurrency configuration for Google Cloud Run
workers = int(os.environ.get("WEB_CONCURRENCY", "2"))
threads = int(os.environ.get("GUNICORN_THREADS", "4"))
worker_class = "gthread"

timeout = int(os.environ.get("GUNICORN_TIMEOUT", "120"))
graceful_timeout = 30
keepalive = 5

max_requests = 1000
max_requests_jitter = 100

accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("LOG_LEVEL", "info")

import os

# Gunicorn configuration optimized for Render free/starter tiers (512MB RAM ceiling)
bind = f"0.0.0.0:{os.environ.get('PORT', '5000')}"
workers = 1
threads = 2
max_requests = 250
max_requests_jitter = 50
timeout = 120
keepalive = 5
accesslog = "-"
errorlog = "-"

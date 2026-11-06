import multiprocessing
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '5000')}"
workers = int(os.environ.get('WEB_CONCURRENCY', 2))
threads = int(os.environ.get('PYTHON_GET_THREADS', 2))
timeout = int(os.environ.get('GUNICORN_TIMEOUT', 120))
keepalive = 5
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get('LOG_LEVEL', 'info')

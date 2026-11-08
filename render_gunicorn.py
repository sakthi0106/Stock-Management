import multiprocessing
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '5000')}"
# Free tier Render: 1 worker avoids multi-process cache desync, memory limits, and orphaned background threads
workers = int(os.environ.get('WEB_CONCURRENCY', '1'))
threads = int(os.environ.get('PYTHON_GET_THREADS', '4'))
timeout = int(os.environ.get('GUNICORN_TIMEOUT', '120'))
keepalive = 5
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get('LOG_LEVEL', 'info')
preload_app = False

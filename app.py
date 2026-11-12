import sys
from pathlib import Path

# Add backend directory to sys.path so Gunicorn resolves backend imports seamlessly
backend_dir = Path(__file__).resolve().parent / 'backend'
sys.path.insert(0, str(backend_dir))

from app import app

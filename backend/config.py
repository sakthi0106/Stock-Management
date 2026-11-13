import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from project root or backend dir
backend_dir = Path(__file__).resolve().parent
root_dir = backend_dir.parent
load_dotenv(backend_dir / '.env')
load_dotenv(root_dir / '.env')


class Config:
    PORT = int(os.environ.get('PORT', 5000))
    FLASK_ENV = os.environ.get('FLASK_ENV', 'production')
    DEBUG = os.environ.get('DEBUG', 'False').lower() in ('true', '1')

    # Google Sheets credentials
    GOOGLE_SHEETS_SPREADSHEET_ID = os.environ.get('GOOGLE_SHEETS_SPREADSHEET_ID', '').strip()
    GOOGLE_SERVICE_ACCOUNT_JSON = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON', '').strip()

    # Polling frequency (seconds) - default 60s to prevent CPU & memory thrashing on 512MB RAM
    SYNC_INTERVAL_SECONDS = int(os.environ.get('SYNC_INTERVAL_SECONDS', 30))

    # Uploads folder
    UPLOAD_FOLDER = backend_dir / 'uploads'

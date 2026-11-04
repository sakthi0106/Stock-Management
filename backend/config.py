import os
import json
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / '.env')
load_dotenv(BASE_DIR.parent / '.env')


def _clean_path(val: str) -> str:
    if not val:
        cred_default = BASE_DIR / 'credentials' / 'service_account.json'
        if cred_default.exists():
            return str(cred_default)
        return ''
    val = val.strip().strip('"').strip("'")
    norm = os.path.normpath(val)
    if os.path.exists(norm):
        return norm
    cred_fallback = BASE_DIR / 'credentials' / 'service_account.json'
    if cred_fallback.exists():
        return str(cred_fallback)
    return norm


class Config:
    GOOGLE_SHEETS_SPREADSHEET_ID = os.getenv('GOOGLE_SHEETS_SPREADSHEET_ID', '').strip().strip('"').strip("'")
    GOOGLE_SERVICE_ACCOUNT_JSON = _clean_path(os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON', ''))
    SYNC_INTERVAL_SECONDS = int(os.getenv('SYNC_INTERVAL_SECONDS', '30'))
    FLASK_HOST = os.getenv('FLASK_HOST', '127.0.0.1')
    FLASK_PORT = int(os.getenv('FLASK_PORT', '5050'))
    DATABASE_PATH = os.getenv('DATABASE_PATH', str(BASE_DIR / 'stock_metadata.db'))
    CORS_ORIGINS = [
        'http://localhost:5173',
        'http://127.0.0.1:5173',
        'http://localhost:5000',
        'http://127.0.0.1:5000',
        'http://localhost:3000',
        'http://127.0.0.1:3000',
    ]
    DEFAULT_LOW_STOCK_THRESHOLD = 50

    @classmethod
    def is_sheets_configured(cls) -> bool:
        return bool(cls.GOOGLE_SHEETS_SPREADSHEET_ID and cls.GOOGLE_SERVICE_ACCOUNT_JSON and os.path.exists(cls.GOOGLE_SERVICE_ACCOUNT_JSON))

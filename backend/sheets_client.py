import json
import logging
import os
import re
import threading
import httplib2
import google_auth_httplib2
from typing import Dict, List, Any, Optional
from google.oauth2 import service_account
from config import Config

logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
_SERVICE_LOCK = threading.Lock()
_CACHED_SERVICE = None
_CACHED_CREDS_KEY = None
_CACHED_HTTP = None


def to_a1_range(sheet_name: str) -> str:
    """Formats sheet name for Google Sheets A1 notation range syntax."""
    s = str(sheet_name).strip()
    # Simple alphanumeric + underscore sheet names do not require quoting
    if re.match(r'^[a-zA-Z0-9_]+$', s):
        return s
    # Names with spaces or special characters must be wrapped in single quotes, with interior quotes doubled
    escaped = s.replace("'", "''")
    return f"'{escaped}'"


class GoogleSheetsClient:
    """Fast, persistent Google Sheets API client with connection pooling and batch values fetching."""
    def __init__(self, spreadsheet_id: Optional[str] = None, service_account_json: Optional[str] = None):
        self.spreadsheet_id = (spreadsheet_id or Config.GOOGLE_SHEETS_SPREADSHEET_ID or "").strip()
        self.service_account_json = (service_account_json or Config.GOOGLE_SERVICE_ACCOUNT_JSON or "").strip()
        self._service = None
        self._is_configured = False
        self._last_error = None
        self._init_service()

    def _load_credentials(self):
        if not self.service_account_json:
            return None
        if os.path.isfile(self.service_account_json):
            return service_account.Credentials.from_service_account_file(
                self.service_account_json, scopes=SCOPES
            )
        info = json.loads(self.service_account_json)
        return service_account.Credentials.from_service_account_info(
            info, scopes=SCOPES
        )

    def _init_service(self):
        global _CACHED_SERVICE, _CACHED_CREDS_KEY, _CACHED_HTTP
        if not self.spreadsheet_id:
            self._last_error = "No Google Sheets Spreadsheet ID configured."
            return

        creds_key = self.service_account_json[:64] if self.service_account_json else ""
        with _SERVICE_LOCK:
            if _CACHED_SERVICE is not None and _CACHED_CREDS_KEY == creds_key:
                self._service = _CACHED_SERVICE
                self._is_configured = True
                self._last_error = None
                return

            try:
                creds = self._load_credentials()
                if not creds:
                    self._last_error = "Google service account credentials missing or invalid."
                    return

                import googleapiclient.discovery_cache  # noqa: F401
                from googleapiclient.discovery import build

                if _CACHED_HTTP is None:
                    _CACHED_HTTP = httplib2.Http(timeout=20)
                authed_http = google_auth_httplib2.AuthorizedHttp(creds, http=_CACHED_HTTP)

                svc = build(
                    'sheets',
                    'v4',
                    http=authed_http,
                    cache_discovery=False,
                    static_discovery=False
                )
                _CACHED_SERVICE = svc
                _CACHED_CREDS_KEY = creds_key
                self._service = svc
                self._is_configured = True
                self._last_error = None
            except Exception as e:
                self._last_error = str(e)
                logger.error(f"GoogleSheetsClient initialization failed: {e}")

    def is_configured(self) -> bool:
        return self._is_configured and self._service is not None

    def get_last_error(self) -> Optional[str]:
        return self._last_error

    def get_spreadsheet_metadata(self) -> Dict[str, Any]:
        """Fetches spreadsheet title and worksheet tabs metadata (fast fields projection)."""
        if not self.is_configured():
            return {"title": "Google Sheet", "sheets": [], "error": self._last_error}
        try:
            res = self._service.spreadsheets().get(
                spreadsheetId=self.spreadsheet_id,
                fields="properties/title,sheets/properties(sheetId,title)"
            ).execute()
            return res
        except Exception as e:
            logger.error(f"Failed to fetch metadata for {self.spreadsheet_id}: {e}")
            self._last_error = str(e)
            return {"title": "Error", "sheets": [], "error": str(e)}

    def get_batch_sheet_values(self, sheet_names: List[str]) -> Dict[str, List[List[Any]]]:
        """Fetches raw 2D values for all listed sheets in a single fast batch call with per-sheet fallback."""
        if not self.is_configured() or not sheet_names:
            return {}

        result = {}
        # Fetch up to 60 sheets in a single batchGet network round trip
        for idx in range(0, len(sheet_names), 60):
            batch_names = sheet_names[idx:idx + 60]
            ranges = [to_a1_range(name) for name in batch_names]
            try:
                res = self._service.spreadsheets().values().batchGet(
                    spreadsheetId=self.spreadsheet_id,
                    ranges=ranges,
                    valueRenderOption='UNFORMATTED_VALUE',
                    dateTimeRenderOption='FORMATTED_STRING'
                ).execute()

                val_ranges = res.get('valueRanges', [])
                for i, name in enumerate(batch_names):
                    if i < len(val_ranges):
                        result[name] = val_ranges[i].get('values') or []
                    else:
                        result[name] = []
            except Exception as batch_err:
                logger.warning(f"batchGet failed for {batch_names}, attempting single gets: {batch_err}")
                for single_name in batch_names:
                    try:
                        clean_r = to_a1_range(single_name)
                        s_res = self._service.spreadsheets().values().get(
                            spreadsheetId=self.spreadsheet_id,
                            range=clean_r,
                            valueRenderOption='UNFORMATTED_VALUE',
                            dateTimeRenderOption='FORMATTED_STRING'
                        ).execute()
                        result[single_name] = s_res.get('values') or []
                    except Exception as single_err:
                        logger.error(f"Failed to fetch worksheet '{single_name}': {single_err}")
                        result[single_name] = []

        return result

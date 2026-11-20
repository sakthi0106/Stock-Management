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

# Thread-local storage ensures each thread has its own isolated httplib2.Http instance and Google Sheets service
# This completely eliminates [SSL: WRONG_VERSION_NUMBER] socket collision errors in multi-threaded environments
_THREAD_LOCAL = threading.local()
_DISCOVERY_LOCK = threading.Lock()
_CACHED_DISCOVERY_DOC = None


def to_a1_range(sheet_name: str) -> str:
    """Formats sheet name for Google Sheets A1 notation range syntax.
    Preserves exact sheet title (including trailing/leading whitespace) and
    ensures any name with whitespace or special characters is properly single-quoted.
    """
    s = str(sheet_name)
    # Simple alphanumeric + underscore sheet names (without any spaces) do not require quoting
    if re.match(r'^[a-zA-Z0-9_]+$', s):
        return s
    # Names with spaces or special characters must be wrapped in single quotes, with interior quotes doubled
    escaped = s.replace("'", "''")
    return f"'{escaped}'"


def reset_thread_service():
    """Resets the thread-local HTTP and service instances after a connection error."""
    if hasattr(_THREAD_LOCAL, 'service'):
        _THREAD_LOCAL.service = None
    if hasattr(_THREAD_LOCAL, 'http'):
        _THREAD_LOCAL.http = None


class GoogleSheetsClient:
    """Thread-safe, high-performance Google Sheets API client with per-thread socket isolation."""
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
        global _CACHED_DISCOVERY_DOC
        if not self.spreadsheet_id:
            self._last_error = "No Google Sheets Spreadsheet ID configured."
            return

        try:
            creds = self._load_credentials()
            if not creds:
                self._last_error = "Google service account credentials missing or invalid."
                return

            # Check thread-local cache first
            svc = getattr(_THREAD_LOCAL, 'service', None)
            if svc is not None:
                self._service = svc
                self._is_configured = True
                self._last_error = None
                return

            # Create an isolated HTTP transport for this thread
            http = getattr(_THREAD_LOCAL, 'http', None)
            if http is None:
                http = httplib2.Http(timeout=25)
                _THREAD_LOCAL.http = http

            authed_http = google_auth_httplib2.AuthorizedHttp(creds, http=http)

            with _DISCOVERY_LOCK:
                if _CACHED_DISCOVERY_DOC is None:
                    import googleapiclient.discovery_cache  # noqa: F401
                    from googleapiclient.discovery import build
                    temp_svc = build(
                        'sheets',
                        'v4',
                        http=authed_http,
                        cache_discovery=False,
                        static_discovery=False
                    )
                    _CACHED_DISCOVERY_DOC = temp_svc._rootDesc
                    _THREAD_LOCAL.service = temp_svc
                    self._service = temp_svc
                else:
                    from googleapiclient.discovery import build_from_document
                    svc = build_from_document(_CACHED_DISCOVERY_DOC, http=authed_http)
                    _THREAD_LOCAL.service = svc
                    self._service = svc

            self._is_configured = True
            self._last_error = None
        except Exception as e:
            self._last_error = str(e)
            reset_thread_service()
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
            reset_thread_service()
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
                reset_thread_service()
                # Re-initialize service for thread fallback
                self._init_service()
                if not self._service:
                    continue
                for single_name in batch_names:
                    try:
                        clean_r = to_a1_range(single_name)
                        try:
                            s_res = self._service.spreadsheets().values().get(
                                spreadsheetId=self.spreadsheet_id,
                                range=clean_r,
                                valueRenderOption='UNFORMATTED_VALUE',
                                dateTimeRenderOption='FORMATTED_STRING'
                            ).execute()
                        except Exception as try_err:
                            if single_name.strip() != single_name:
                                alt_r = to_a1_range(single_name.strip())
                                s_res = self._service.spreadsheets().values().get(
                                    spreadsheetId=self.spreadsheet_id,
                                    range=alt_r,
                                    valueRenderOption='UNFORMATTED_VALUE',
                                    dateTimeRenderOption='FORMATTED_STRING'
                                ).execute()
                            else:
                                raise try_err
                        result[single_name] = s_res.get('values') or []
                    except Exception as single_err:
                        logger.error(f"Failed to fetch worksheet '{single_name}': {single_err}")
                        result[single_name] = []

        return result

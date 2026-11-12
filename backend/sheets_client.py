import json
import logging
import os
import threading
import httplib2
import google_auth_httplib2
from typing import Dict, List, Any, Optional
from google.oauth2 import service_account
from config import Config

logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
_DISCOVERY_LOCK = threading.Lock()
_CACHED_DISCOVERY_DOC = None


class GoogleSheetsClient:
    """Clean Google Sheets API client for reading worksheets and cellular ranges."""
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

            with _DISCOVERY_LOCK:
                import googleapiclient.discovery_cache  # noqa: F401
                from googleapiclient.discovery import build, build_from_document
                http = httplib2.Http(timeout=15)
                authed_http = google_auth_httplib2.AuthorizedHttp(creds, http=http)

                if _CACHED_DISCOVERY_DOC is None:
                    svc = build(
                        'sheets',
                        'v4',
                        http=authed_http,
                        cache_discovery=False,
                        static_discovery=False
                    )
                    # Cache the discovery schema in memory so subsequent syncs never re-download it
                    _CACHED_DISCOVERY_DOC = svc._rootDesc
                    self._service = svc
                else:
                    self._service = build_from_document(_CACHED_DISCOVERY_DOC, http=authed_http)

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
        """Fetches raw 2D values for listed sheets in an efficient single batch call."""
        if not self.is_configured() or not sheet_names:
            return {}

        result = {}
        try:
            for idx in range(0, len(sheet_names), 10):
                batch_names = sheet_names[idx:idx + 10]
                ranges = [f"'{name}'" for name in batch_names]
                res = self._service.spreadsheets().values().batchGet(
                    spreadsheetId=self.spreadsheet_id,
                    ranges=ranges,
                    valueRenderOption='UNFORMATTED_VALUE',
                    dateTimeRenderOption='FORMATTED_STRING'
                ).execute()

                for i, vr in enumerate(res.get('valueRanges', [])):
                    rng = vr.get('range', '')
                    sheet_title = rng.split('!')[0].strip("'") if '!' in rng else batch_names[i]
                    result[sheet_title] = vr.get('values', [])
            return result
        except Exception as e:
            logger.error(f"Error fetching batch values: {e}")
            self._last_error = str(e)
            return {}

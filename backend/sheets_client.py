import json
import logging
import os
import threading
from typing import Dict, List, Any, Optional
from google.oauth2 import service_account
from config import Config

logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
_DISCOVERY_LOCK = threading.Lock()


class GoogleSheetsClient:
    """Clean Google Sheets API client for reading worksheets and cellular ranges."""
    def __init__(self, spreadsheet_id: Optional[str] = None, service_account_json: Optional[str] = None):
        self.spreadsheet_id = (spreadsheet_id or Config.GOOGLE_SHEETS_SPREADSHEET_ID or "").strip()
        self.service_account_json = (service_account_json or Config.GOOGLE_SERVICE_ACCOUNT_JSON or "").strip()
        self._service = None
        self._is_configured = False
        self._last_error = None
        self._init_service()

    def _init_service(self):
        if not self.spreadsheet_id:
            self._last_error = "No Google Sheets Spreadsheet ID configured."
            return

        try:
            creds = None
            if self.service_account_json:
                if os.path.isfile(self.service_account_json):
                    creds = service_account.Credentials.from_service_account_file(
                        self.service_account_json, scopes=SCOPES
                    )
                else:
                    info = json.loads(self.service_account_json)
                    creds = service_account.Credentials.from_service_account_info(
                        info, scopes=SCOPES
                    )

            if creds:
                with _DISCOVERY_LOCK:
                    # Lazy-import inside lock to prevent Python 3.14 partial module init race across threads
                    import googleapiclient.discovery_cache  # noqa: F401
                    from googleapiclient.discovery import build
                    self._service = build(
                        'sheets',
                        'v4',
                        credentials=creds,
                        cache_discovery=False,
                        static_discovery=False
                    )
                self._is_configured = True
                self._last_error = None
            else:
                self._last_error = "Google service account credentials missing or invalid."
        except Exception as e:
            self._last_error = str(e)
            logger.warning(f"GoogleSheetsClient initialization notice: {e}")

    def is_configured(self) -> bool:
        return self._is_configured and self._service is not None

    def get_last_error(self) -> Optional[str]:
        return self._last_error

    def get_spreadsheet_metadata(self) -> Dict[str, Any]:
        """Fetches spreadsheet title and worksheet tabs metadata."""
        if not self.is_configured():
            return {"title": "Google Sheet", "sheets": [], "error": self._last_error}
        try:
            res = self._service.spreadsheets().get(spreadsheetId=self.spreadsheet_id).execute()
            return res
        except Exception as e:
            logger.error(f"Failed to fetch metadata for {self.spreadsheet_id}: {e}")
            self._last_error = str(e)
            return {"title": "Error", "sheets": [], "error": str(e)}

    def get_batch_sheet_values(self, sheet_names: List[str]) -> Dict[str, List[List[Any]]]:
        """Fetches raw 2D values for listed sheets in an efficient single batch call."""
        if not self.is_configured() or not sheet_names:
            return {}

        ranges = [f"'{name}'!A1:ZZ5000" for name in sheet_names]
        try:
            res = self._service.spreadsheets().values().batchGet(
                spreadsheetId=self.spreadsheet_id,
                ranges=ranges,
                valueRenderOption='UNFORMATTED_VALUE',
                dateTimeRenderOption='FORMATTED_STRING'
            ).execute()

            result = {}
            for vr in res.get('valueRanges', []):
                rng = vr.get('range', '')
                sheet_title = rng.split('!')[0].strip("'")
                result[sheet_title] = vr.get('values', [])
            return result
        except Exception as e:
            logger.error(f"Error fetching batch values: {e}")
            self._last_error = str(e)
            return {}

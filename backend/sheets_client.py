import json
import logging
import os
import socket
import time
from typing import Dict, List, Any, Optional
from pathlib import Path
from config import Config

socket.setdefaulttimeout(10.0)

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly"
]

SERVICE_ACCOUNT_EMAIL = "stockmanagement@shining-courage-510614-a2.iam.gserviceaccount.com"

class GoogleSheetsClient:
    def __init__(
        self,
        spreadsheet_id: Optional[str] = None,
        service_account_json: Optional[str] = None,
        local_only: bool = False,
        file_path: Optional[str] = None,
    ):
        raw_id = spreadsheet_id or Config.GOOGLE_SHEETS_SPREADSHEET_ID
        self.spreadsheet_id = raw_id
        self.service_account_json = service_account_json or Config.GOOGLE_SERVICE_ACCOUNT_JSON
        self.file_path = file_path
        self._is_local_file = False

        # Detect local file
        if self.file_path and os.path.exists(self.file_path):
            self._is_local_file = True
        elif raw_id and (raw_id.startswith("local_file:") or os.path.isfile(raw_id)):
            self.file_path = raw_id[len("local_file:"):] if raw_id.startswith("local_file:") else raw_id
            self._is_local_file = os.path.exists(self.file_path)

        self._service = None
        self._is_configured = False
        self._last_error = None
        self._cached_demo_values: Optional[Dict[str, List[List[Any]]]] = None
        self._cached_demo_metadata: Optional[Dict[str, Any]] = None

        if self._is_local_file:
            self._is_configured = True
            logger.info(f"Initialized local Excel workbook source: {self.file_path}")
        elif not local_only:
            self._init_service()

    def _init_service(self):
        if not self.spreadsheet_id or not self.service_account_json:
            self._is_configured = False
            self._last_error = "Google Sheets credentials or Spreadsheet ID not configured"
            logger.info("Google Sheets not configured. Running with local 6-sheet master.")
            return

        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            creds = None
            if os.path.exists(self.service_account_json):
                creds = service_account.Credentials.from_service_account_file(
                    self.service_account_json, scopes=SCOPES
                )
            else:
                try:
                    info = json.loads(self.service_account_json)
                    creds = service_account.Credentials.from_service_account_info(
                        info, scopes=SCOPES
                    )
                except Exception:
                    raise FileNotFoundError(f"Service account file not found: {self.service_account_json}")

            self._service = build("sheets", "v4", credentials=creds, cache_discovery=False)
            self._is_configured = True
            logger.info("Successfully connected to Google Sheets API v4")
        except Exception as e:
            self._is_configured = False
            self._last_error = str(e)
            logger.warning(f"Could not initialize Google Sheets client: {e}. Falling back to local master.")

    def is_configured(self) -> bool:
        return self._is_configured

    def get_last_error(self) -> Optional[str]:
        return self._last_error

    def get_spreadsheet_metadata(self, max_retries: int = 2) -> Dict[str, Any]:
        """Fetch metadata including all sheet titles and dimensions."""
        if self._is_local_file and self.file_path:
            return self._load_excel_metadata(self.file_path)

        is_default_master = (self.spreadsheet_id == Config.GOOGLE_SHEETS_SPREADSHEET_ID)

        if not self._is_configured or not self._service:
            if is_default_master:
                return self._get_demo_metadata()
            raise ValueError(f"Google Sheets client is not configured: {self._last_error}")

        for attempt in range(max_retries):
            try:
                sheet_metadata = self._service.spreadsheets().get(
                    spreadsheetId=self.spreadsheet_id,
                    includeGridData=False
                ).execute()
                return sheet_metadata
            except Exception as e:
                err_str = str(e)
                if "403" in err_str or "PERMISSION_DENIED" in err_str:
                    clean_msg = (
                        f"Google Sheets permission denied (403). Please share your spreadsheet with: "
                        f"{SERVICE_ACCOUNT_EMAIL} (Viewer role), or set link sharing to 'Anyone with the link can view'."
                    )
                    if not is_default_master:
                        raise PermissionError(clean_msg) from e
                if not is_default_master:
                    raise e
                logger.warning(f"Google Sheets metadata warning: {err_str}. Using local master dataset.")
                return self._get_demo_metadata()
        return self._get_demo_metadata()

    def get_batch_sheet_values(self, sheet_names: List[str]) -> Dict[str, List[List[Any]]]:
        """Fetch all sheets in a SINGLE Google Sheets API batchGet call."""
        if self._is_local_file and self.file_path:
            return self._load_excel_batch_values(self.file_path, sheet_names)

        is_default_master = (self.spreadsheet_id == Config.GOOGLE_SHEETS_SPREADSHEET_ID)

        if not self._is_configured or not self._service:
            if is_default_master:
                return self._get_all_demo_sheet_values(sheet_names)
            raise ValueError(f"Google Sheets client is not configured: {self._last_error}")

        ranges = [f"'{s}'!A1:ZZ" for s in sheet_names]
        try:
            resp = self._service.spreadsheets().values().batchGet(
                spreadsheetId=self.spreadsheet_id,
                ranges=ranges,
                valueRenderOption="FORMATTED_VALUE",
                dateTimeRenderOption="FORMATTED_STRING"
            ).execute()

            results = {}
            value_ranges = resp.get("valueRanges", [])
            for idx, vr in enumerate(value_ranges):
                s_name = sheet_names[idx] if idx < len(sheet_names) else f"Sheet{idx+1}"
                results[s_name] = vr.get("values", [])
            return results
        except Exception as e:
            if not is_default_master:
                err_str = str(e)
                if "403" in err_str or "PERMISSION_DENIED" in err_str:
                    raise PermissionError(
                        f"Google Sheets permission denied (403). Please share your spreadsheet with: "
                        f"{SERVICE_ACCOUNT_EMAIL} (Viewer role)"
                    ) from e
                raise e
            logger.warning(f"Google Sheets batchGet warning: {e}. Falling back to cached local dataset.")
            return self._get_all_demo_sheet_values(sheet_names)

    def get_batch_sheet_formulas(self, sheet_names: List[str]) -> Dict[str, List[List[Any]]]:
        return {sheet_name: [] for sheet_name in sheet_names}

    def get_sheet_values(self, sheet_name: str, render_option: str = "FORMATTED_VALUE", max_retries: int = 1) -> List[List[Any]]:
        if self._is_local_file and self.file_path:
            vals = self._load_excel_batch_values(self.file_path, [sheet_name])
            return vals.get(sheet_name, [])

        is_default_master = (self.spreadsheet_id == Config.GOOGLE_SHEETS_SPREADSHEET_ID)
        if not self._is_configured or not self._service:
            return self._get_demo_sheet_values(sheet_name)

        range_name = f"'{sheet_name}'!A1:ZZ"
        try:
            result = self._service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
                valueRenderOption=render_option,
                dateTimeRenderOption="FORMATTED_STRING"
            ).execute()
            return result.get("values", [])
        except Exception as e:
            if not is_default_master:
                raise e
            logger.warning(f"Google Sheets read warning for '{sheet_name}': {e}")
            return self._get_demo_sheet_values(sheet_name)

    def get_sheet_formulas(self, sheet_name: str) -> List[List[Any]]:
        return []

    # ---------------- Excel File Loader for uploaded / local workbooks ----------------

    def _load_excel_metadata(self, file_path: str) -> Dict[str, Any]:
        import openpyxl
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        sheets_meta = []
        for idx, sname in enumerate(wb.sheetnames, start=1):
            ws = wb[sname]
            sheet_rows_count = ws.max_row or 100
            sheet_cols_count = ws.max_column or 50
            sheets_meta.append({
                "properties": {
                    "title": sname,
                    "sheetId": idx,
                    "gridProperties": {
                        "rowCount": sheet_rows_count,
                        "columnCount": sheet_cols_count
                    }
                }
            })
        wb.close()
        return {
            "properties": {"title": Path(file_path).stem},
            "sheets": sheets_meta
        }

    def _load_excel_batch_values(self, file_path: str, sheet_names: List[str]) -> Dict[str, List[List[Any]]]:
        import openpyxl
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        results = {}
        for sname in sheet_names:
            if sname not in wb.sheetnames:
                results[sname] = []
                continue
            ws = wb[sname]
            rows = []
            for row in ws.iter_rows(values_only=True):
                if any(c is not None for c in row[:15]):
                    rows.append(list(row))
            results[sname] = rows
        wb.close()
        return results

    # ---------------- High-Performance Real Master Local Fallback Provider ----------------
    def _ensure_demo_cache_loaded(self):
        if self._cached_demo_values is not None:
            return

        wb_path = Path(__file__).resolve().parent.parent / "sample-data" / "saravanan_actual_stock_master.xlsx"
        if not wb_path.exists():
            self._cached_demo_values = {}
            return

        try:
            import openpyxl
            wb = openpyxl.load_workbook(str(wb_path), read_only=True, data_only=True)
            cached = {}
            sheets_meta = []
            for idx, sname in enumerate(wb.sheetnames, start=1):
                ws = wb[sname]
                sheet_rows = []
                for row in ws.iter_rows(values_only=True):
                    if any(c is not None for c in row[:10]):
                        sheet_rows.append(list(row))
                cached[sname] = sheet_rows
                sheets_meta.append({
                    "properties": {
                        "title": sname,
                        "sheetId": idx,
                        "gridProperties": {
                            "rowCount": len(sheet_rows),
                            "columnCount": max((len(r) for r in sheet_rows), default=100)
                        }
                    }
                })
            wb.close()
            self._cached_demo_values = cached
            self._cached_demo_metadata = {
                "properties": {"title": "Saravanan Electricals Master Stock Sheet"},
                "sheets": sheets_meta
            }
            logger.info(f"Loaded and cached {len(cached)} sheets from local stock master.")
        except Exception as e:
            logger.error(f"Failed to load local stock master: {e}")
            self._cached_demo_values = {}

    def _get_demo_metadata(self) -> Dict[str, Any]:
        self._ensure_demo_cache_loaded()
        if self._cached_demo_metadata:
            return self._cached_demo_metadata

        return {
            "properties": {"title": "Saravanan Electricals Master Stock Sheet"},
            "sheets": [
                {"properties": {"title": "Busbar", "sheetId": 1, "gridProperties": {"rowCount": 130, "columnCount": 110}}},
                {"properties": {"title": "ACCESORIES", "sheetId": 2, "gridProperties": {"rowCount": 160, "columnCount": 110}}},
                {"properties": {"title": "Cable,Lug,Lamp,TB,Truff", "sheetId": 3, "gridProperties": {"rowCount": 190, "columnCount": 110}}},
                {"properties": {"title": "SLEEVE ", "sheetId": 4, "gridProperties": {"rowCount": 80, "columnCount": 110}}},
                {"properties": {"title": "Fab Sheets", "sheetId": 5, "gridProperties": {"rowCount": 30, "columnCount": 110}}},
                {"properties": {"title": "Fasteners", "sheetId": 6, "gridProperties": {"rowCount": 120, "columnCount": 110}}}
            ]
        }

    def _get_demo_sheet_values(self, sheet_name: str) -> List[List[Any]]:
        self._ensure_demo_cache_loaded()
        if self._cached_demo_values and sheet_name in self._cached_demo_values:
            return self._cached_demo_values[sheet_name]
        return []

    def _get_all_demo_sheet_values(self, sheet_names: List[str]) -> Dict[str, List[List[Any]]]:
        self._ensure_demo_cache_loaded()
        results = {}
        for s in sheet_names:
            results[s] = self._cached_demo_values.get(s, []) if self._cached_demo_values else []
        return results

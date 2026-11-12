import uuid
import time
import logging
import threading
import datetime
from typing import Dict, List, Any, Optional
from sheets_client import GoogleSheetsClient
from inventory_store import InventoryDataStore, extract_spreadsheet_id
from config import Config

logger = logging.getLogger(__name__)


class SyncManager:
    """Manages multi-source Google Sheets registrations and 15-second automatic synchronization."""

    def __init__(self):
        self.sources: Dict[str, InventoryDataStore] = {}
        self.active_source_id: Optional[str] = None
        self._lock = threading.RLock()

        self.sync_interval = Config.SYNC_INTERVAL_SECONDS
        self._poller_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._is_paused = False
        self._is_syncing = False
        self.sync_history: List[Dict[str, Any]] = []

        # Auto-register primary environment Google Sheet if configured
        if Config.GOOGLE_SHEETS_SPREADSHEET_ID:
            sid = extract_spreadsheet_id(Config.GOOGLE_SHEETS_SPREADSHEET_ID)
            self.register_source(
                name="Primary Stock Sheet",
                spreadsheet_url_or_id=sid,
                source_id="default_source",
                is_active=True
            )

    def register_source(
        self,
        name: str,
        spreadsheet_url_or_id: str,
        period: str = "",
        description: str = "",
        source_type: str = "google_sheets",
        source_id: Optional[str] = None,
        is_active: bool = True
    ) -> InventoryDataStore:
        with self._lock:
            sid = source_id or f"src_{uuid.uuid4().hex[:8]}"
            clean_sheet_id = spreadsheet_url_or_id if source_type == "excel_upload" else extract_spreadsheet_id(spreadsheet_url_or_id)
            store = InventoryDataStore(
                source_id=sid,
                name=name,
                spreadsheet_id=clean_sheet_id,
                source_type=source_type
            )
            store.period = period
            store.description = description

            if is_active or not self.active_source_id:
                for s in self.sources.values():
                    s.is_active = 0
                store.is_active = 1
                self.active_source_id = sid
            else:
                store.is_active = 0

            self.sources[sid] = store
            return store

    def get_store(self, source_filter: str = "active") -> Optional[InventoryDataStore]:
        with self._lock:
            if not self.sources:
                return None
            if source_filter == "active":
                if self.active_source_id and self.active_source_id in self.sources:
                    return self.sources[self.active_source_id]
                # Fallback to first available source
                first_id = next(iter(self.sources))
                return self.sources[first_id]
            return self.sources.get(source_filter)

    def activate_source(self, source_id: str) -> bool:
        with self._lock:
            if source_id not in self.sources:
                return False
            for sid, store in self.sources.items():
                store.is_active = 1 if sid == source_id else 0
            self.active_source_id = source_id
            return True

    def delete_source(self, source_id: str) -> bool:
        with self._lock:
            if source_id not in self.sources:
                return False
            self.sources.pop(source_id)
            if self.active_source_id == source_id:
                self.active_source_id = next(iter(self.sources)) if self.sources else None
                if self.active_source_id:
                    self.sources[self.active_source_id].is_active = 1
            return True

    def start_poller(self):
        if self._poller_thread and self._poller_thread.is_alive():
            return
        self._stop_event.clear()
        self._poller_thread = threading.Thread(target=self._poll_loop, daemon=True, name="GoogleSheetsSyncThread")
        self._poller_thread.start()
        logger.info("Started 15-second Google Sheets background synchronization worker.")

    def stop_poller(self):
        self._stop_event.set()
        if self._poller_thread:
            self._poller_thread.join(timeout=2.0)

    def pause_sync(self):
        self._is_paused = True

    def resume_sync(self):
        self._is_paused = False

    def _poll_loop(self):
        # Perform initial sync immediately if active source exists
        if self.active_source_id:
            self.sync_source(self.active_source_id)
        while not self._stop_event.is_set():
            time.sleep(self.sync_interval)
            if not self._is_paused and self.active_source_id:
                store = self.get_store("active")
                if store and store.source_type != "excel_upload":
                    self.sync_source(store.source_id)

    def sync_source(self, source_id: str = "active", force: bool = False) -> bool:
        store = self.get_store(source_id)
        if not store:
            return False

        if store.source_type == "excel_upload":
            return True

        if self._is_syncing and not force:
            return False

        self._is_syncing = True
        try:
            client = GoogleSheetsClient(spreadsheet_id=store.spreadsheet_id)
            if not client.is_configured():
                err = client.get_last_error() or "Google Sheets credentials missing."
                store.last_sync_status = "error"
                store.last_sync_error = err
                self._record_run(store, "error", err)
                return False

            meta = client.get_spreadsheet_metadata()
            if meta.get("error"):
                store.last_sync_status = "error"
                store.last_sync_error = meta["error"]
                self._record_run(store, "error", meta["error"])
                return False

            sheets_info = meta.get("sheets", [])
            sheet_names = [s.get("properties", {}).get("title") for s in sheets_info if s.get("properties", {}).get("title")]
            if not sheet_names:
                err = "No worksheets found in spreadsheet."
                store.last_sync_status = "error"
                store.last_sync_error = err
                self._record_run(store, "error", err)
                return False

            raw_dict = client.get_batch_sheet_values(sheet_names)
            if not raw_dict and client.get_last_error():
                err = client.get_last_error()
                store.last_sync_status = "error"
                store.last_sync_error = err
                self._record_run(store, "error", err)
                return False

            sheet_title = meta.get("properties", {}).get("title")
            if sheet_title and store.name in ("Primary Stock Sheet", "Google Sheet", ""):
                store.name = sheet_title

            store.update_from_raw_sheets(raw_dict)
            self._record_run(store, "success", None)
            return True
        except Exception as e:
            logger.error(f"Sync failed for {store.source_id}: {e}", exc_info=True)
            store.last_sync_status = "error"
            store.last_sync_error = str(e)
            self._record_run(store, "error", str(e))
            return False
        finally:
            self._is_syncing = False

    def _record_run(self, store: InventoryDataStore, status: str, error: Optional[str]):
        self.sync_history.insert(0, {
            "id": uuid.uuid4().hex[:8],
            "source_id": store.source_id,
            "source_name": store.name,
            "status": status,
            "sheets_processed": len(store.worksheets),
            "products_count": len(store.products),
            "movements_count": len(store.movements),
            "error_message": error,
            "synced_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
        })
        if len(self.sync_history) > 50:
            self.sync_history = self.sync_history[:50]

    def get_status(self) -> Dict[str, Any]:
        store = self.get_store("active")
        if not store:
            return {
                "state": "paused" if self._is_paused else "disconnected",
                "is_live_google_sheet": False,
                "is_paused": self._is_paused,
                "poll_interval_seconds": self.sync_interval,
                "lastSuccess": None,
                "lastError": "No spreadsheet source connected. Add a Google Sheet ID or upload Excel.",
                "source": "No Active Source",
                "itemsSynced": 0,
                "sheetsProcessed": 0,
                "sheets": [],
                "nextSync": f"Every {self.sync_interval}s"
            }

        is_live = store.source_type == "google_sheets" and store.last_sync_status == "success"
        state = "paused" if self._is_paused else ("syncing" if self._is_syncing else ("connected" if is_live else ("error" if store.last_sync_status == "error" else "demo")))

        sheets_status = [
            {
                "name": w["sheet_name"],
                "status": "success",
                "row_count": w["row_count"],
                "last_sync": store.last_sync_at,
                "issues": w.get("issues", [])
            }
            for w in store.worksheets
        ]

        return {
            "state": state,
            "is_live_google_sheet": is_live,
            "is_paused": self._is_paused,
            "poll_interval_seconds": self.sync_interval,
            "lastSuccess": store.last_sync_at,
            "lastError": store.last_sync_error,
            "source": store.name,
            "itemsSynced": len(store.products),
            "sheetsProcessed": len(store.worksheets),
            "sheets": sheets_status,
            "nextSync": f"Every {self.sync_interval}s"
        }

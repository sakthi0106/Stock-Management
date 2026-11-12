import time
import logging
import threading
from typing import Dict, List, Any, Optional
from sheets_client import GoogleSheetsClient
from inventory_store import InventoryDataStore
from config import Config

logger = logging.getLogger(__name__)


class SyncManager:
    """Manages periodic 15-second synchronization from Google Sheets directly to memory."""

    def __init__(self, client: Optional[GoogleSheetsClient] = None, store: Optional[InventoryDataStore] = None):
        self.client = client or GoogleSheetsClient()
        self.store = store or InventoryDataStore()
        self.sync_interval = Config.SYNC_INTERVAL_SECONDS
        self._poller_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._is_paused = False
        self._is_syncing = False
        self._last_error: Optional[str] = None
        self._last_sync_time: Optional[str] = None

    def start_poller(self):
        if self._poller_thread and self._poller_thread.is_alive():
            return
        self._stop_event.clear()
        self._poller_thread = threading.Thread(target=self._poll_loop, daemon=True, name="GoogleSheetsSyncThread")
        self._poller_thread.start()
        logger.info(f"Started 15-second Google Sheets background synchronization worker.")

    def stop_poller(self):
        self._stop_event.set()
        if self._poller_thread:
            self._poller_thread.join(timeout=2.0)

    def pause_sync(self):
        self._is_paused = True

    def resume_sync(self):
        self._is_paused = False

    def is_paused(self) -> bool:
        return self._is_paused

    def _poll_loop(self):
        # Trigger immediate sync upon start
        self.sync(force=True)
        while not self._stop_event.is_set():
            time.sleep(self.sync_interval)
            if not self._is_paused:
                self.sync(force=False)

    def sync(self, force: bool = False) -> bool:
        """Fetches latest sheets data from Google Sheets API and updates store."""
        if self._is_syncing and not force:
            return False

        self._is_syncing = True
        try:
            if not self.client.is_configured():
                self._last_error = self.client.get_last_error() or "Google Sheets not configured."
                self.store.source_metadata["status"] = "unconfigured"
                return False

            meta = self.client.get_spreadsheet_metadata()
            sheets_info = meta.get('sheets', [])
            sheet_names = [s.get('properties', {}).get('title') for s in sheets_info if s.get('properties', {}).get('title')]

            if not sheet_names:
                self._last_error = "No worksheets found in spreadsheet."
                return False

            raw_dict = self.client.get_batch_sheet_values(sheet_names)
            self.store.update_from_raw_sheets(raw_dict)

            self.store.source_metadata["title"] = meta.get('properties', {}).get('title', 'Google Sheet')
            self._last_error = None
            self._last_sync_time = self.store.source_metadata.get("last_sync_at")
            return True
        except Exception as e:
            logger.error(f"Sync error: {e}", exc_info=True)
            self._last_error = str(e)
            self.store.source_metadata["status"] = "error"
            return False
        finally:
            self._is_syncing = False

    def get_status(self) -> Dict[str, Any]:
        return {
            "is_configured": self.client.is_configured(),
            "is_paused": self._is_paused,
            "is_syncing": self._is_syncing,
            "interval_seconds": self.sync_interval,
            "last_sync_at": self._last_sync_time,
            "last_error": self._last_error,
            "total_items": len(self.store.products),
            "total_movements": len(self.store.movements),
            "total_worksheets": len(self.store.worksheets),
            "source_title": self.store.source_metadata.get("title", "Google Sheets")
        }

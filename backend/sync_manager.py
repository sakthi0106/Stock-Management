import os
import json
import uuid
import time
import logging
import threading
import datetime
from typing import Dict, List, Any, Optional
from sheets_client import GoogleSheetsClient
from inventory_store import InventoryDataStore, extract_spreadsheet_id
from spreadsheet_reader import UniversalSpreadsheetReader
from config import Config

logger = logging.getLogger(__name__)


class SyncManager:
    """Manages multi-source Google Sheets registrations, uploaded Excel workbooks, persistence, and synchronization."""

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

        # Restore previously uploaded Excel workbooks from persistent registry
        self._load_registry()

    def _get_registry_path(self) -> str:
        os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
        return os.path.join(Config.UPLOAD_FOLDER, "sources_registry.json")

    def _save_registry(self):
        """Persists source metadata to disk so worker restarts or Render wake-ups preserve sources."""
        try:
            reg_path = self._get_registry_path()
            serializable = []
            with self._lock:
                for sid, store in self.sources.items():
                    if store.source_type == "excel_upload":
                        serializable.append({
                            "source_id": store.source_id,
                            "name": store.name,
                            "spreadsheet_id": store.spreadsheet_id,
                            "period": store.period,
                            "description": store.description,
                            "source_type": store.source_type,
                            "is_active": store.is_active,
                            "status": store.status
                        })
            with open(reg_path, 'w', encoding='utf-8') as f:
                json.dump(serializable, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not persist sources registry: {e}")

    def _load_registry(self):
        """Restores sources and reparses them on startup if files exist on disk."""
        reg_path = self._get_registry_path()
        if not os.path.exists(reg_path):
            return

        try:
            with open(reg_path, 'r', encoding='utf-8') as f:
                records = json.load(f)

            reader = UniversalSpreadsheetReader()
            for r in records:
                sid = r.get("source_id")
                clean_path = r.get("spreadsheet_id", "")
                if clean_path.startswith("local_file:"):
                    clean_path = clean_path.split("local_file:", 1)[1]

                if not os.path.exists(clean_path):
                    # Check relative to uploads folder
                    basename = os.path.basename(clean_path)
                    candidate = os.path.join(Config.UPLOAD_FOLDER, basename)
                    if os.path.exists(candidate):
                        clean_path = candidate
                    else:
                        continue

                try:
                    extracted = reader.extract_from_excel(clean_path)
                    raw_dict = {sname: sdata.get('values', []) for sname, sdata in extracted.get('sheets', {}).items()}

                    store = self.register_source(
                        name=r.get("name", "Restored Source"),
                        spreadsheet_url_or_id=f"local_file:{clean_path}",
                        period=r.get("period", ""),
                        description=r.get("description", ""),
                        source_type="excel_upload",
                        source_id=sid,
                        is_active=bool(r.get("is_active", False))
                    )
                    store.status = r.get("status", "active")
                    store.update_from_raw_sheets(raw_dict, period=r.get("period", ""))
                    logger.info(f"Successfully restored persistent source '{store.name}' ({sid}).")
                except Exception as ex:
                    logger.warning(f"Could not restore source {sid}: {ex}")

        except Exception as e:
            logger.warning(f"Failed loading sources registry: {e}")

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
            self._save_registry()
            return store

    def get_combined_store(self) -> InventoryDataStore:
        """Constructs a unified, combined view across all registered and non-archived sources."""
        combined = InventoryDataStore(
            source_id="all",
            name="All Sources (Combined)",
            spreadsheet_id="all",
            source_type="combined"
        )
        with self._lock:
            all_prods = []
            all_movs = []
            all_worksheets = []
            all_dyn_cols: Dict[str, List[Dict[str, Any]]] = {}
            all_dyn_recs: Dict[str, List[Dict[str, Any]]] = {}

            for sid, store in self.sources.items():
                if store.status == "archived":
                    continue

                for p in store.products:
                    p_copy = dict(p)
                    p_copy["source_id"] = store.source_id
                    p_copy["source_name"] = store.name
                    all_prods.append(p_copy)

                for m in store.movements:
                    m_copy = dict(m)
                    m_copy["source_id"] = store.source_id
                    m_copy["source_name"] = store.name
                    all_movs.append(m_copy)

                for w in store.worksheets:
                    w_copy = dict(w)
                    w_copy["source_id"] = store.source_id
                    w_copy["source_name"] = store.name
                    all_worksheets.append(w_copy)

                prefix = f"{store.name} - " if len(self.sources) > 1 else ""
                for sname, cols in store.dynamic_columns.items():
                    all_dyn_cols[f"{prefix}{sname}"] = cols

                for sname, recs in store.dynamic_records.items():
                    all_dyn_recs[f"{prefix}{sname}"] = recs

            # Sort movements by date descending
            all_movs.sort(key=lambda m: str(m.get("date") or ""), reverse=True)

            combined.products = all_prods
            combined.movements = all_movs
            combined.worksheets = all_worksheets
            combined.dynamic_columns = all_dyn_cols
            combined.dynamic_records = all_dyn_recs
            return combined

    def get_store(self, source_filter: str = "active") -> Optional[InventoryDataStore]:
        with self._lock:
            if not self.sources:
                if source_filter in ("all", "combined"):
                    return InventoryDataStore(source_id="all", name="All Sources (Combined)")
                return None

            # Support unified combined view across all uploaded workbooks and sheets
            if source_filter in ("all", "combined"):
                return self.get_combined_store()

            if source_filter == "active":
                if self.active_source_id and self.active_source_id in self.sources:
                    return self.sources[self.active_source_id]
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
            self._save_registry()
            return True

    def delete_source(self, source_id: str) -> bool:
        with self._lock:
            if source_id not in self.sources:
                return False
            store = self.sources.pop(source_id)

            # Clean up local file if it was an uploaded Excel workbook
            if store.source_type == "excel_upload" and store.spreadsheet_id.startswith("local_file:"):
                fpath = store.spreadsheet_id.split("local_file:", 1)[1]
                if os.path.exists(fpath):
                    try:
                        os.remove(fpath)
                    except Exception:
                        pass

            if self.active_source_id == source_id:
                self.active_source_id = next(iter(self.sources)) if self.sources else None
                if self.active_source_id:
                    self.sources[self.active_source_id].is_active = 1

            self._save_registry()
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
        time.sleep(2)
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

        if self._is_syncing:
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

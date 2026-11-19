import os
import json
import uuid
import time
import logging
import threading
import datetime
from typing import Dict, List, Any, Optional, Set
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
        self._active_syncing_sids: Set[str] = set()
        self.sync_history: List[Dict[str, Any]] = []

        # Caching for combined multi-source views to prevent redundant object churn
        self._cached_combined: Optional[InventoryDataStore] = None
        self._dirty_combined: bool = True

        # Restore all previously registered sources (Google Sheets & Excel) from disk
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
        if os.path.exists(reg_path):
            try:
                with open(reg_path, 'r', encoding='utf-8') as f:
                    records = json.load(f)

                reader = UniversalSpreadsheetReader()
                for r in records:
                    sid = r.get("source_id")
                    stype = r.get("source_type", "google_sheets")
                    name = r.get("name", "Restored Source")
                    period = r.get("period", "")
                    desc = r.get("description", "")
                    is_active = bool(r.get("is_active", False))
                    status = r.get("status", "active")

                    if stype == "google_sheets":
                        sheet_id = r.get("spreadsheet_id", "")
                        if sheet_id:
                            store = self.register_source(
                                name=name,
                                spreadsheet_url_or_id=sheet_id,
                                period=period,
                                description=desc,
                                source_type="google_sheets",
                                source_id=sid,
                                is_active=is_active
                            )
                            store.status = status
                            logger.info(f"Restored Google Sheets source '{name}' ({sid}).")

                    elif stype == "excel_upload":
                        clean_path = r.get("spreadsheet_id", "")
                        if clean_path.startswith("local_file:"):
                            clean_path = clean_path.split("local_file:", 1)[1]

                        if not os.path.exists(clean_path):
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
                                name=name,
                                spreadsheet_url_or_id=f"local_file:{clean_path}",
                                period=period,
                                description=desc,
                                source_type="excel_upload",
                                source_id=sid,
                                is_active=is_active
                            )
                            store.status = status
                            store.update_from_raw_sheets(raw_dict, period=period)
                            logger.info(f"Successfully restored persistent Excel source '{store.name}' ({sid}).")
                        except Exception as ex:
                            logger.warning(f"Could not restore source {sid}: {ex}")

            except Exception as e:
                logger.warning(f"Failed loading sources registry: {e}")

        # Auto-register environment variable source if configured and no source with that ID exists
        if Config.GOOGLE_SHEETS_SPREADSHEET_ID:
            clean_env_id = extract_spreadsheet_id(Config.GOOGLE_SHEETS_SPREADSHEET_ID)
            if clean_env_id and not any(s.spreadsheet_id == clean_env_id for s in self.sources.values()):
                self.register_source(
                    name="Google Sheet Live",
                    spreadsheet_url_or_id=clean_env_id,
                    source_type="google_sheets",
                    is_active=True
                )
                logger.info(f"Auto-registered default Google Sheets source from environment: {clean_env_id}")

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
            self._dirty_combined = True
            self._save_registry()
            return store

    def get_combined_store(self) -> InventoryDataStore:
        """Constructs a memory-cached, combined view across all registered and non-archived sources."""
        with self._lock:
            if not self._dirty_combined and self._cached_combined is not None:
                return self._cached_combined

            combined = InventoryDataStore(
                source_id="all",
                name="All Sources (Combined)",
                spreadsheet_id="all",
                source_type="combined"
            )
            all_prods = []
            all_movs = []
            all_worksheets = []
            all_dyn_cols: Dict[str, List[Dict[str, Any]]] = {}
            all_dyn_recs: Dict[str, List[Dict[str, Any]]] = {}

            for sid, store in self.sources.items():
                if store.status == "archived":
                    continue

                # Direct extension avoids duplicating tens of thousands of dict objects in RAM
                all_prods.extend(store.products)
                all_movs.extend(store.movements)
                all_worksheets.extend(store.worksheets)

                prefix = f"{store.name} - " if len(self.sources) > 1 else ""
                for sname, cols in store.dynamic_columns.items():
                    all_dyn_cols[f"{prefix}{sname}"] = cols

                for sname, recs in store.dynamic_records.items():
                    all_dyn_recs[f"{prefix}{sname}"] = recs

            # Sort and cap movements to 3000 max
            all_movs.sort(key=lambda m: str(m.get("date") or ""), reverse=True)
            combined.products = all_prods
            combined.movements = all_movs[:3000]
            combined.worksheets = all_worksheets
            combined.dynamic_columns = all_dyn_cols
            combined.dynamic_records = all_dyn_recs
            self._cached_combined = combined
            self._dirty_combined = False
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
            self._dirty_combined = True
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

            self._dirty_combined = True
            self._save_registry()
            return True

    def start_poller(self):
        with self._lock:
            if self._poller_thread and self._poller_thread.is_alive():
                return
            self._stop_event.clear()
            self._poller_thread = threading.Thread(target=self._poll_loop, daemon=True, name="GoogleSheetsSyncThread")
            self._poller_thread.start()
            logger.info(f"Started Google Sheets background sync worker with {self.sync_interval}s interval.")

    def stop_poller(self):
        self._stop_event.set()
        if self._poller_thread:
            self._poller_thread.join(timeout=2.0)

    def pause_sync(self):
        self._is_paused = True

    def resume_sync(self):
        self._is_paused = False

    def _poll_loop(self):
        time.sleep(1)
        while not self._stop_event.is_set():
            try:
                if not self._is_paused:
                    with self._lock:
                        g_sids = [
                            sid for sid, s in self.sources.items()
                            if s.source_type == "google_sheets" and s.status != "archived"
                        ]
                    for sid in g_sids:
                        if self._stop_event.is_set() or self._is_paused:
                            break
                        self.sync_source(sid)
            except Exception as e:
                logger.error(f"Error in background sync poll loop: {e}", exc_info=True)
            time.sleep(self.sync_interval)

    def sync_source(self, source_id: str = "active", force: bool = False) -> bool:
        if source_id in ("all", "combined"):
            with self._lock:
                g_sids = [sid for sid, s in self.sources.items() if s.source_type == "google_sheets" and s.status != "archived"]
            success = True
            for sid in g_sids:
                if not self.sync_source(sid, force=force):
                    success = False
            return success

        store = self.get_store(source_id)
        if not store:
            return False

        if store.source_type == "excel_upload":
            return True

        with self._lock:
            if store.source_id in self._active_syncing_sids and not force:
                return False
            self._active_syncing_sids.add(store.source_id)
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
            if sheet_title and store.name in ("Google Sheet", "Untitled Source", "Google Sheet Live", ""):
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
            with self._lock:
                self._active_syncing_sids.discard(store.source_id)
                self._is_syncing = bool(self._active_syncing_sids)
                self._dirty_combined = True
            import gc
            gc.collect()

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
        # Self-healing: if background poller thread stopped or was not started, revive it
        if not self._poller_thread or not self._poller_thread.is_alive():
            self.start_poller()

        with self._lock:
            if not self.sources:
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

            active_store = self.get_store("active")
            is_live = any(s.source_type == "google_sheets" and s.last_sync_status == "success" for s in self.sources.values())
            has_error = any(s.last_sync_status == "error" for s in self.sources.values())
            state = "paused" if self._is_paused else ("syncing" if self._is_syncing else ("connected" if is_live else ("error" if has_error else "demo")))

            all_sheets_status = []
            total_items = 0
            latest_success = None
            last_err = None

            for s in self.sources.values():
                total_items += len(s.products)
                if s.last_sync_at and (not latest_success or s.last_sync_at > latest_success):
                    latest_success = s.last_sync_at
                if s.last_sync_error:
                    last_err = s.last_sync_error
                for w in s.worksheets:
                    sheet_label = f"{s.name} - {w['sheet_name']}" if len(self.sources) > 1 else w["sheet_name"]
                    all_sheets_status.append({
                        "name": sheet_label,
                        "status": "success",
                        "row_count": w["row_count"],
                        "last_sync": s.last_sync_at,
                        "issues": w.get("issues", [])
                    })

            source_name = "All Connected Sheets" if len(self.sources) > 1 else (active_store.name if active_store else "Google Sheets")

            return {
                "state": state,
                "is_live_google_sheet": is_live,
                "is_paused": self._is_paused,
                "poll_interval_seconds": self.sync_interval,
                "lastSuccess": latest_success,
                "lastError": last_err,
                "source": source_name,
                "itemsSynced": total_items,
                "sheetsProcessed": len(all_sheets_status),
                "sheets": all_sheets_status,
                "nextSync": f"Every {self.sync_interval}s"
            }

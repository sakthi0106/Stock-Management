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

        # Track explicitly deleted source tombstones to prevent cold-boot resurrection
        self.deleted_source_ids: Set[str] = set()
        self._load_deleted()

        # Restore all previously registered sources permanently from disk
        self._load_registry()

    def _get_deleted_path(self) -> str:
        os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
        return os.path.join(Config.UPLOAD_FOLDER, "deleted_sources.json")

    def _load_deleted(self):
        try:
            dpath = self._get_deleted_path()
            if os.path.exists(dpath):
                with open(dpath, 'r', encoding='utf-8') as f:
                    self.deleted_source_ids = set(json.load(f))
        except Exception as e:
            logger.warning(f"Could not load deleted sources tombstones: {e}")

    def _save_deleted(self):
        try:
            dpath = self._get_deleted_path()
            with open(dpath, 'w', encoding='utf-8') as f:
                json.dump(list(self.deleted_source_ids), f)
        except Exception as e:
            logger.warning(f"Could not save deleted sources tombstones: {e}")

    def _get_registry_path(self) -> str:
        os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
        return os.path.join(Config.UPLOAD_FOLDER, "sources_registry.json")

    def _get_cache_path(self, source_id: str) -> str:
        os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
        return os.path.join(Config.UPLOAD_FOLDER, f"cache_{source_id}.json")

    def _save_source_cache(self, store: InventoryDataStore):
        """Saves a single source's parsed inventory and worksheet data to an isolated JSON cache.
        Using per-source files prevents large RAM allocations during serialization and keeps memory usage optimal.
        """
        try:
            cache_path = self._get_cache_path(store.source_id)
            payload = {
                "products": store.products,
                "movements": store.movements[:500],
                "worksheets": store.worksheets,
                "dynamic_columns": store.dynamic_columns,
                "last_sync_at": store.last_sync_at,
                "last_sync_status": store.last_sync_status,
                "last_sync_error": store.last_sync_error
            }
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(payload, f)
        except Exception as e:
            logger.warning(f"Could not save cache for source {store.source_id}: {e}")

    def _save_registry(self):
        """Persists source metadata to disk. Lightweight, fast, and does not duplicate inventory objects in RAM."""
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
                        "status": store.status,
                        "last_sync_at": store.last_sync_at,
                        "last_sync_status": store.last_sync_status,
                        "last_sync_error": store.last_sync_error,
                        "items_count": len(store.products),
                        "sheets_count": len(store.worksheets)
                    })
            with open(reg_path, 'w', encoding='utf-8') as f:
                json.dump(serializable, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not persist sources registry: {e}")

    def _load_registry(self):
        """Restores sources and full parsed product/sheet records on startup permanently from cache."""
        reg_path = self._get_registry_path()
        if os.path.exists(reg_path):
            try:
                with open(reg_path, 'r', encoding='utf-8') as f:
                    records = json.load(f)

                # Deduplicate records by spreadsheet_id, favoring the one with parsed data
                deduped = {}
                for r in records:
                    sheet_id = r.get("spreadsheet_id", "")
                    if sheet_id and sheet_id in deduped:
                        prev = deduped[sheet_id]
                        if r.get("sheets_count", 0) > prev.get("sheets_count", 0) or r.get("items_count", 0) > prev.get("items_count", 0):
                            deduped[sheet_id] = r
                    else:
                        deduped[sheet_id or r.get("source_id")] = r
                records = list(deduped.values())

                reader = UniversalSpreadsheetReader()
                for r in records:
                    sid = r.get("source_id")
                    sheet_id = r.get("spreadsheet_id", "")
                    if sid in self.deleted_source_ids or sheet_id in self.deleted_source_ids:
                        continue
                    stype = r.get("source_type", "google_sheets")
                    name = r.get("name", "Restored Source")
                    period = r.get("period", "")
                    desc = r.get("description", "")
                    is_active = bool(r.get("is_active", False))
                    status = r.get("status", "active")

                    store = self.register_source(
                        name=name,
                        spreadsheet_url_or_id=r.get("spreadsheet_id", ""),
                        period=period,
                        description=desc,
                        source_type=stype,
                        source_id=sid,
                        is_active=is_active
                    )
                    store.status = status
                    store.last_sync_at = r.get("last_sync_at")
                    store.last_sync_status = r.get("last_sync_status", "success")
                    store.last_sync_error = r.get("last_sync_error")

                    # Permanently restore from isolated per-source cache file
                    cache_path = self._get_cache_path(sid)
                    loaded_from_cache = False
                    if os.path.exists(cache_path):
                        try:
                            with open(cache_path, 'r', encoding='utf-8') as cf:
                                cdata = json.load(cf)
                            store.products = cdata.get("products", [])
                            store.movements = cdata.get("movements", [])
                            store.worksheets = cdata.get("worksheets", [])
                            store.dynamic_columns = cdata.get("dynamic_columns", {})
                            loaded_from_cache = bool(store.products or store.worksheets)
                            if loaded_from_cache:
                                logger.info(f"Permanently restored {len(store.products)} products for '{name}' ({sid}) from cache.")
                        except Exception as ce:
                            logger.warning(f"Could not load cache for {sid}: {ce}")

                    # Backwards compatibility: check if legacy registry had embedded products
                    if not loaded_from_cache and r.get("products"):
                        store.products = r.get("products", [])
                        store.movements = r.get("movements", [])
                        store.worksheets = r.get("worksheets", [])
                        store.dynamic_columns = r.get("dynamic_columns", {})
                        store.dynamic_records = r.get("dynamic_records", {})
                        self._save_source_cache(store)
                        loaded_from_cache = True

                    # If excel upload and no cache was found, try reading original excel file if it exists
                    if stype == "excel_upload" and not loaded_from_cache:
                        clean_path = r.get("spreadsheet_id", "")
                        if clean_path.startswith("local_file:"):
                            clean_path = clean_path.split("local_file:", 1)[1]

                        if os.path.exists(clean_path):
                            try:
                                extracted = reader.extract_from_excel(clean_path)
                                raw_dict = {sname: sdata.get('values', []) for sname, sdata in extracted.get('sheets', {}).items()}
                                store.update_from_raw_sheets(raw_dict, period=period)
                                self._save_source_cache(store)
                            except Exception as ex:
                                logger.warning(f"Could not re-parse excel {sid}: {ex}")

            except Exception as e:
                logger.warning(f"Failed loading sources registry: {e}")

        # Auto-register environment variable sources if configured
        if Config.GOOGLE_SHEETS_SPREADSHEET_ID:
            raw_ids = [s.strip() for s in Config.GOOGLE_SHEETS_SPREADSHEET_ID.split(',') if s.strip()]
            for idx, raw_id in enumerate(raw_ids):
                clean_env_id = extract_spreadsheet_id(raw_id)
                if clean_env_id and clean_env_id not in self.deleted_source_ids and not any(s.spreadsheet_id == clean_env_id for s in self.sources.values()):
                    default_name = f"Google Sheet {idx + 1}" if len(raw_ids) > 1 else "Google Sheet Live"
                    self.register_source(
                        name=default_name,
                        spreadsheet_url_or_id=clean_env_id,
                        source_type="google_sheets",
                        is_active=False
                    )
                    logger.info(f"Auto-registered Google Sheets source from environment: {clean_env_id}")

    def register_source(
        self,
        name: str,
        spreadsheet_url_or_id: str,
        period: str = "",
        description: str = "",
        source_type: str = "google_sheets",
        source_id: Optional[str] = None,
        is_active: bool = False
    ) -> InventoryDataStore:
        with self._lock:
            sid = source_id or f"src_{uuid.uuid4().hex[:8]}"
            clean_sheet_id = spreadsheet_url_or_id if source_type == "excel_upload" else extract_spreadsheet_id(spreadsheet_url_or_id)

            # If user explicitly registers anew, remove any past deletion tombstones
            if sid in self.deleted_source_ids:
                self.deleted_source_ids.discard(sid)
            if clean_sheet_id in self.deleted_source_ids:
                self.deleted_source_ids.discard(clean_sheet_id)
            self._save_deleted()

            # Deduplication: If a source with the exact same clean_sheet_id already exists in self.sources
            for existing_sid, existing_store in self.sources.items():
                if existing_store.spreadsheet_id == clean_sheet_id and (source_id is None or source_id == existing_sid):
                    if name and name not in ("Google Sheet", "Google Sheet Live", "Untitled Source"):
                        existing_store.name = name
                    if period:
                        existing_store.period = period
                    if description:
                        existing_store.description = description
                    if is_active:
                        for s in self.sources.values():
                            s.is_active = 0
                        existing_store.is_active = 1
                        self.active_source_id = existing_sid
                    self._dirty_combined = True
                    self._save_registry()
                    return existing_store

            store = InventoryDataStore(
                source_id=sid,
                name=name,
                spreadsheet_id=clean_sheet_id,
                source_type=source_type
            )
            store.period = period
            store.description = description

            if is_active:
                for s in self.sources.values():
                    s.is_active = 0
                store.is_active = 1
                self.active_source_id = sid
            else:
                store.is_active = 0
                if self.active_source_id == sid:
                    self.active_source_id = None

            self.sources[sid] = store
            self._dirty_combined = True
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

                all_prods.extend(store.products)
                all_movs.extend(store.movements)
                all_worksheets.extend(store.worksheets)

                prefix = f"{store.name} - " if len(self.sources) > 1 else ""
                for sname, cols in store.dynamic_columns.items():
                    all_dyn_cols[f"{prefix}{sname}"] = cols

                for sname, recs in store.dynamic_records.items():
                    all_dyn_recs[f"{prefix}{sname}"] = recs

            # Sort and cap movements to 1500 max to maintain low memory profile
            all_movs.sort(key=lambda m: str(m.get("date") or ""), reverse=True)
            combined.products = all_prods
            combined.movements = all_movs[:1500]
            combined.worksheets = all_worksheets
            combined.dynamic_columns = all_dyn_cols
            combined.dynamic_records = all_dyn_recs
            self._cached_combined = combined
            self._dirty_combined = False
            return combined

    def get_store(self, source_filter: str = "all") -> Optional[InventoryDataStore]:
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
                return self.get_combined_store()

            return self.sources.get(source_filter)

    def activate_source(self, source_id: str) -> bool:
        with self._lock:
            target_sid = source_id
            if target_sid not in self.sources:
                for sid, s in self.sources.items():
                    if s.spreadsheet_id == source_id:
                        target_sid = sid
                        break
            if target_sid not in self.sources:
                return False
            for sid, store in self.sources.items():
                store.is_active = 1 if sid == target_sid else 0
            self.active_source_id = target_sid
            self._dirty_combined = True
            self._save_registry()
            return True

    def deactivate_source(self, source_id: str) -> bool:
        with self._lock:
            target_sid = source_id
            if target_sid not in self.sources:
                for sid, s in self.sources.items():
                    if s.spreadsheet_id == source_id:
                        target_sid = sid
                        break
            if target_sid not in self.sources:
                return False
            self.sources[target_sid].is_active = 0
            if self.active_source_id == target_sid:
                self.active_source_id = None
            self._dirty_combined = True
            self._save_registry()
            return True

    def delete_source(self, source_id: str) -> bool:
        with self._lock:
            # Match by source_id or spreadsheet_id
            target_sid = source_id
            if target_sid not in self.sources:
                for sid, s in self.sources.items():
                    if s.spreadsheet_id == source_id:
                        target_sid = sid
                        break

            # Always record deletion tombstone so it cannot return on cold boot or restart
            self.deleted_source_ids.add(source_id)

            if target_sid not in self.sources:
                self._save_deleted()
                return True

            store = self.sources.pop(target_sid)
            self.deleted_source_ids.add(target_sid)
            # CRITICAL: ONLY tombstone spreadsheet_id if NO OTHER registered source is using it
            other_has_sheet = any(s.spreadsheet_id == store.spreadsheet_id for s in self.sources.values())
            if not other_has_sheet and store.spreadsheet_id:
                self.deleted_source_ids.add(store.spreadsheet_id)
            self._save_deleted()

            # Clean up local file if it was an uploaded Excel workbook
            if store.source_type == "excel_upload" and store.spreadsheet_id.startswith("local_file:"):
                fpath = store.spreadsheet_id.split("local_file:", 1)[1]
                # Only delete the file from disk if NO OTHER registered source is referencing it
                other_using = any(
                    s.source_id != target_sid and s.spreadsheet_id == store.spreadsheet_id
                    for s in self.sources.values()
                )
                if not other_using and os.path.exists(fpath):
                    try:
                        os.remove(fpath)
                    except Exception:
                        pass

            # Clean up persistent cache file
            cache_path = self._get_cache_path(target_sid)
            if os.path.exists(cache_path):
                try:
                    os.remove(cache_path)
                except Exception:
                    pass

            if self.active_source_id == target_sid:
                self.active_source_id = None

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

    def sync_source(self, source_id: str = "all", force: bool = False) -> bool:
        if source_id in ("all", "combined"):
            with self._lock:
                all_sids = list(self.sources.keys())
            success = True
            for sid in all_sids:
                if not self.sync_source(sid, force=force):
                    success = False
            return success

        store = self.get_store(source_id)
        if not store:
            return False

        if store.source_type == "excel_upload":
            # An uploaded Excel workbook's data is already resident in memory/cache.
            # Avoid re-reading large Excel files with openpyxl during sync when data is already resident.
            if not store.products:
                clean_path = store.spreadsheet_id
                if clean_path.startswith("local_file:"):
                    clean_path = clean_path.split("local_file:", 1)[1]
                if os.path.exists(clean_path):
                    try:
                        reader = UniversalSpreadsheetReader()
                        extracted = reader.extract_from_excel(clean_path)
                        raw_dict = {sname: sdata.get('values', []) for sname, sdata in extracted.get('sheets', {}).items()}
                        store.update_from_raw_sheets(raw_dict, period=store.period)
                        self._save_source_cache(store)
                        self._save_registry()
                        del extracted
                        del raw_dict
                        gc.collect()
                    except Exception as ex:
                        logger.warning(f"Excel sync notice for {store.source_id}: {ex}")
            store.last_sync_status = "success"
            store.last_sync_error = None
            self._record_run(store, "success", None)
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
            self._save_source_cache(store)
            self._save_registry()
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

            active_store = self.get_store("all")
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

            # Active 30-second Auto-Sync: if 30s elapsed since last sync, trigger background sync
            if is_live and not self._is_syncing and not self._is_paused:
                now_utc = datetime.datetime.now(datetime.timezone.utc)
                need_refresh = False
                if not latest_success:
                    need_refresh = True
                else:
                    try:
                        clean_ts = latest_success.replace('Z', '+00:00')
                        last_dt = datetime.datetime.fromisoformat(clean_ts)
                        if (now_utc - last_dt).total_seconds() >= self.sync_interval:
                            need_refresh = True
                    except Exception:
                        need_refresh = False
                if need_refresh:
                    threading.Thread(target=self.sync_source, args=("all", False), daemon=True).start()

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

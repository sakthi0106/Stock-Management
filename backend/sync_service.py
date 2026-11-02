import hashlib
import json
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

from config import Config
from sheets_client import GoogleSheetsClient
from sheet_analyzer import SheetAnalyzer
from inventory_service import InventoryService
import database

logger = logging.getLogger(__name__)


class SourceSyncState:
    """Holds per-source sync state: client, current service snapshot, lock, and metadata."""

    def __init__(self, source: Dict[str, Any]):
        self.source_id: str = source["source_id"]
        self.name: str = source.get("name", source["source_id"])
        self.spreadsheet_id: str = source.get("spreadsheet_id", "")
        self.period: str = source.get("period", "")
        self.poll_interval: int = max(30, source.get("poll_interval_seconds", 30))
        self.status: str = source.get("status", "active")

        self.client: Optional[GoogleSheetsClient] = None
        self._service: Optional[InventoryService] = None
        self._lock = threading.Lock()
        self._fingerprint: str = ""
        self.last_sync_at: Optional[str] = None
        self.last_error: Optional[str] = None
        self.sync_state: str = "pending"
        self.sheets_processed: int = 0
        self.sheet_statuses: List[Dict[str, Any]] = []

    def build_client(self) -> bool:
        """Instantiate a GoogleSheetsClient for this source's spreadsheet."""
        if not self.spreadsheet_id:
            return False
        try:
            self.client = GoogleSheetsClient(spreadsheet_id=self.spreadsheet_id)
            return True
        except Exception as e:
            logger.warning(f"[{self.source_id}] Could not build sheets client: {e}")
            return False

    def get_service(self) -> Optional[InventoryService]:
        with self._lock:
            return self._service

    def set_service(self, service: InventoryService, fingerprint: str, sheet_statuses: List[Dict], is_sync: bool = True):
        with self._lock:
            self._service = service
            self._fingerprint = fingerprint
            self.sheets_processed = len(sheet_statuses)
            self.sheet_statuses = sheet_statuses
            if is_sync:
                self.last_sync_at = datetime.now(timezone.utc).isoformat()
                self.sync_state = "success"
            else:
                self.last_sync_at = None
                self.sync_state = "connected"
            self.last_error = None

    @property
    def fingerprint(self) -> str:
        return self._fingerprint


class MultiSourceSyncService:
    """
    Manages multiple Google Spreadsheet sources independently.
    Each source has its own GoogleSheetsClient, InventoryService snapshot,
    sync lock, and fingerprint for change detection.
    """

    def __init__(self):
        self._sources: Dict[str, SourceSyncState] = {}
        self._sources_lock = threading.Lock()
        self._is_running = False
        self._poll_thread: Optional[threading.Thread] = None

        self._local_state: Optional[SourceSyncState] = None
        self._load_local_snapshot()
        self._initialize_sources()

    # ------------------------------------------------------------------ #
    #  Initialization                                                       #
    # ------------------------------------------------------------------ #

    def _load_local_snapshot(self):
        """Make the bundled Excel workbook available immediately at startup."""
        try:
            local_client = GoogleSheetsClient(local_only=True)
            active_src = database.get_active_source()
            source_id = active_src["source_id"] if active_src else "october-2026-master"
            period = active_src.get("period", "") if active_src else "2026-10"

            metadata = local_client.get_spreadsheet_metadata()
            sheet_names = [
                s.get("properties", {}).get("title", "")
                for s in metadata.get("sheets", [])
                if s.get("properties", {}).get("title")
            ]
            raw_data = local_client.get_batch_sheet_values(sheet_names)
            analysis = SheetAnalyzer(local_client).analyze_all_sheets(
                metadata, raw_data, {sn: [] for sn in sheet_names}
            )
            service = InventoryService(analysis, raw_data, source_id=source_id, period=period)

            dummy_src = {
                "source_id": source_id,
                "name": "Local Snapshot",
                "spreadsheet_id": "",
                "period": period,
                "poll_interval_seconds": 30,
                "status": "active",
            }
            state = SourceSyncState(dummy_src)
            sheet_statuses = [
                {
                    "name": sn,
                    "status": "success",
                    "row_count": len(raw_data.get(sn, [])),
                    "last_sync": None,
                    "issues": analysis["sheets"].get(sn, {}).get("issues", []),
                }
                for sn in sheet_names
            ]
            state.set_service(service, "", sheet_statuses, is_sync=False)
            self._local_state = state
            logger.info(
                f"Local snapshot loaded: {len(sheet_names)} sheets, "
                f"{len(service.products)} products, {len(service.movements)} movements."
            )
        except Exception as e:
            logger.exception(f"Could not load local snapshot: {e}")

    def _initialize_sources(self):
        """Load all non-disabled sources from DB and build their clients."""
        try:
            sources = database.list_sources(include_disabled=False)
            with self._sources_lock:
                for src in sources:
                    if src.get("status") == "disabled":
                        continue
                    state = SourceSyncState(src)
                    if src.get("spreadsheet_id"):
                        state.build_client()
                    if self._local_state and (src.get("is_active") or src["source_id"] == self._local_state.source_id):
                        local_svc = self._local_state.get_service()
                        if local_svc:
                            state.set_service(local_svc, "", self._local_state.sheet_statuses, is_sync=False)
                            state.sync_state = "connected"
                    self._sources[src["source_id"]] = state
            logger.info(f"Initialized {len(self._sources)} spreadsheet source(s) from database.")
        except Exception as e:
            logger.exception(f"Failed to initialize sources from DB: {e}")

    # ------------------------------------------------------------------ #
    #  Background Polling                                                   #
    # ------------------------------------------------------------------ #

    def start_background_poller(self):
        if self._is_running:
            return
        any_live = any(
            s.client and s.client.is_configured()
            for s in self._sources.values()
        )
        if not any_live:
            logger.info("No live Google Sheets configured; background poller not started.")
            return
        self._is_running = True
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()
        logger.info("Multi-source background poller started.")

    def stop_background_poller(self):
        self._is_running = False

    def _poll_loop(self):
        while self._is_running:
            try:
                with self._sources_lock:
                    source_ids = list(self._sources.keys())
                for sid in source_ids:
                    if not self._is_running:
                        break
                    try:
                        self.sync_source(sid)
                    except Exception as e:
                        logger.error(f"[{sid}] Unhandled sync error (continuing): {e}")
            except Exception as e:
                logger.error(f"Poll loop error: {e}")
            if self._is_running:
                time.sleep(max(30, Config.SYNC_INTERVAL_SECONDS))

    # ------------------------------------------------------------------ #
    #  Source Registration                                                  #
    # ------------------------------------------------------------------ #

    def register_source(self, source: Dict[str, Any]) -> bool:
        """Dynamically register a new source after DB creation."""
        sid = source.get("source_id", "")
        if not sid:
            return False
        state = SourceSyncState(source)
        if source.get("spreadsheet_id"):
            state.build_client()
        with self._sources_lock:
            self._sources[sid] = state
        logger.info(f"Registered new source in-memory: {sid}")
        return True

    def unregister_source(self, source_id: str):
        with self._sources_lock:
            self._sources.pop(source_id, None)

    def reload_sources(self):
        """Re-read all sources from DB and refresh in-memory registry."""
        try:
            sources = database.list_sources(include_disabled=False)
            new_states: Dict[str, SourceSyncState] = {}
            with self._sources_lock:
                for src in sources:
                    if src.get("status") == "disabled":
                        continue
                    sid = src["source_id"]
                    if sid in self._sources:
                        existing = self._sources[sid]
                        existing.name = src.get("name", sid)
                        existing.period = src.get("period", "")
                        existing.status = src.get("status", "active")
                        new_states[sid] = existing
                    else:
                        state = SourceSyncState(src)
                        if src.get("spreadsheet_id"):
                            state.build_client()
                        new_states[sid] = state
                self._sources = new_states
        except Exception as e:
            logger.exception(f"reload_sources failed: {e}")

    # ------------------------------------------------------------------ #
    #  Sync                                                                 #
    # ------------------------------------------------------------------ #

    def sync_source(self, source_id: str, force: bool = False) -> bool:
        """
        Synchronize a single source independently.
        One source failure does NOT affect others.
        """
        with self._sources_lock:
            state = self._sources.get(source_id)

        if state is None:
            logger.warning(f"sync_source called for unknown source: {source_id}")
            return False

        if state.status == "disabled":
            logger.debug(f"[{source_id}] Source disabled; skipping sync.")
            return False

        if not state.client or not state.client.is_configured():
            logger.debug(f"[{source_id}] No live client; skipping remote sync.")
            return state.get_service() is not None

        t_start = time.time()
        try:
            analyzer = SheetAnalyzer(state.client)
            metadata = state.client.get_spreadsheet_metadata()
            sheet_names = [
                s.get("properties", {}).get("title", "")
                for s in metadata.get("sheets", [])
                if s.get("properties", {}).get("title")
            ]
            raw_data = state.client.get_batch_sheet_values(sheet_names)
            raw_formulas = state.client.get_batch_sheet_formulas(sheet_names)
            analysis = analyzer.analyze_all_sheets(metadata, raw_data, raw_formulas)

            hasher = hashlib.sha256()
            sheet_statuses = []
            for sn in sheet_names:
                vals = raw_data.get(sn, [])
                hasher.update(json.dumps(vals, default=str, sort_keys=True).encode("utf-8"))
                sheet_statuses.append({
                    "name": sn,
                    "status": "success",
                    "row_count": len(vals),
                    "last_sync": datetime.now(timezone.utc).isoformat(),
                    "issues": analysis.get("sheets", {}).get(sn, {}).get("issues", []),
                })
            new_fp = hasher.hexdigest()

            if not force and new_fp == state.fingerprint and state.get_service() is not None:
                logger.debug(f"[{source_id}] Unchanged; skipping snapshot replacement.")
                return True

            service = InventoryService(
                analysis, raw_data,
                source_id=source_id,
                period=state.period
            )
            state.set_service(service, new_fp, sheet_statuses)

            duration_ms = int((time.time() - t_start) * 1000)

            database.save_sheets_and_mappings(source_id, analysis)
            database.replace_source_snapshot(
                source_id=source_id,
                period=state.period,
                products=service.products,
                movements=service.movements,
                fingerprint=new_fp
            )
            database.record_sync_run(
                status="success",
                sheets_processed=len(sheet_names),
                products_count=len(service.products),
                movements_count=len(service.movements),
                fingerprint=new_fp,
                source_id=source_id,
                source_name=state.name
            )
            database.record_audit(
                "SYNC_SUCCESS",
                f"[{source_id}] {len(sheet_names)} sheets, "
                f"{len(service.products)} products, {len(service.movements)} movements in {duration_ms}ms"
            )
            logger.info(
                f"[{source_id}] Sync complete — {len(sheet_names)} sheets, "
                f"{len(service.products)} products, {len(service.movements)} movements."
            )
            return True

        except Exception as e:
            err_msg = str(e)
            state.last_error = err_msg
            state.sync_state = "warning" if state.get_service() else "error"
            logger.warning(f"[{source_id}] Sync failed: {err_msg}. Keeping existing snapshot.")

            database.record_sync_run(
                status="warning",
                sheets_processed=state.sheets_processed,
                products_count=len(state.get_service().products) if state.get_service() else 0,
                movements_count=len(state.get_service().movements) if state.get_service() else 0,
                error_message=err_msg,
                source_id=source_id,
                source_name=state.name
            )
            return state.get_service() is not None

    def perform_sync(self, force: bool = False) -> bool:
        """Sync the active source — backwards-compatible with single-source SyncService."""
        active = database.get_active_source()
        if active:
            return self.sync_source(active["source_id"], force=force)
        with self._sources_lock:
            ids = list(self._sources.keys())
        return any(self.sync_source(sid, force=force) for sid in ids)

    # ------------------------------------------------------------------ #
    #  Service Access                                                       #
    # ------------------------------------------------------------------ #

    def get_service(self, source_filter: str = "active") -> Optional[InventoryService]:
        """
        Return an InventoryService for the given filter:
          "active"    → currently active source (fallback: local snapshot)
          "all"       → combined view of all non-disabled sources
          <source_id> → that specific source only
        """
        if source_filter == "active":
            active = database.get_active_source()
            sid = active["source_id"] if active else None
            if sid:
                with self._sources_lock:
                    state = self._sources.get(sid)
                if state and state.get_service():
                    return state.get_service()
            if self._local_state:
                return self._local_state.get_service()
            return None

        if source_filter == "all":
            return self._get_combined_service()

        with self._sources_lock:
            state = self._sources.get(source_filter)
        if state and state.get_service():
            return state.get_service()
        return self._local_state.get_service() if self._local_state else None

    def _get_combined_service(self) -> Optional[InventoryService]:
        """Merge data from all non-disabled sources into a synthetic InventoryService."""
        with self._sources_lock:
            states = list(self._sources.values())

        all_products: List[Dict[str, Any]] = []
        all_movements: List[Dict[str, Any]] = []

        for state in states:
            if state.status == "disabled":
                continue
            svc = state.get_service()
            if svc:
                all_products.extend(svc.products)
                all_movements.extend(svc.movements)

        if not all_products and self._local_state:
            svc = self._local_state.get_service()
            if svc:
                return svc

        if not all_products:
            return None

        combined = InventoryService.__new__(InventoryService)
        combined.source_id = "all"
        combined.period = ""
        combined.analysis = {}
        combined.raw_data = {}
        combined.products = all_products
        combined.movements = sorted(
            all_movements, key=lambda m: (m["date"], m.get("source_id", ""), m["product_id"])
        )
        combined.data_quality_issues = []
        return combined

    # ------------------------------------------------------------------ #
    #  Status                                                              #
    # ------------------------------------------------------------------ #

    def get_status(self, source_filter: str = "active") -> Dict[str, Any]:
        """Return sync status. Backwards-compatible with legacy SyncService.get_status()."""
        active = database.get_active_source()
        sid = active["source_id"] if active else None
        with self._sources_lock:
            state = self._sources.get(sid) if sid else None

        if state and (state.get_service() is not None or state.sheets_processed > 0):
            return {
                "state": state.sync_state if state.get_service() else "pending",
                "is_live_google_sheet": bool(state.client and state.client.is_configured()),
                "lastSuccess": state.last_sync_at,
                "lastError": state.last_error,
                "sheetsProcessed": state.sheets_processed,
                "sheets": state.sheet_statuses,
                "source_id": sid,
                "source_name": state.name,
            }

        local = self._local_state
        if local and local.get_service():
            return {
                "state": "connected",
                "is_live_google_sheet": False,
                "lastSuccess": local.last_sync_at,
                "lastError": None,
                "sheetsProcessed": local.sheets_processed,
                "sheets": local.sheet_statuses,
                "source_id": local.source_id,
                "source_name": "Local Snapshot",
            }

        return {
            "state": "error",
            "is_live_google_sheet": False,
            "lastSuccess": None,
            "lastError": "No service initialized",
            "sheetsProcessed": 0,
            "sheets": [],
        }

    def get_source_status(self, source_id: str) -> Dict[str, Any]:
        with self._sources_lock:
            state = self._sources.get(source_id)
        if not state:
            return {}
        return {
            "source_id": source_id,
            "name": state.name,
            "state": state.sync_state,
            "is_live": bool(state.client and state.client.is_configured()),
            "lastSuccess": state.last_sync_at,
            "lastError": state.last_error,
            "sheetsProcessed": state.sheets_processed,
            "sheets": state.sheet_statuses,
        }

    def get_all_source_statuses(self) -> List[Dict[str, Any]]:
        with self._sources_lock:
            sids = list(self._sources.keys())
        return [self.get_source_status(sid) for sid in sids]


# ------------------------------------------------------------------ #
#  Backwards-Compatible Alias                                          #
# ------------------------------------------------------------------ #

class SyncService(MultiSourceSyncService):
    """
    Drop-in replacement preserving the original SyncService(sheets_client) API.
    """

    def __init__(self, sheets_client: Optional[GoogleSheetsClient] = None):
        super().__init__()
        if sheets_client and sheets_client.is_configured():
            active = database.get_active_source()
            if active:
                sid = active["source_id"]
                with self._sources_lock:
                    state = self._sources.get(sid)
                if state:
                    state.client = sheets_client
                else:
                    dummy = {
                        "source_id": sid,
                        "name": active.get("name", sid),
                        "spreadsheet_id": active.get("spreadsheet_id", ""),
                        "period": active.get("period", ""),
                        "poll_interval_seconds": 30,
                        "status": "active",
                    }
                    s = SourceSyncState(dummy)
                    s.client = sheets_client
                    with self._sources_lock:
                        self._sources[sid] = s

    def get_service(self, source_filter: str = "active") -> Optional[InventoryService]:  # type: ignore[override]
        return super().get_service(source_filter)

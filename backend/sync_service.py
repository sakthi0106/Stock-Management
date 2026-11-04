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
    """Tracks state and service for an individual spreadsheet source."""
    def __init__(self, source_dict: Dict[str, Any], client: Optional[GoogleSheetsClient] = None):
        self.source = source_dict
        self.source_id = source_dict.get('source_id', '')
        self.client = client
        self._service: Optional[InventoryService] = None
        self._last_fingerprint = source_dict.get('fingerprint', '')
        self._last_sync_time = source_dict.get('last_sync_at')
        self._last_sync_status = source_dict.get('last_sync_status', 'pending')
        self._last_sync_error = source_dict.get('last_sync_error')
        self._is_syncing = False

    def build_client(self) -> GoogleSheetsClient:
        if self.client:
            return self.client
        sheet_id = self.source.get('spreadsheet_id', '')
        self.client = GoogleSheetsClient(spreadsheet_id=sheet_id)
        return self.client

    def get_service(self) -> Optional[InventoryService]:
        if not self._service:
            # Fallback to loading DB records for this source
            self._service = InventoryService(source_id=self.source_id, period=self.source.get('period', ''))
        return self._service

    def set_service(self, srv: InventoryService):
        self._service = srv

    @property
    def fingerprint(self) -> str:
        return self._last_fingerprint


class MultiSourceSyncService:
    """Manages multi-source inventory polling, sync and unified queries."""
    def __init__(self, default_client: Optional[GoogleSheetsClient] = None):
        self.default_client = default_client or GoogleSheetsClient()
        self._sources: Dict[str, SourceSyncState] = {}
        self._sources_lock = threading.RLock()
        self._poller_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._local_state: Optional[SourceSyncState] = None

        self._initialize_sources()
        self._load_local_snapshot()

    def _load_local_snapshot(self):
        try:
            local_client = GoogleSheetsClient(local_only=True)
            active_src = database.get_active_source()
            source_id = active_src['source_id'] if active_src else 'october-2026-master'
            period = active_src.get('period', '') if active_src else '2026-10'

            metadata = local_client.get_spreadsheet_metadata()
            sheets_info = metadata.get('sheets', [])
            sheet_names = [
                s.get('properties', {}).get('title', '')
                for s in sheets_info
                if s.get('properties', {}).get('title')
            ]

            raw_data = local_client.get_batch_sheet_values(sheet_names)
            analyzer = SheetAnalyzer(local_client)
            analysis = analyzer.analyze_all_sheets(metadata=metadata, raw_values=raw_data, raw_formulas={sn: [] for sn in sheet_names})

            srv = InventoryService(analysis_report=analysis, raw_sheets_data=raw_data, source_id=source_id, period=period)
            self._local_state = SourceSyncState({'source_id': source_id, 'name': 'Local Snapshot', 'period': period}, local_client)
            self._local_state.set_service(srv)
            logger.info(f"Loaded local snapshot with {len(srv.products)} products and {len(srv.movements)} movements.")
        except Exception as e:
            logger.warning(f"Could not load local snapshot: {e}. Falling back to DB inventory.")
            srv = InventoryService(source_id='default_source')
            self._local_state = SourceSyncState({'source_id': 'default_source', 'name': 'Database Snapshot'}, None)
            self._local_state.set_service(srv)

    def _initialize_sources(self):
        with self._sources_lock:
            sources = database.list_sources(include_disabled=False)
            for s in sources:
                sid = s['source_id']
                client = self.default_client if s.get('is_active') and self.default_client.spreadsheet_id == s.get('spreadsheet_id') else None
                self._sources[sid] = SourceSyncState(s, client)

    def start_background_poller(self):
        if self._poller_thread and self._poller_thread.is_alive():
            return
        self._stop_event.clear()
        self._poller_thread = threading.Thread(target=self._poll_loop, daemon=True, name="SyncPollerThread")
        self._poller_thread.start()
        logger.info("Started background inventory synchronization poller.")

    def stop_background_poller(self):
        self._stop_event.set()
        if self._poller_thread:
            self._poller_thread.join(timeout=3.0)

    def _poll_loop(self):
        while not self._stop_event.is_set():
            try:
                active_src = database.get_active_source()
                if active_src:
                    self.sync_source(active_src['source_id'], force=False)
            except Exception as e:
                logger.error(f"Error in background sync loop: {e}")
            time.sleep(Config.SYNC_INTERVAL_SECONDS)

    def register_source(self, source_dict: Dict[str, Any]):
        with self._sources_lock:
            sid = source_dict['source_id']
            self._sources[sid] = SourceSyncState(source_dict)

    def unregister_source(self, source_id: str):
        with self._sources_lock:
            self._sources.pop(source_id, None)

    def reload_sources(self):
        self._initialize_sources()

    def sync_source(self, source_id: str, force: bool = False) -> Tuple[bool, Dict[str, Any]]:
        with self._sources_lock:
            state = self._sources.get(source_id)
            if not state:
                src_dict = database.get_source(source_id)
                if not src_dict:
                    return False, {"error": "Source not found"}
                state = SourceSyncState(src_dict)
                self._sources[source_id] = state

        if state._is_syncing and not force:
            return False, {"status": "already_syncing"}

        state._is_syncing = True
        try:
            client = state.build_client()
            metadata = client.get_spreadsheet_metadata()
            sheets_info = metadata.get('sheets', [])
            sheet_names = [
                s.get('properties', {}).get('title', '')
                for s in sheets_info
                if s.get('properties', {}).get('title')
            ]

            raw_data = client.get_batch_sheet_values(sheet_names)

            # Compute fingerprint
            fp_hasher = hashlib.md5()
            for sname in sorted(raw_data.keys()):
                fp_hasher.update(sname.encode('utf-8'))
                for r in raw_data[sname]:
                    fp_hasher.update(str(r).encode('utf-8'))
            fingerprint = fp_hasher.hexdigest()

            if not force and fingerprint == state.fingerprint:
                state._last_sync_time = datetime.now(timezone.utc).isoformat()
                state._last_sync_status = "success"
                return True, {"status": "unchanged", "fingerprint": fingerprint}

            analyzer = SheetAnalyzer(client)
            analysis = analyzer.analyze_all_sheets(metadata=metadata, raw_values=raw_data)

            database.save_sheets_and_mappings(source_id, list(analysis.get('sheets', {}).values()))

            srv = InventoryService(
                analysis_report=analysis,
                raw_sheets_data=raw_data,
                source_id=source_id,
                period=state.source.get('period', '')
            )
            state.set_service(srv)

            # Persist to SQLite
            database.replace_source_snapshot(
                source_id=source_id,
                period=state.source.get('period', ''),
                products=srv.products,
                movements=srv.movements,
                fingerprint=fingerprint
            )

            database.record_sync_run(
                status="success",
                sheets_processed=len(analysis.get('sheets', {})),
                products_count=len(srv.products),
                movements_count=len(srv.movements),
                fingerprint=fingerprint,
                source_id=source_id,
                source_name=state.source.get('name')
            )

            state._last_fingerprint = fingerprint
            state._last_sync_time = datetime.now(timezone.utc).isoformat()
            state._last_sync_status = "success"
            state._last_sync_error = None

            return True, {
                "status": "success",
                "products_count": len(srv.products),
                "movements_count": len(srv.movements),
                "fingerprint": fingerprint
            }
        except Exception as e:
            logger.error(f"Sync failed for source '{source_id}': {e}")
            state._last_sync_status = "error"
            state._last_sync_error = str(e)
            database.record_sync_run(
                status="error",
                sheets_processed=0,
                products_count=0,
                movements_count=0,
                error_message=str(e),
                source_id=source_id,
                source_name=state.source.get('name')
            )
            return False, {"status": "error", "error": str(e)}
        finally:
            state._is_syncing = False

    def perform_sync(self, source_id: str = "active", force: bool = True) -> Tuple[bool, Dict[str, Any]]:
        if source_id == "active":
            active_src = database.get_active_source()
            sid = active_src['source_id'] if active_src else "default_source"
        else:
            sid = source_id
        return self.sync_source(sid, force=force)

    def get_service(self, source_filter: str = "active") -> Optional[InventoryService]:
        if source_filter == "active":
            active_src = database.get_active_source()
            sid = active_src['source_id'] if active_src else None
            if sid:
                with self._sources_lock:
                    state = self._sources.get(sid)
                    if state and state.get_service():
                        return state.get_service()
            if self._local_state and self._local_state.get_service():
                return self._local_state.get_service()
            return InventoryService(source_id="default_source")

        if source_filter == "all":
            return self._get_combined_service()

        with self._sources_lock:
            state = self._sources.get(source_filter)
            if state and state.get_service():
                return state.get_service()

        if self._local_state and self._local_state.get_service():
            return self._local_state.get_service()
        return InventoryService(source_id=source_filter)

    def _get_combined_service(self) -> InventoryService:
        combined = InventoryService(source_id="all")
        with self._sources_lock:
            for s in self._sources.values():
                srv = s.get_service()
                if srv:
                    combined.products.extend(srv.products)
                    combined.movements.extend(srv.movements)
        if not combined.products and self._local_state:
            srv = self._local_state.get_service()
            if srv:
                combined.products.extend(srv.products)
                combined.movements.extend(srv.movements)
        return combined

    def get_status(self) -> Dict[str, Any]:
        active_src = database.get_active_source()
        srv = self.get_service("active")
        is_live = False
        sheets = []
        if active_src:
            sid = active_src['source_id']
            sheets_data = database.get_sheets_for_source(sid)
            for s in sheets_data:
                issues = []
                try:
                    issues = json.loads(s.get("issues_json") or "[]")
                except Exception:
                    pass
                sheets.append({
                    "name": s.get("sheet_name", ""),
                    "status": s.get("status", "success"),
                    "row_count": s.get("row_count", 0),
                    "last_sync": s.get("last_sync_at"),
                    "issues": issues
                })
            with self._sources_lock:
                st = self._sources.get(sid)
                if st and st.client and st.client.is_configured():
                    is_live = True

        return {
            "state": "connected" if is_live else "demo",
            "is_live_google_sheet": is_live,
            "lastSuccess": active_src.get('last_sync_at') if active_src else None,
            "lastError": active_src.get('last_sync_error') if active_src else None,
            "source": active_src.get('name', 'Default Source') if active_src else "Primary Stock Sheet",
            "itemsSynced": len(srv.products) if srv else 0,
            "sheetsProcessed": len(sheets),
            "sheets": sheets,
            "nextSync": None
        }

    def get_source_status(self, source_id: str) -> Dict[str, Any]:
        with self._sources_lock:
            state = self._sources.get(source_id)
            if state:
                return {
                    "source_id": source_id,
                    "status": state._last_sync_status,
                    "last_sync_at": state._last_sync_time,
                    "error": state._last_sync_error
                }
        src = database.get_source(source_id)
        if src:
            return {
                "source_id": source_id,
                "status": src.get('last_sync_status', 'pending'),
                "last_sync_at": src.get('last_sync_at'),
                "error": src.get('last_sync_error')
            }
        return {"source_id": source_id, "status": "unknown"}

    def get_all_source_statuses(self) -> List[Dict[str, Any]]:
        sources = database.list_sources(include_disabled=True)
        return [self.get_source_status(s['source_id']) for s in sources]


class SyncService(MultiSourceSyncService):
    """Backwards compatible alias for MultiSourceSyncService."""
    def __init__(self, default_client: Optional[GoogleSheetsClient] = None):
        super().__init__(default_client=default_client)

import os
import hashlib
import json
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple
from config import Config
from sheets_client import GoogleSheetsClient
from inventory_service import InventoryService
from pipeline import UnifiedDataPipeline
from spreadsheet_reader import UniversalSpreadsheetReader
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
            self._service = InventoryService(source_id=self.source_id, period=self.source.get('period', ''))
        return self._service

    def set_service(self, srv: InventoryService):
        self._service = srv

    @property
    def fingerprint(self) -> str:
        return self._last_fingerprint


class MultiSourceSyncService:
    """Manages multi-source inventory polling, 15-second sync, and unified pipeline processing."""
    def __init__(self, default_client: Optional[GoogleSheetsClient] = None):
        self.default_client = default_client or GoogleSheetsClient()
        self._sources: Dict[str, SourceSyncState] = {}
        self._sources_lock = threading.RLock()
        self._poller_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._is_paused = False
        self._instance_last_success: Optional[str] = None
        self.pipeline = UnifiedDataPipeline()

        self._initialize_sources()

    def _initialize_sources(self):
        with self._sources_lock:
            sources = database.list_sources(include_disabled=False)
            if not sources and Config.GOOGLE_SHEETS_SPREADSHEET_ID:
                try:
                    default_src = database.create_source(
                        name="Stock Data",
                        spreadsheet_url_or_id=Config.GOOGLE_SHEETS_SPREADSHEET_ID,
                        period="2026-10",
                        description="Default Google Sheets Stock Register",
                        status="active",
                        is_active=True
                    )
                    sources = [default_src]
                    logger.info(f"Auto-registered default Google Sheet source: {default_src['source_id']}")
                except Exception as e:
                    logger.warning(f"Could not auto-register default Google Sheet: {e}")

            for s in sources:
                sid = s['source_id']
                client = self.default_client if s.get('is_active') and getattr(self.default_client, 'spreadsheet_id', '') == s.get('spreadsheet_id') else None
                self._sources[sid] = SourceSyncState(s, client)

    def start_background_poller(self):
        """Starts persistent background worker polling all active sources every 15 seconds."""
        if self._poller_thread and self._poller_thread.is_alive():
            return
        self._stop_event.clear()
        self._poller_thread = threading.Thread(target=self._poll_loop, daemon=True, name="SyncPollerThread")
        self._poller_thread.start()
        logger.info(f"Started persistent background inventory poller ({Config.SYNC_INTERVAL_SECONDS}s interval).")

    def stop_background_poller(self):
        self._stop_event.set()
        if self._poller_thread:
            self._poller_thread.join(timeout=3.0)

    def pause_sync(self):
        self._is_paused = True
        logger.info("Automatic 15-second synchronization paused by administrator.")

    def resume_sync(self):
        self._is_paused = False
        logger.info("Automatic 15-second synchronization resumed by administrator.")

    def is_paused(self) -> bool:
        return self._is_paused

    def _poll_loop(self):
        # Immediate initial sync run upon worker startup so data is ready right away
        if not self._is_paused and not self._stop_event.is_set():
            try:
                active_sources = database.get_active_and_enabled_sources()
                for src in active_sources:
                    sid = src.get('source_id')
                    if src.get('source_type') != 'excel_upload':
                        self.sync_source(sid, force=False)
            except Exception as e:
                logger.error(f"Error in initial startup background sync: {e}", exc_info=True)

        while not self._stop_event.is_set():
            # Wait for interval or immediate wake up on shutdown/stop_event
            if self._stop_event.wait(timeout=Config.SYNC_INTERVAL_SECONDS):
                break
            if not self._is_paused and not self._stop_event.is_set():
                try:
                    # Discover all active, explicitly registered sources
                    active_sources = database.get_active_and_enabled_sources()
                    for src in active_sources:
                        sid = src.get('source_id')
                        # Sync Google Sheets sources automatically every 15 seconds
                        if src.get('source_type') != 'excel_upload':
                            self.sync_source(sid, force=False)
                except Exception as e:
                    logger.error(f"Error in 15-second background sync loop: {e}", exc_info=True)

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
        """Synchronizes an active registered spreadsheet source using the UnifiedDataPipeline."""
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
            spreadsheet_ref = state.source.get('spreadsheet_id', '')
            raw_data: Dict[str, List[List[Any]]] = {}

            if state.source.get('source_type') == 'excel_upload' or spreadsheet_ref.startswith('local_file:'):
                file_path = spreadsheet_ref.replace('local_file:', '')
                if not os.path.exists(file_path):
                    uploads_dir = os.path.join(os.path.dirname(__file__), "uploads")
                    possible = os.path.join(uploads_dir, os.path.basename(file_path))
                    if os.path.exists(possible):
                        file_path = possible
                reader = UniversalSpreadsheetReader()
                excel_extracted = reader.extract_from_excel(file_path)
                for sname, sinfo in excel_extracted.get("sheets", {}).items():
                    raw_data[sname] = sinfo.get("values", [])
            else:
                client = state.build_client()
                metadata = client.get_spreadsheet_metadata()
                sheets_info = metadata.get('sheets', [])
                sheet_names = [
                    s.get('properties', {}).get('title', '')
                    for s in sheets_info
                    if s.get('properties', {}).get('title')
                ]
                raw_data = client.get_batch_sheet_values(sheet_names)

            # Compute content hash / fingerprint for change detection
            fp_hasher = hashlib.md5()
            for sname in sorted(raw_data.keys()):
                fp_hasher.update(sname.encode('utf-8'))
                for r in raw_data[sname]:
                    fp_hasher.update(str(r).encode('utf-8'))
            fingerprint = fp_hasher.hexdigest()

            # Skip unchanged sheets unless forced
            if not force and fingerprint == state.fingerprint:
                state._last_sync_time = datetime.now(timezone.utc).isoformat()
                state._last_sync_status = "success"
                return True, {"status": "unchanged", "fingerprint": fingerprint}

            # Run Unified Data Pipeline
            pipeline_res = self.pipeline.process_and_persist(
                source_id=source_id,
                raw_sheets_dict=raw_data,
                fingerprint=fingerprint,
                period=state.source.get('period', '')
            )

            # Update in-memory InventoryService for live fast query responses
            srv = InventoryService(
                source_id=source_id,
                period=state.source.get('period', '')
            )
            state.set_service(srv)

            # Record sync run in audit and history
            database.record_sync_run(
                status="success",
                sheets_processed=pipeline_res["total_sheets"],
                products_count=pipeline_res["total_inventory_records"],
                movements_count=pipeline_res["total_stock_movements"],
                fingerprint=fingerprint,
                source_id=source_id,
                source_name=state.source.get('name')
            )

            state._last_fingerprint = fingerprint
            state._last_sync_time = datetime.now(timezone.utc).isoformat()
            state._last_sync_status = "success"
            state._last_sync_error = None
            self._instance_last_success = state._last_sync_time

            return True, {
                "status": "success",
                "products_count": pipeline_res["total_inventory_records"],
                "movements_count": pipeline_res["total_stock_movements"],
                "total_sheets": pipeline_res["total_sheets"],
                "fingerprint": fingerprint
            }
        except Exception as e:
            logger.error(f"Sync failed for source '{source_id}': {e}", exc_info=True)
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
                return InventoryService(source_id=sid)
            return InventoryService(source_id="")

        if source_filter == "all":
            return self._get_combined_service()

        with self._sources_lock:
            state = self._sources.get(source_filter)
            if state and state.get_service():
                return state.get_service()

        return InventoryService(source_id=source_filter)

    def _get_combined_service(self) -> InventoryService:
        combined = InventoryService(source_id="all")
        with self._sources_lock:
            for s in self._sources.values():
                srv = s.get_service()
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
            sheets_data = database.get_worksheet_metadata(sid)
            for s in sheets_data:
                summary = s.get("summary", {})
                issues = summary.get("quality_issues", [])
                sheets.append({
                    "name": s.get("sheet_name", ""),
                    "status": s.get("analysis_status", "success"),
                    "row_count": s.get("row_count", 0),
                    "last_sync": s.get("updated_at"),
                    "issues": issues
                })
            with self._sources_lock:
                st = self._sources.get(sid)
                if st and st.client and st.client.is_configured():
                    is_live = True

        return {
            "state": "connected" if is_live else ("paused" if self._is_paused else "demo"),
            "is_live_google_sheet": is_live,
            "is_paused": self._is_paused,
            "poll_interval_seconds": Config.SYNC_INTERVAL_SECONDS,
            "lastSuccess": self._instance_last_success or (active_src.get('last_sync_at') if active_src else None),
            "lastError": active_src.get('last_sync_error') if active_src else None,
            "source": active_src.get('name', 'Default Source') if active_src else "Primary Stock Sheet",
            "itemsSynced": len(srv.products) if srv else 0,
            "sheetsProcessed": len(sheets),
            "sheets": sheets,
            "nextSync": f"Every {Config.SYNC_INTERVAL_SECONDS} seconds"
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

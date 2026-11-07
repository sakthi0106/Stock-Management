"""
Standalone Persistent Background Worker for Google Sheets Synchronization.
Runs independently of Flask web request threads.
Ideal for Render Background Worker service deployments or standalone server daemons.
"""

import sys
import os
import time
import logging

# Ensure backend directory is in path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from config import Config
import database
from sheets_client import GoogleSheetsClient
from sync_service import SyncService

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] [SyncWorker] %(message)s'
)
logger = logging.getLogger('worker')


def run_worker():
    logger.info("Initializing Render Persistent Background Worker...")
    database.init_db()

    sheets_client = GoogleSheetsClient()
    sync_service = SyncService(sheets_client)

    interval = max(10, Config.SYNC_INTERVAL_SECONDS)
    logger.info(f"Worker running. Automatic synchronization interval: {interval} seconds.")

    while True:
        try:
            if not sync_service.is_paused():
                active_sources = database.get_active_and_enabled_sources()
                for src in active_sources:
                    sid = src.get('source_id')
                    # Automatic sync for registered Google Sheets
                    if src.get('source_type') != 'excel_upload':
                        logger.info(f"Checking Google Spreadsheet source '{src.get('name')}' ({sid})...")
                        ok, res = sync_service.sync_source(sid, force=False)
                        if ok and res.get('status') == 'success':
                            logger.info(f"Synced source '{sid}': {res.get('products_count')} items, {res.get('movements_count')} movements.")
                        elif not ok:
                            logger.warning(f"Sync issue on source '{sid}': {res.get('error')}")
        except KeyboardInterrupt:
            logger.info("Worker stopped by user.")
            break
        except Exception as e:
            logger.error(f"Unexpected error in worker loop: {e}", exc_info=True)

        time.sleep(interval)


if __name__ == '__main__':
    run_worker()

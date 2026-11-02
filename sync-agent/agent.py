"""
Enterprise On-Premise LAN Excel Synchronization Agent
=====================================================
Runs inside the company private network on an approved, always-on server or computer.
Watches the company's shared Excel workbook, detects changes via SHA-256, handles
temporary Excel file locks gracefully, and initiates authenticated outbound HTTPS POST
requests to the cloud backend.

Zero inbound ports or SMB shares are exposed to the public internet.
"""

import os
import sys
import time
import json
import logging
import hashlib
import shutil
import tempfile
import argparse
import requests
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [SyncAgent] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger("SyncAgent")

DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

def load_config(config_path: str) -> dict:
    if not os.path.exists(config_path):
        logger.warning(f"Config file not found at {config_path}. Using fallback defaults.")
        return {
            "backend_url": "http://127.0.0.1:8000",
            "agent_api_key": "corp-sync-agent-secret-auth-token-2026",
            "excel_file_path": "../sample-data/company_inventory_master.xlsx",
            "poll_interval_seconds": 60,
            "max_lock_retries": 5,
            "lock_retry_delay_seconds": 3
        }
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)

def compute_file_hash(filepath: str, max_retries: int = 5, retry_delay: int = 3) -> tuple[str, bytes]:
    """
    Reads file safely even if an employee currently has it open in Microsoft Excel.
    Creates a temporary shadow copy to avoid WinError 32 (file sharing violation).
    """
    for attempt in range(1, max_retries + 1):
        try:
            # Create a shadow copy in temp directory
            with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
                temp_path = tmp.name

            # Copy file to temp location
            shutil.copy2(filepath, temp_path)
            
            with open(temp_path, "rb") as f:
                data = f.read()

            try:
                os.remove(temp_path)
            except Exception:
                pass

            file_hash = hashlib.sha256(data).hexdigest()
            return file_hash, data

        except PermissionError as pe:
            logger.warning(f"File locked by Excel (Attempt {attempt}/{max_retries}): {pe}. Retrying in {retry_delay}s...")
            time.sleep(retry_delay)
        except Exception as e:
            logger.error(f"Error reading file {filepath}: {e}")
            raise e

    raise TimeoutError(f"Could not read {filepath} after {max_retries} attempts due to file lock.")

def sync_file_to_cloud(config: dict, last_hash: str, config_dir: str = "") -> str:
    raw_path = config["excel_file_path"]
    if not os.path.isabs(raw_path) and config_dir:
        filepath = os.path.abspath(os.path.join(config_dir, raw_path))
    else:
        filepath = os.path.abspath(raw_path)
    if not os.path.exists(filepath):
        logger.error(f"Target Excel file does not exist at: {filepath}")
        return last_hash

    try:
        current_hash, file_bytes = compute_file_hash(
            filepath,
            max_retries=config.get("max_lock_retries", 5),
            retry_delay=config.get("lock_retry_delay_seconds", 3)
        )
    except Exception as e:
        logger.error(f"Failed to access workbook: {e}")
        return last_hash

    if current_hash == last_hash:
        logger.info(f"Workbook unchanged (SHA-256: {current_hash[:12]}...). Skipping sync.")
        return last_hash

    logger.info(f"Detected workbook change! New hash: {current_hash[:12]}... Pushing to cloud...")
    
    backend_url = config["backend_url"].rstrip("/") + "/api/v1/sync/agent-push"
    headers = {
        "X-Agent-Key": config["agent_api_key"]
    }
    files = {
        "file": (os.path.basename(filepath), file_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    }

    try:
        resp = requests.post(backend_url, headers=headers, files=files, timeout=30)
        if resp.status_code == 200:
            result = resp.json()
            logger.info(f"Sync successfully accepted by cloud backend! Result: {result.get('message')}")
            return current_hash
        else:
            logger.error(f"Cloud backend returned error {resp.status_code}: {resp.text}")
            return last_hash
    except Exception as e:
        logger.error(f"Network error connecting to cloud backend ({backend_url}): {e}")
        return last_hash

def main():
    parser = argparse.ArgumentParser(description="Secure On-Premise LAN Excel Sync Agent")
    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="Path to config JSON")
    parser.add_argument("--once", action="store_true", help="Run once and exit (for Windows Scheduled Tasks)")
    parser.add_argument("--file", help="Override path to Excel workbook")
    args = parser.parse_args()

    config = load_config(args.config)
    if args.file:
        config["excel_file_path"] = args.file

    config_dir = os.path.dirname(os.path.abspath(args.config))
    raw_path = config["excel_file_path"]
    resolved_path = os.path.abspath(os.path.join(config_dir, raw_path)) if not os.path.isabs(raw_path) else os.path.abspath(raw_path)

    logger.info("=" * 60)
    logger.info("Starting Secure Excel Sync Agent")
    logger.info(f"Target Workbook: {resolved_path}")
    logger.info(f"Cloud Endpoint:  {config['backend_url']}")
    logger.info("=" * 60)

    last_hash = ""

    if args.once:
        sync_file_to_cloud(config, last_hash, config_dir=config_dir)
        return

    poll_interval = config.get("poll_interval_seconds", 60)
    logger.info(f"Running in daemon mode. Polling every {poll_interval} seconds...")
    try:
        while True:
            last_hash = sync_file_to_cloud(config, last_hash, config_dir=config_dir)
            time.sleep(poll_interval)
    except KeyboardInterrupt:
        logger.info("Sync agent stopped by user.")

if __name__ == "__main__":
    main()

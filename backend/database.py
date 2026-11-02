import re
import sqlite3
import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple, Union
from config import Config

logger = logging.getLogger(__name__)

def get_db_connection():
    conn = sqlite3.connect(Config.DATABASE_PATH, timeout=20.0)
    conn.row_factory = sqlite3.Row
    return conn

def extract_spreadsheet_id(input_str: str) -> str:
    """Extract clean Google Spreadsheet ID from raw ID, full Google Sheets URL, or local file."""
    if not input_str:
        return ""
    cleaned = input_str.strip().strip('"').strip("'")
    if cleaned.startswith("local_file:"):
        return cleaned
    match = re.search(r'/spreadsheets/d/([a-zA-Z0-9-_]+)', cleaned)
    if match:
        return match.group(1)
    if "/" not in cleaned and "\\" not in cleaned and len(cleaned) > 10:
        return cleaned
    return cleaned

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Registered Spreadsheet Sources
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS spreadsheet_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            spreadsheet_id TEXT NOT NULL,
            description TEXT DEFAULT '',
            period TEXT DEFAULT '',
            status TEXT DEFAULT 'active', -- 'active', 'archived', 'disabled'
            is_active INTEGER DEFAULT 0,  -- 1 for currently active live spreadsheet
            poll_interval_seconds INTEGER DEFAULT 30,
            last_sync_at TEXT,
            last_sync_status TEXT DEFAULT 'pending', -- 'success', 'warning', 'error', 'pending'
            last_sync_error TEXT,
            fingerprint TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    ''')

    # 2. Discovered Sheets per Spreadsheet Source
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS spreadsheet_sheets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT NOT NULL,
            sheet_name TEXT NOT NULL,
            sheet_index INTEGER DEFAULT 0,
            row_count INTEGER DEFAULT 0,
            col_count INTEGER DEFAULT 0,
            data_start_row INTEGER DEFAULT 3,
            status TEXT DEFAULT 'success',
            last_sync_at TEXT,
            issues_json TEXT DEFAULT '[]',
            UNIQUE(source_id, sheet_name)
        )
    ''')

    # 3. Independent Column Mappings per Worksheet
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sheet_column_mappings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT NOT NULL,
            sheet_name TEXT NOT NULL,
            part_no_col TEXT,
            desc_col TEXT,
            cat_col TEXT,
            uom_col TEXT,
            unit_price_col TEXT,
            monthly_open_col TEXT,
            closing_col TEXT,
            amount_cols_json TEXT DEFAULT '[]',
            date_columns_json TEXT DEFAULT '[]',
            extra_mappings_json TEXT DEFAULT '{}',
            updated_at TEXT NOT NULL,
            UNIQUE(source_id, sheet_name)
        )
    ''')

    # 4. Synchronization History / Runs
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sync_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT NOT NULL,
            source_name TEXT,
            timestamp TEXT NOT NULL,
            status TEXT NOT NULL,
            sheets_processed INTEGER DEFAULT 0,
            products_imported INTEGER DEFAULT 0,
            movements_imported INTEGER DEFAULT 0,
            fingerprint TEXT DEFAULT '',
            duration_ms INTEGER DEFAULT 0,
            error_message TEXT
        )
    ''')

    # Legacy support table alias
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sync_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            status TEXT NOT NULL,
            sheets_processed INTEGER DEFAULT 0,
            products_count INTEGER DEFAULT 0,
            movements_count INTEGER DEFAULT 0,
            fingerprint TEXT,
            error_message TEXT
        )
    ''')

    # 5. Normalized Inventory Records (Google Sheets remains source of truth)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS inventory_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT NOT NULL,
            source_sheet TEXT NOT NULL,
            source_row INTEGER NOT NULL,
            product_id TEXT NOT NULL,
            part_no TEXT NOT NULL,
            description TEXT NOT NULL,
            category TEXT NOT NULL,
            uom TEXT NOT NULL,
            unit_price TEXT, -- Stored as string to strictly preserve 'NA' and '-'
            opening_stock TEXT,
            current_stock TEXT,
            latest_date TEXT,
            min_level REAL DEFAULT 10,
            stock_status TEXT,
            period TEXT,
            extra_fields_json TEXT DEFAULT '{}',
            validation_flags_json TEXT DEFAULT '[]',
            updated_at TEXT NOT NULL,
            UNIQUE(source_id, source_sheet, source_row)
        )
    ''')

    # 6. Daily Stock Movements
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stock_movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            movement_id TEXT NOT NULL,
            source_id TEXT NOT NULL,
            source_sheet TEXT NOT NULL,
            source_row INTEGER NOT NULL,
            date TEXT NOT NULL,
            product_id TEXT NOT NULL,
            part_no TEXT,
            description TEXT,
            category TEXT,
            movement_type TEXT NOT NULL, -- 'IN', 'OUT', 'IN/OUT'
            qty REAL NOT NULL,
            uom TEXT NOT NULL,
            opening_stock REAL,
            in_qty REAL DEFAULT 0,
            out_qty REAL DEFAULT 0,
            closing_stock REAL,
            period TEXT,
            reference_no TEXT,
            party_name TEXT,
            remarks TEXT,
            validation_flags_json TEXT DEFAULT '[]',
            UNIQUE(source_id, movement_id)
        )
    ''')

    # 7. Audit Logs
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            event_type TEXT NOT NULL,
            description TEXT NOT NULL,
            details TEXT
        )
    ''')

    # Create Indexes for lightning fast searching and filtering
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_inv_source ON inventory_records(source_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_inv_search ON inventory_records(product_id, part_no, category)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mov_source ON stock_movements(source_id, date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mov_prod ON stock_movements(product_id, date)')

    # Bootstrap default October 2026 source if database is brand new
    cursor.execute('SELECT COUNT(*) FROM spreadsheet_sources')
    if cursor.fetchone()[0] == 0:
        default_sid = Config.GOOGLE_SHEETS_SPREADSHEET_ID or "1lWYUrq8PvHE_uZQZRKNT7CSbxDN43hdIR86iTWVUwiM"
        now_iso = datetime.now(timezone.utc).isoformat()
        cursor.execute('''
            INSERT INTO spreadsheet_sources (
                source_id, name, spreadsheet_id, description, period, status, is_active, poll_interval_seconds, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 1, 30, ?, ?)
        ''', ("october-2026-master", "October 2026 Stock Master", default_sid, "Primary 6-worksheet master stock register for October 2026", "2026-10", "active", now_iso, now_iso))
        logger.info("Bootstrapped initial active source: October 2026 Stock Master")

    conn.commit()
    conn.close()
    logger.info("Relational database schema initialized with multi-spreadsheet support.")

# ---------------- Source Management Operations ----------------

def list_sources(include_disabled: bool = False) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    query = 'SELECT * FROM spreadsheet_sources'
    if not include_disabled:
        query += " WHERE status != 'disabled'"
    query += ' ORDER BY is_active DESC, period DESC, id ASC'
    cursor.execute(query)
    rows = [dict(r) for r in cursor.fetchall()]
    
    # Enrich with sheet counts and product counts
    for s in rows:
        sid = s["source_id"]
        cursor.execute('SELECT COUNT(*) FROM spreadsheet_sheets WHERE source_id = ?', (sid,))
        s["sheets_count"] = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM inventory_records WHERE source_id = ?', (sid,))
        s["products_count"] = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM stock_movements WHERE source_id = ?', (sid,))
        s["movements_count"] = cursor.fetchone()[0]

    conn.close()
    return rows

def get_source(source_id: str) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM spreadsheet_sources WHERE source_id = ? OR id = ?', (source_id, source_id))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None
    res = dict(row)
    sid = res["source_id"]
    cursor.execute('SELECT COUNT(*) FROM spreadsheet_sheets WHERE source_id = ?', (sid,))
    res["sheets_count"] = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM inventory_records WHERE source_id = ?', (sid,))
    res["products_count"] = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM stock_movements WHERE source_id = ?', (sid,))
    res["movements_count"] = cursor.fetchone()[0]
    conn.close()
    return res

def get_active_source() -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM spreadsheet_sources WHERE is_active = 1 AND status != 'disabled' LIMIT 1")
    row = cursor.fetchone()
    if not row:
        # Fallback to the first available non-disabled source
        cursor.execute("SELECT * FROM spreadsheet_sources WHERE status != 'disabled' ORDER BY id ASC LIMIT 1")
        row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def create_source(
    name: str,
    spreadsheet_url_or_id: str,
    period: str = "",
    description: str = "",
    status: str = "active",
    is_active: bool = False,
    poll_interval: int = 30
) -> Dict[str, Any]:
    conn = get_db_connection()
    cursor = conn.cursor()

    sheet_id = extract_spreadsheet_id(spreadsheet_url_or_id)
    # Generate stable source_id slug
    slug_base = re.sub(r'[^a-zA-Z0-9]+', '-', (period or name).lower()).strip('-')
    if not slug_base:
        slug_base = f"source-{int(datetime.now().timestamp())}"
    source_id = slug_base

    # Ensure uniqueness
    counter = 1
    while True:
        cursor.execute('SELECT id FROM spreadsheet_sources WHERE source_id = ?', (source_id,))
        if not cursor.fetchone():
            break
        source_id = f"{slug_base}-{counter}"
        counter += 1

    now_iso = datetime.now(timezone.utc).isoformat()

    if is_active:
        # Demote any other active source
        cursor.execute('UPDATE spreadsheet_sources SET is_active = 0')

    cursor.execute('''
        INSERT INTO spreadsheet_sources (
            source_id, name, spreadsheet_id, description, period, status, is_active, poll_interval_seconds, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (source_id, name.strip(), sheet_id, description.strip(), period.strip(), status, 1 if is_active else 0, max(15, poll_interval), now_iso, now_iso))

    conn.commit()
    conn.close()
    record_audit("SOURCE_CREATED", f"Registered new spreadsheet source: {name} ({source_id})", {"spreadsheet_id": sheet_id, "period": period})
    return get_source(source_id)

def update_source(source_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()

    fields = []
    vals = []
    for k, v in updates.items():
        if k in ("name", "description", "period", "status", "poll_interval_seconds"):
            fields.append(f"{k} = ?")
            vals.append(v)
        elif k == "spreadsheet_id":
            fields.append("spreadsheet_id = ?")
            vals.append(extract_spreadsheet_id(str(v)))
        elif k == "is_active":
            if v:
                cursor.execute('UPDATE spreadsheet_sources SET is_active = 0')
            fields.append("is_active = ?")
            vals.append(1 if v else 0)

    if not fields:
        conn.close()
        return get_source(source_id)

    fields.append("updated_at = ?")
    vals.append(datetime.now(timezone.utc).isoformat())
    vals.append(source_id)

    cursor.execute(f"UPDATE spreadsheet_sources SET {', '.join(fields)} WHERE source_id = ?", vals)
    conn.commit()
    conn.close()
    record_audit("SOURCE_UPDATED", f"Updated spreadsheet source {source_id}", updates)
    return get_source(source_id)

def set_active_source(source_id: str) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE spreadsheet_sources SET is_active = 0')
    cursor.execute("UPDATE spreadsheet_sources SET is_active = 1, status = 'active', updated_at = ? WHERE source_id = ?", (datetime.now(timezone.utc).isoformat(), source_id))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    if affected > 0:
        record_audit("SOURCE_ACTIVATED", f"Activated spreadsheet source: {source_id}")
        return True
    return False

def archive_source(source_id: str) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE spreadsheet_sources SET status = 'archived', is_active = 0, updated_at = ? WHERE source_id = ?", (datetime.now(timezone.utc).isoformat(), source_id))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    if affected > 0:
        record_audit("SOURCE_ARCHIVED", f"Archived spreadsheet source: {source_id}")
        return True
    return False

def delete_source(source_id: str) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM spreadsheet_sources WHERE source_id = ?', (source_id,))
    cursor.execute('DELETE FROM spreadsheet_sheets WHERE source_id = ?', (source_id,))
    cursor.execute('DELETE FROM sheet_column_mappings WHERE source_id = ?', (source_id,))
    cursor.execute('DELETE FROM inventory_records WHERE source_id = ?', (source_id,))
    cursor.execute('DELETE FROM stock_movements WHERE source_id = ?', (source_id,))
    cursor.execute('DELETE FROM sync_history WHERE source_id = ?', (source_id,))
    conn.commit()
    conn.close()
    record_audit("SOURCE_DELETED", f"Deleted spreadsheet source: {source_id}")
    return True

# ---------------- Sheet & Mapping Operations ----------------

def save_sheets_and_mappings(source_id: str, analysis_report: Dict[str, Any]):
    conn = get_db_connection()
    cursor = conn.cursor()
    now_iso = datetime.now(timezone.utc).isoformat()

    sheets = analysis_report.get("sheets", {})
    for idx, (sheet_name, s_data) in enumerate(sheets.items(), start=1):
        # 1. Save sheet metadata
        cursor.execute('''
            INSERT INTO spreadsheet_sheets (
                source_id, sheet_name, sheet_index, row_count, col_count, data_start_row, status, last_sync_at, issues_json
            ) VALUES (?, ?, ?, ?, ?, ?, 'success', ?, ?)
            ON CONFLICT(source_id, sheet_name) DO UPDATE SET
                row_count = excluded.row_count,
                col_count = excluded.col_count,
                data_start_row = excluded.data_start_row,
                last_sync_at = excluded.last_sync_at,
                issues_json = excluded.issues_json
        ''', (
            source_id,
            sheet_name,
            idx,
            s_data.get("row_count", 0),
            s_data.get("column_count", 0),
            s_data.get("data_start_row", 3),
            now_iso,
            json.dumps(s_data.get("issues", []))
        ))

        # 2. Save independent column mapping
        part_no_col = s_data["product_key_candidates"][0] if s_data.get("product_key_candidates") else None
        unit_price_col = s_data["unit_price_candidates"][0] if s_data.get("unit_price_candidates") else None
        cursor.execute('''
            INSERT INTO sheet_column_mappings (
                source_id, sheet_name, part_no_col, desc_col, cat_col, uom_col, unit_price_col,
                amount_cols_json, date_columns_json, extra_mappings_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_id, sheet_name) DO UPDATE SET
                part_no_col = excluded.part_no_col,
                unit_price_col = excluded.unit_price_col,
                amount_cols_json = excluded.amount_cols_json,
                date_columns_json = excluded.date_columns_json,
                updated_at = excluded.updated_at
        ''', (
            source_id,
            sheet_name,
            part_no_col,
            "Description",
            "Category",
            "UOM",
            unit_price_col,
            json.dumps(s_data.get("amount_columns", [])),
            json.dumps(s_data.get("date_columns", [])),
            json.dumps({"headers": s_data.get("headers", [])}),
            now_iso
        ))

    conn.commit()
    conn.close()

def get_sheets_for_source(source_id: str) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT s.*, m.amount_cols_json, m.date_columns_json, m.unit_price_col, m.part_no_col, m.extra_mappings_json
        FROM spreadsheet_sheets s
        LEFT JOIN sheet_column_mappings m ON s.source_id = m.source_id AND s.sheet_name = m.sheet_name
        WHERE s.source_id = ?
        ORDER BY s.sheet_index ASC
    ''', (source_id,))
    rows = []
    for r in cursor.fetchall():
        d = dict(r)
        d["issues"] = json.loads(d.get("issues_json") or "[]")
        d["amount_columns"] = json.loads(d.get("amount_cols_json") or "[]")
        d["date_columns"] = json.loads(d.get("date_columns_json") or "[]")
        extra_meta = json.loads(d.get("extra_mappings_json") or "{}")
        d["headers"] = extra_meta.get("headers", [])
        rows.append(d)
    conn.close()
    return rows

# ---------------- Transactional Inventory & Movement Storage ----------------

def replace_source_snapshot(
    source_id: str,
    period: str,
    products: List[Dict[str, Any]],
    movements: List[Dict[str, Any]],
    fingerprint: str = ""
) -> bool:
    """Atomically replaces inventory and movements for a specific source without touching other sources."""
    conn = get_db_connection()
    cursor = conn.cursor()
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        # Clean existing records for THIS source only
        cursor.execute('DELETE FROM inventory_records WHERE source_id = ?', (source_id,))
        cursor.execute('DELETE FROM stock_movements WHERE source_id = ?', (source_id,))

        # Batch insert products
        inv_rows = []
        for p in products:
            # Strictly filter out any amount fields
            extra = p.get("extra_fields", {})
            safe_extra = {
                k: v for k, v in extra.items()
                if not any(kw in k.lower() for kw in ["amount", "total cost", "total price", "val", "closing value"])
            }

            inv_rows.append((
                source_id,
                p.get("source_sheet", ""),
                p.get("source_row", 0),
                p.get("product_id", ""),
                p.get("part_no", ""),
                p.get("description", ""),
                p.get("category", ""),
                p.get("uom", "NOS"),
                str(p.get("unit_price")) if p.get("unit_price") is not None else None,
                str(p.get("opening_stock")) if p.get("opening_stock") is not None else None,
                str(p.get("current_stock")) if p.get("current_stock") is not None else None,
                p.get("latest_date", ""),
                p.get("min_level", 10),
                p.get("stock_status", "In Stock"),
                period or p.get("period", ""),
                json.dumps(safe_extra),
                json.dumps(p.get("validation_flags", [])),
                now_iso
            ))

        cursor.executemany('''
            INSERT INTO inventory_records (
                source_id, source_sheet, source_row, product_id, part_no, description,
                category, uom, unit_price, opening_stock, current_stock, latest_date,
                min_level, stock_status, period, extra_fields_json, validation_flags_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', inv_rows)

        # Batch insert movements
        mov_rows = []
        for m in movements:
            mov_rows.append((
                m.get("movement_id", ""),
                source_id,
                m.get("source_sheet", ""),
                m.get("source_row", 0),
                m.get("date", ""),
                m.get("product_id", ""),
                m.get("part_no", ""),
                m.get("description", ""),
                m.get("category", ""),
                m.get("movement_type", "IN"),
                m.get("qty", 0.0),
                m.get("uom", "NOS"),
                m.get("opening_stock"),
                m.get("in_qty", 0.0),
                m.get("out_qty", 0.0),
                m.get("closing_stock"),
                period,
                m.get("reference_no", ""),
                m.get("party_name", ""),
                m.get("remarks", ""),
                json.dumps(m.get("validation_flags", []))
            ))

        cursor.executemany('''
            INSERT INTO stock_movements (
                movement_id, source_id, source_sheet, source_row, date, product_id,
                part_no, description, category, movement_type, qty, uom, opening_stock,
                in_qty, out_qty, closing_stock, period, reference_no, party_name, remarks, validation_flags_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', mov_rows)

        # Update source last_sync metadata
        cursor.execute('''
            UPDATE spreadsheet_sources SET
                last_sync_at = ?,
                last_sync_status = 'success',
                last_sync_error = NULL,
                fingerprint = ?,
                updated_at = ?
            WHERE source_id = ?
        ''', (now_iso, fingerprint, now_iso, source_id))

        conn.commit()
        conn.close()
        return True

    except Exception as e:
        conn.rollback()
        conn.close()
        logger.error(f"Failed to replace snapshot for {source_id}: {e}")
        return False

# ---------------- Sync Runs & Audit Logging ----------------

def record_sync_run(
    status: str,
    sheets_processed: int,
    products_count: int,
    movements_count: int,
    fingerprint: str = "",
    error_message: Optional[str] = None,
    source_id: str = "active",
    source_name: str = ""
):
    conn = get_db_connection()
    cursor = conn.cursor()
    now_iso = datetime.now(timezone.utc).isoformat()
    
    # Insert in sync_history
    cursor.execute('''
        INSERT INTO sync_history (
            source_id, source_name, timestamp, status, sheets_processed,
            products_imported, movements_imported, fingerprint, error_message
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (source_id, source_name, now_iso, status, sheets_processed, products_count, movements_count, fingerprint, error_message))

    # Keep legacy sync_runs table populated for backwards-compatibility
    cursor.execute('''
        INSERT INTO sync_runs (timestamp, status, sheets_processed, products_count, movements_count, fingerprint, error_message)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (now_iso, status, sheets_processed, products_count, movements_count, fingerprint, error_message))

    # If error, update source record
    if status == 'error' and error_message:
        cursor.execute('''
            UPDATE spreadsheet_sources SET
                last_sync_at = ?,
                last_sync_status = 'error',
                last_sync_error = ?,
                updated_at = ?
            WHERE source_id = ?
        ''', (now_iso, error_message, now_iso, source_id))

    conn.commit()
    conn.close()

def record_audit(event_type: str, description: str, details: Any = None):
    conn = get_db_connection()
    cursor = conn.cursor()
    details_str = json.dumps(details) if details else None
    cursor.execute('''
        INSERT INTO audit_logs (timestamp, event_type, description, details)
        VALUES (?, ?, ?, ?)
    ''', (datetime.now(timezone.utc).isoformat(), event_type, description, details_str))
    conn.commit()
    conn.close()

def get_recent_sync_runs(source_id: Optional[str] = None, limit: int = 15) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    if source_id and source_id != "all":
        cursor.execute('SELECT * FROM sync_history WHERE source_id = ? ORDER BY id DESC LIMIT ?', (source_id, limit))
    else:
        cursor.execute('SELECT * FROM sync_history ORDER BY id DESC LIMIT ?', (limit,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

import re
import sqlite3
import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple, Union
from config import Config

logger = logging.getLogger(__name__)


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(Config.DATABASE_PATH)
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
    if "/" in cleaned or "\\" in cleaned:
        parts = re.split(r'[/\\]', cleaned)
        for part in reversed(parts):
            if len(part) >= 20 and re.match(r'^[a-zA-Z0-9-_]+$', part):
                return part
    return cleaned


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
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
    """)

    cursor.execute("""
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
    """)

    cursor.execute("""
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
    """)

    cursor.execute("""
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
    """)

    cursor.execute("""
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
    """)

    cursor.execute("""
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
    """)

    cursor.execute("""
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
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            event_type TEXT NOT NULL,
            description TEXT NOT NULL,
            details TEXT
        )
    """)

    # Seed default source if empty
    cursor.execute("SELECT count(*) FROM spreadsheet_sources")
    if cursor.fetchone()[0] == 0 and Config.GOOGLE_SHEETS_SPREADSHEET_ID:
        default_sid = "default_source"
        now_iso = datetime.now(timezone.utc).isoformat()
        cursor.execute("""
            INSERT INTO spreadsheet_sources (
                source_id, name, spreadsheet_id, description, period, status, is_active,
                poll_interval_seconds, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'active', 1, ?, ?, ?)
        """, (
            default_sid,
            "Primary Stock Spreadsheet",
            Config.GOOGLE_SHEETS_SPREADSHEET_ID,
            "Default Google Sheets stock register",
            "",
            Config.SYNC_INTERVAL_SECONDS,
            now_iso,
            now_iso
        ))
        logger.info(f"Initialized default spreadsheet source: {Config.GOOGLE_SHEETS_SPREADSHEET_ID}")

    conn.commit()
    conn.close()


def list_sources(include_disabled: bool = False) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    if include_disabled:
        cursor.execute("SELECT * FROM spreadsheet_sources ORDER BY is_active DESC, updated_at DESC")
    else:
        cursor.execute("SELECT * FROM spreadsheet_sources WHERE status != 'disabled' ORDER BY is_active DESC, updated_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_source(source_id: str) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM spreadsheet_sources WHERE source_id = ?", (source_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_active_source() -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM spreadsheet_sources WHERE is_active = 1 LIMIT 1")
    row = cursor.fetchone()
    if not row:
        cursor.execute("SELECT * FROM spreadsheet_sources WHERE status = 'active' ORDER BY updated_at DESC LIMIT 1")
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
    slug_base = re.sub(r'[^a-zA-Z0-9_]+', '_', name.strip().lower()).strip('_')
    if not slug_base:
        slug_base = "source"
    source_id = f"{slug_base}_{int(datetime.now().timestamp())}"

    now_iso = datetime.now(timezone.utc).isoformat()

    if is_active:
        cursor.execute("UPDATE spreadsheet_sources SET is_active = 0 WHERE is_active = 1")

    cursor.execute("""
        INSERT INTO spreadsheet_sources (
            source_id, name, spreadsheet_id, description, period, status, is_active,
            poll_interval_seconds, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        source_id,
        name.strip(),
        sheet_id,
        description.strip(),
        period.strip(),
        status,
        1 if is_active else 0,
        max(10, int(poll_interval)),
        now_iso,
        now_iso
    ))

    conn.commit()
    conn.close()
    record_audit("SOURCE_CREATED", f"Created spreadsheet source '{name}'", {"source_id": source_id, "sheet_id": sheet_id})
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
        elif k in ("spreadsheet_url_or_id", "spreadsheet_id"):
            fields.append("spreadsheet_id = ?")
            vals.append(extract_spreadsheet_id(str(v)))
        elif k == "is_active":
            if v:
                cursor.execute("UPDATE spreadsheet_sources SET is_active = 0 WHERE is_active = 1")
            fields.append("is_active = ?")
            vals.append(1 if v else 0)

    if not fields:
        conn.close()
        return get_source(source_id)

    now_iso = datetime.now(timezone.utc).isoformat()
    fields.append("updated_at = ?")
    vals.append(now_iso)
    vals.append(source_id)

    cursor.execute(f"UPDATE spreadsheet_sources SET {', '.join(fields)} WHERE source_id = ?", vals)
    conn.commit()
    conn.close()
    record_audit("SOURCE_UPDATED", f"Updated source {source_id}", updates)
    return get_source(source_id)


def set_active_source(source_id: str) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    now_iso = datetime.now(timezone.utc).isoformat()
    cursor.execute("UPDATE spreadsheet_sources SET is_active = 0 WHERE is_active = 1")
    cursor.execute("UPDATE spreadsheet_sources SET is_active = 1, updated_at = ? WHERE source_id = ?", (now_iso, source_id))
    affected = cursor.rowcount > 0
    conn.commit()
    conn.close()
    if affected:
        record_audit("SOURCE_ACTIVATED", f"Activated source {source_id}", {"source_id": source_id})
    return affected


def archive_source(source_id: str) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    now_iso = datetime.now(timezone.utc).isoformat()
    cursor.execute("UPDATE spreadsheet_sources SET status = 'archived', is_active = 0, updated_at = ? WHERE source_id = ?", (now_iso, source_id))
    affected = cursor.rowcount > 0
    conn.commit()
    conn.close()
    if affected:
        record_audit("SOURCE_ARCHIVED", f"Archived source {source_id}", {"source_id": source_id})
    return affected


def delete_source(source_id: str) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM inventory_records WHERE source_id = ?", (source_id,))
    cursor.execute("DELETE FROM stock_movements WHERE source_id = ?", (source_id,))
    cursor.execute("DELETE FROM spreadsheet_sheets WHERE source_id = ?", (source_id,))
    cursor.execute("DELETE FROM sheet_column_mappings WHERE source_id = ?", (source_id,))
    cursor.execute("DELETE FROM sync_history WHERE source_id = ?", (source_id,))
    cursor.execute("DELETE FROM spreadsheet_sources WHERE source_id = ?", (source_id,))
    conn.commit()
    conn.close()
    record_audit("SOURCE_DELETED", f"Deleted source {source_id}", {"source_id": source_id})
    return True


def save_sheets_and_mappings(source_id: str, analysis_results: List[Dict[str, Any]]):
    conn = get_db_connection()
    cursor = conn.cursor()
    now_iso = datetime.now(timezone.utc).isoformat()

    for idx, sheet in enumerate(analysis_results):
        sheet_name = sheet.get("sheet_name", f"Sheet{idx+1}")
        cursor.execute("""
            INSERT INTO spreadsheet_sheets (
                source_id, sheet_name, sheet_index, row_count, col_count, data_start_row,
                status, last_sync_at, issues_json
            ) VALUES (?, ?, ?, ?, ?, ?, 'success', ?, ?)
            ON CONFLICT(source_id, sheet_name) DO UPDATE SET
                sheet_index = excluded.sheet_index,
                row_count = excluded.row_count,
                col_count = excluded.col_count,
                data_start_row = excluded.data_start_row,
                last_sync_at = excluded.last_sync_at,
                issues_json = excluded.issues_json
        """, (
            source_id,
            sheet_name,
            idx,
            sheet.get("row_count", 0),
            sheet.get("column_count", 0),
            sheet.get("data_start_row", 3),
            now_iso,
            json.dumps(sheet.get("issues", []))
        ))

        cursor.execute("""
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
        """, (
            source_id,
            sheet_name,
            sheet.get("product_key_col", ""),
            sheet.get("description_col", "Description"),
            sheet.get("category_col", ""),
            sheet.get("uom_col", ""),
            sheet.get("unit_price_col", ""),
            json.dumps(sheet.get("amount_columns", [])),
            json.dumps(sheet.get("date_columns", [])),
            json.dumps(sheet.get("extra_mappings", {})),
            now_iso
        ))

    conn.commit()
    conn.close()


def get_sheets_for_source(source_id: str) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.*, m.amount_cols_json, m.date_columns_json, m.unit_price_col, m.part_no_col, m.extra_mappings_json
        FROM spreadsheet_sheets s
        LEFT JOIN sheet_column_mappings m ON s.source_id = m.source_id AND s.sheet_name = m.sheet_name
        WHERE s.source_id = ?
        ORDER BY s.sheet_index ASC
    """, (source_id,))
    rows = cursor.fetchall()
    conn.close()

    result = []
    for r in rows:
        d = dict(r)
        d["issues"] = json.loads(d.get("issues_json") or "[]")
        d["amount_columns"] = json.loads(d.get("amount_cols_json") or "[]")
        d["date_columns"] = json.loads(d.get("date_columns_json") or "[]")
        d["extra_mappings"] = json.loads(d.get("extra_mappings_json") or "{}")
        result.append(d)
    return result


def replace_source_snapshot(
    source_id: str,
    period: str,
    products: List[Dict[str, Any]],
    movements: List[Dict[str, Any]],
    fingerprint: str
) -> bool:
    """Atomically replaces inventory and movements for a specific source without touching other sources."""
    conn = get_db_connection()
    cursor = conn.cursor()
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        cursor.execute("DELETE FROM inventory_records WHERE source_id = ?", (source_id,))
        cursor.execute("DELETE FROM stock_movements WHERE source_id = ?", (source_id,))

        inv_rows = []
        for p in products:
            extra = p.get("extra_fields", {})
            safe_extra = {k: v for k, v in extra.items() if not any(w in k.lower() for w in ['amount', 'closing value', 'closing stk val', 'total price'])}
            inv_rows.append((
                source_id,
                p.get("source_sheet", ""),
                p.get("source_row", 0),
                p.get("product_id", ""),
                p.get("part_no", ""),
                p.get("description", ""),
                p.get("category", ""),
                p.get("uom", ""),
                str(p.get("unit_price", "NA")),
                str(p.get("opening_stock", 0)),
                str(p.get("current_stock", 0)),
                p.get("latest_date", ""),
                float(p.get("min_level", 10) or 10),
                p.get("stock_status", "in_stock"),
                period,
                json.dumps(safe_extra),
                json.dumps(p.get("validation_flags", [])),
                now_iso
            ))

        if inv_rows:
            cursor.executemany("""
                INSERT OR REPLACE INTO inventory_records (
                    source_id, source_sheet, source_row, product_id, part_no, description, category,
                    uom, unit_price, opening_stock, current_stock, latest_date, min_level,
                    stock_status, period, extra_fields_json, validation_flags_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, inv_rows)

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
                m.get("movement_type", "IN/OUT"),
                float(m.get("qty", 0) or 0),
                m.get("uom", ""),
                float(m.get("opening_stock", 0) or 0),
                float(m.get("in_qty", 0) or 0),
                float(m.get("out_qty", 0) or 0),
                float(m.get("closing_stock", 0) or 0),
                period,
                m.get("reference_no", ""),
                m.get("party_name", ""),
                m.get("remarks", ""),
                json.dumps(m.get("validation_flags", []))
            ))

        if mov_rows:
            cursor.executemany("""
                INSERT OR REPLACE INTO stock_movements (
                    movement_id, source_id, source_sheet, source_row, date, product_id,
                    part_no, description, category, movement_type, qty, uom, opening_stock,
                    in_qty, out_qty, closing_stock, period, reference_no, party_name, remarks, validation_flags_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, mov_rows)

        cursor.execute("""
            UPDATE spreadsheet_sources SET
                last_sync_at = ?,
                last_sync_status = 'success',
                last_sync_error = NULL,
                fingerprint = ?,
                updated_at = ?
            WHERE source_id = ?
        """, (now_iso, fingerprint, now_iso, source_id))

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        conn.rollback()
        conn.close()
        logger.error(f"Failed to replace snapshot for {source_id}: {e}")
        return False


def record_sync_run(
    status: str,
    sheets_processed: int,
    products_count: int,
    movements_count: int,
    fingerprint: str = "",
    error_message: Optional[str] = None,
    source_id: str = "default_source",
    source_name: Optional[str] = None
):
    conn = get_db_connection()
    cursor = conn.cursor()
    now_iso = datetime.now(timezone.utc).isoformat()

    cursor.execute("""
        INSERT INTO sync_history (
            source_id, source_name, timestamp, status, sheets_processed,
            products_imported, movements_imported, fingerprint, error_message
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        source_id,
        source_name or source_id,
        now_iso,
        status,
        sheets_processed,
        products_count,
        movements_count,
        fingerprint,
        error_message
    ))

    cursor.execute("""
        INSERT INTO sync_runs (timestamp, status, sheets_processed, products_count, movements_count, fingerprint, error_message)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        now_iso,
        status,
        sheets_processed,
        products_count,
        movements_count,
        fingerprint,
        error_message
    ))

    if status == "error":
        cursor.execute("""
            UPDATE spreadsheet_sources SET
                last_sync_at = ?,
                last_sync_status = 'error',
                last_sync_error = ?,
                updated_at = ?
            WHERE source_id = ?
        """, (now_iso, error_message, now_iso, source_id))

    conn.commit()
    conn.close()


def record_audit(event_type: str, description: str, details: Any = None):
    conn = get_db_connection()
    cursor = conn.cursor()
    details_str = json.dumps(details) if details else ""
    cursor.execute("""
        INSERT INTO audit_logs (timestamp, event_type, description, details)
        VALUES (?, ?, ?, ?)
    """, (datetime.now(timezone.utc).isoformat(), event_type, description, details_str))
    conn.commit()
    conn.close()


def get_recent_sync_runs(source_id: Optional[str] = None, limit: int = 15) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    if source_id and source_id != "all":
        cursor.execute("SELECT * FROM sync_history WHERE source_id = ? ORDER BY id DESC LIMIT ?", (source_id, limit))
    else:
        cursor.execute("SELECT * FROM sync_history ORDER BY id DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

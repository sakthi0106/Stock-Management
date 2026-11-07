import os
import re
import math
import sqlite3
import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple, Union
from config import Config

logger = logging.getLogger(__name__)

# Determine active database engine: PostgreSQL (if DATABASE_URL is set) or SQLite (fallback)
DB_ENGINE = "postgresql" if Config.DATABASE_URL and Config.DATABASE_URL.startswith("postgres") else "sqlite"


class UnifiedCursor:
    """Cursor wrapper that transparently adapts SQL query syntax between SQLite and PostgreSQL."""
    def __init__(self, raw_cursor, is_postgres: bool):
        self._raw_cursor = raw_cursor
        self.is_postgres = is_postgres

    def _translate_query(self, query: str) -> str:
        if not self.is_postgres:
            return query
        # Adapt ? to %s for PostgreSQL parameterized queries
        # Preserve ?? or string literals
        translated = query.replace('?', '%s')
        # Translate INSERT OR REPLACE INTO ... (table) (cols) VALUES (...) to PostgreSQL ON CONFLICT
        # Handled at call sites or table definitions
        return translated

    def execute(self, query: str, params: Optional[Union[tuple, list]] = None):
        t_query = self._translate_query(query)
        if params is not None:
            return self._raw_cursor.execute(t_query, params)
        return self._raw_cursor.execute(t_query)

    def executemany(self, query: str, seq_of_params: List[Union[tuple, list]]):
        t_query = self._translate_query(query)
        return self._raw_cursor.executemany(t_query, seq_of_params)

    def fetchone(self):
        row = self._raw_cursor.fetchone()
        if row is None:
            return None
        if hasattr(row, 'keys'):
            return row
        if isinstance(row, dict):
            return row
        return row

    def fetchall(self):
        return self._raw_cursor.fetchall()

    @property
    def rowcount(self):
        return self._raw_cursor.rowcount

    def close(self):
        return self._raw_cursor.close()


class UnifiedConnection:
    """Connection wrapper ensuring identical behavior across PostgreSQL and SQLite."""
    def __init__(self, raw_conn, is_postgres: bool):
        self._raw_conn = raw_conn
        self.is_postgres = is_postgres

    def cursor(self):
        return UnifiedCursor(self._raw_conn.cursor(), self.is_postgres)

    def execute(self, query: str, params: Optional[Union[tuple, list]] = None):
        cur = self.cursor()
        cur.execute(query, params)
        return cur

    def commit(self):
        return self._raw_conn.commit()

    def rollback(self):
        return self._raw_conn.rollback()

    def close(self):
        return self._raw_conn.close()


def get_db_connection() -> UnifiedConnection:
    """Connect to PostgreSQL (if configured in DATABASE_URL) or SQLite local database."""
    global DB_ENGINE
    if Config.DATABASE_URL and Config.DATABASE_URL.startswith("postgres"):
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor
            raw_conn = psycopg2.connect(Config.DATABASE_URL, cursor_factory=RealDictCursor)
            DB_ENGINE = "postgresql"
            return UnifiedConnection(raw_conn, is_postgres=True)
        except Exception as e:
            logger.warning(f"Could not connect to PostgreSQL via DATABASE_URL ({e}). Falling back to SQLite.")

    # SQLite local engine
    raw_conn = sqlite3.connect(Config.DATABASE_PATH, timeout=30.0)
    raw_conn.row_factory = sqlite3.Row
    raw_conn.execute("PRAGMA busy_timeout=30000")
    DB_ENGINE = "sqlite"
    return UnifiedConnection(raw_conn, is_postgres=False)


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
    """Idempotently initialize all database tables and perform safe schema migrations."""
    conn = get_db_connection()
    cursor = conn.cursor()

    id_type = "SERIAL PRIMARY KEY" if conn.is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"

    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS spreadsheet_sources (
            id {id_type},
            source_id VARCHAR(100) UNIQUE NOT NULL,
            name VARCHAR(255) NOT NULL,
            spreadsheet_id TEXT NOT NULL,
            description TEXT DEFAULT '',
            period VARCHAR(50) DEFAULT '',
            status VARCHAR(50) DEFAULT 'active', -- 'active', 'archived', 'disabled'
            is_active INTEGER DEFAULT 0,          -- 1 for currently active live spreadsheet
            poll_interval_seconds INTEGER DEFAULT 15,
            last_sync_at VARCHAR(100),
            last_sync_status VARCHAR(50) DEFAULT 'pending', -- 'success', 'warning', 'error', 'pending'
            last_sync_error TEXT,
            fingerprint VARCHAR(255) DEFAULT '',
            source_type VARCHAR(50) DEFAULT 'google_sheets', -- 'google_sheets', 'excel_upload'
            total_worksheets INTEGER DEFAULT 0,
            total_records INTEGER DEFAULT 0,
            last_analyzed_at VARCHAR(100),
            analysis_status VARCHAR(50) DEFAULT 'idle',
            created_at VARCHAR(100) NOT NULL,
            updated_at VARCHAR(100) NOT NULL
        )
    """)

    # Safe column migrations for spreadsheet_sources
    if not conn.is_postgres:
        cursor.execute("PRAGMA table_info(spreadsheet_sources)")
        source_cols = [c[1] for c in cursor.fetchall()]
        if 'source_type' not in source_cols:
            cursor.execute("ALTER TABLE spreadsheet_sources ADD COLUMN source_type TEXT DEFAULT 'google_sheets'")
        if 'total_worksheets' not in source_cols:
            cursor.execute("ALTER TABLE spreadsheet_sources ADD COLUMN total_worksheets INTEGER DEFAULT 0")
        if 'total_records' not in source_cols:
            cursor.execute("ALTER TABLE spreadsheet_sources ADD COLUMN total_records INTEGER DEFAULT 0")
        if 'last_analyzed_at' not in source_cols:
            cursor.execute("ALTER TABLE spreadsheet_sources ADD COLUMN last_analyzed_at TEXT")
        if 'analysis_status' not in source_cols:
            cursor.execute("ALTER TABLE spreadsheet_sources ADD COLUMN analysis_status TEXT DEFAULT 'idle'")

    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS worksheet_metadata (
            id {id_type},
            source_id VARCHAR(100) NOT NULL,
            sheet_name VARCHAR(255) NOT NULL,
            row_count INTEGER DEFAULT 0,
            col_count INTEGER DEFAULT 0,
            header_row INTEGER DEFAULT 1,
            structure_type VARCHAR(100) DEFAULT 'tabular',
            classification VARCHAR(100) DEFAULT 'unknown',
            quality_score REAL DEFAULT 100.0,
            analysis_status VARCHAR(50) DEFAULT 'completed',
            summary_json TEXT DEFAULT '{{}}',
            created_at VARCHAR(100) NOT NULL,
            updated_at VARCHAR(100) NOT NULL,
            UNIQUE(source_id, sheet_name)
        )
    """)

    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS dynamic_column_metadata (
            id {id_type},
            source_id VARCHAR(100) NOT NULL,
            sheet_name VARCHAR(255) NOT NULL,
            column_index INTEGER NOT NULL,
            original_col TEXT NOT NULL,
            normalized_col TEXT NOT NULL,
            inferred_role VARCHAR(100) NOT NULL,
            inferred_type VARCHAR(50) DEFAULT 'text',
            confidence REAL DEFAULT 0.5,
            sample_values_json TEXT DEFAULT '[]',
            stats_json TEXT DEFAULT '{{}}',
            mapping_status VARCHAR(50) DEFAULT 'auto',
            requires_review INTEGER DEFAULT 0,
            reason TEXT DEFAULT '',
            updated_at VARCHAR(100) NOT NULL,
            UNIQUE(source_id, sheet_name, column_index)
        )
    """)

    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS dynamic_records (
            id {id_type},
            source_id VARCHAR(100) NOT NULL,
            sheet_name VARCHAR(255) NOT NULL,
            row_index INTEGER NOT NULL,
            raw_data_json TEXT NOT NULL,
            inferred_data_json TEXT DEFAULT '{{}}',
            created_at VARCHAR(100) NOT NULL,
            updated_at VARCHAR(100) NOT NULL,
            UNIQUE(source_id, sheet_name, row_index)
        )
    """)

    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS spreadsheet_sheets (
            id {id_type},
            source_id VARCHAR(100) NOT NULL,
            sheet_name VARCHAR(255) NOT NULL,
            sheet_index INTEGER DEFAULT 0,
            row_count INTEGER DEFAULT 0,
            col_count INTEGER DEFAULT 0,
            data_start_row INTEGER DEFAULT 3,
            status VARCHAR(50) DEFAULT 'success',
            last_sync_at VARCHAR(100),
            issues_json TEXT DEFAULT '[]',
            UNIQUE(source_id, sheet_name)
        )
    """)

    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS sheet_column_mappings (
            id {id_type},
            source_id VARCHAR(100) NOT NULL,
            sheet_name VARCHAR(255) NOT NULL,
            part_no_col TEXT,
            desc_col TEXT,
            cat_col TEXT,
            uom_col TEXT,
            unit_price_col TEXT,
            monthly_open_col TEXT,
            closing_col TEXT,
            amount_cols_json TEXT DEFAULT '[]',
            date_columns_json TEXT DEFAULT '[]',
            extra_mappings_json TEXT DEFAULT '{{}}',
            updated_at VARCHAR(100) NOT NULL,
            UNIQUE(source_id, sheet_name)
        )
    """)

    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS sync_history (
            id {id_type},
            source_id VARCHAR(100) NOT NULL,
            source_name VARCHAR(255),
            timestamp VARCHAR(100) NOT NULL,
            status VARCHAR(50) NOT NULL,
            sheets_processed INTEGER DEFAULT 0,
            products_imported INTEGER DEFAULT 0,
            movements_imported INTEGER DEFAULT 0,
            fingerprint VARCHAR(255) DEFAULT '',
            duration_ms INTEGER DEFAULT 0,
            error_message TEXT
        )
    """)

    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS sync_runs (
            id {id_type},
            timestamp VARCHAR(100) NOT NULL,
            status VARCHAR(50) NOT NULL,
            sheets_processed INTEGER DEFAULT 0,
            products_count INTEGER DEFAULT 0,
            movements_count INTEGER DEFAULT 0,
            fingerprint VARCHAR(255),
            error_message TEXT
        )
    """)

    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS inventory_records (
            id {id_type},
            source_id VARCHAR(100) NOT NULL,
            source_sheet VARCHAR(255) NOT NULL,
            source_row INTEGER NOT NULL,
            product_id VARCHAR(255) NOT NULL,
            part_no TEXT NOT NULL,
            description TEXT NOT NULL,
            category TEXT NOT NULL,
            uom VARCHAR(50) NOT NULL,
            unit_price TEXT,
            opening_stock TEXT,
            current_stock TEXT,
            latest_date VARCHAR(50),
            min_level REAL DEFAULT 10,
            stock_status VARCHAR(50),
            period VARCHAR(50),
            extra_fields_json TEXT DEFAULT '{{}}',
            validation_flags_json TEXT DEFAULT '[]',
            updated_at VARCHAR(100) NOT NULL,
            UNIQUE(source_id, source_sheet, source_row)
        )
    """)

    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS stock_movements (
            id {id_type},
            movement_id VARCHAR(255) NOT NULL,
            source_id VARCHAR(100) NOT NULL,
            source_sheet VARCHAR(255) NOT NULL,
            source_row INTEGER NOT NULL,
            date VARCHAR(50) NOT NULL,
            product_id VARCHAR(255) NOT NULL,
            part_no TEXT,
            description TEXT,
            category TEXT,
            movement_type VARCHAR(50) NOT NULL,
            qty REAL NOT NULL,
            uom VARCHAR(50) NOT NULL,
            opening_stock REAL,
            in_qty REAL DEFAULT 0,
            out_qty REAL DEFAULT 0,
            closing_stock REAL,
            period VARCHAR(50),
            reference_no TEXT,
            party_name TEXT,
            remarks TEXT,
            validation_flags_json TEXT DEFAULT '[]',
            UNIQUE(source_id, movement_id)
        )
    """)

    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id {id_type},
            timestamp VARCHAR(100) NOT NULL,
            event_type VARCHAR(100) NOT NULL,
            description TEXT NOT NULL,
            details TEXT
        )
    """)

    # Performance indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_inv_source ON inventory_records(source_id, source_sheet)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_inv_product ON inventory_records(product_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_mov_source ON stock_movements(source_id, source_sheet)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_mov_date ON stock_movements(date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_mov_prod ON stock_movements(product_id)")

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
    if not source_id:
        return None
    if source_id in ("default", "active"):
        return get_active_source()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM spreadsheet_sources WHERE source_id = ?", (source_id,))
    row = cursor.fetchone()
    if not row and str(source_id).isdigit():
        cursor.execute("SELECT * FROM spreadsheet_sources WHERE id = ?", (int(source_id),))
        row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_active_source() -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM spreadsheet_sources WHERE is_active = 1 LIMIT 1")
    row = cursor.fetchone()
    if not row:
        # Fallback to the most recently updated active source
        cursor.execute("SELECT * FROM spreadsheet_sources WHERE status = 'active' ORDER BY updated_at DESC, id DESC LIMIT 1")
        row = cursor.fetchone()
    if not row:
        # Fallback to any registered spreadsheet source
        cursor.execute("SELECT * FROM spreadsheet_sources ORDER BY updated_at DESC, id DESC LIMIT 1")
        row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_active_and_enabled_sources() -> List[Dict[str, Any]]:
    """Return all explicitly registered spreadsheet sources that are active and not disabled."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM spreadsheet_sources WHERE status = 'active' ORDER BY is_active DESC, id ASC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_source(
    name: str,
    spreadsheet_url_or_id: str,
    period: str = "",
    description: str = "",
    status: str = "active",
    is_active: bool = False,
    poll_interval: int = 15
) -> Dict[str, Any]:
    conn = get_db_connection()
    cursor = conn.cursor()

    # If no active source currently exists, activate this source automatically
    cursor.execute("SELECT COUNT(*) as c FROM spreadsheet_sources WHERE is_active = 1")
    count_row = cursor.fetchone()
    active_count = count_row['c'] if count_row and 'c' in count_row else (count_row[0] if count_row else 0)
    if active_count == 0:
        is_active = True

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
    cursor.execute("DELETE FROM worksheet_metadata WHERE source_id = ?", (source_id,))
    cursor.execute("DELETE FROM dynamic_column_metadata WHERE source_id = ?", (source_id,))
    cursor.execute("DELETE FROM dynamic_records WHERE source_id = ?", (source_id,))
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
                INSERT INTO inventory_records (
                    source_id, source_sheet, source_row, product_id, part_no, description, category,
                    uom, unit_price, opening_stock, current_stock, latest_date, min_level,
                    stock_status, period, extra_fields_json, validation_flags_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_id, source_sheet, source_row) DO UPDATE SET
                    product_id = excluded.product_id,
                    part_no = excluded.part_no,
                    description = excluded.description,
                    category = excluded.category,
                    uom = excluded.uom,
                    unit_price = excluded.unit_price,
                    opening_stock = excluded.opening_stock,
                    current_stock = excluded.current_stock,
                    latest_date = excluded.latest_date,
                    min_level = excluded.min_level,
                    stock_status = excluded.stock_status,
                    period = excluded.period,
                    extra_fields_json = excluded.extra_fields_json,
                    validation_flags_json = excluded.validation_flags_json,
                    updated_at = excluded.updated_at
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
                INSERT INTO stock_movements (
                    movement_id, source_id, source_sheet, source_row, date, product_id,
                    part_no, description, category, movement_type, qty, uom, opening_stock,
                    in_qty, out_qty, closing_stock, period, reference_no, party_name, remarks, validation_flags_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_id, movement_id) DO UPDATE SET
                    date = excluded.date,
                    product_id = excluded.product_id,
                    part_no = excluded.part_no,
                    description = excluded.description,
                    category = excluded.category,
                    movement_type = excluded.movement_type,
                    qty = excluded.qty,
                    uom = excluded.uom,
                    opening_stock = excluded.opening_stock,
                    in_qty = excluded.in_qty,
                    out_qty = excluded.out_qty,
                    closing_stock = excluded.closing_stock,
                    period = excluded.period,
                    reference_no = excluded.reference_no,
                    party_name = excluded.party_name,
                    remarks = excluded.remarks,
                    validation_flags_json = excluded.validation_flags_json
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
        logger.error(f"Failed to replace snapshot for {source_id}: {e}", exc_info=True)
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


# ==========================================
# DYNAMIC SPREADSHEET INTELLIGENCE ACCESS
# ==========================================

def update_source_intelligence_status(
    source_id: str,
    status: str,
    last_analyzed: Optional[str] = None,
    total_sheets: Optional[int] = None,
    total_records: Optional[int] = None
):
    conn = get_db_connection()
    cursor = conn.cursor()
    now_iso = datetime.now(timezone.utc).isoformat()
    cursor.execute("""
        UPDATE spreadsheet_sources SET
            analysis_status = ?,
            last_analyzed_at = COALESCE(?, last_analyzed_at),
            total_worksheets = COALESCE(?, total_worksheets),
            total_records = COALESCE(?, total_records),
            updated_at = ?
        WHERE source_id = ?
    """, (status, last_analyzed or now_iso, total_sheets, total_records, now_iso, source_id))
    conn.commit()
    conn.close()


def save_worksheet_analysis(source_id: str, profile: Dict[str, Any]):
    """Save or update worksheet metadata and dynamic column profiling."""
    conn = get_db_connection()
    cursor = conn.cursor()
    now_iso = datetime.now(timezone.utc).isoformat()
    sheet_name = profile["sheet_name"]

    cursor.execute("""
        INSERT INTO worksheet_metadata (
            source_id, sheet_name, row_count, col_count, header_row,
            structure_type, classification, quality_score, analysis_status,
            summary_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'completed', ?, ?, ?)
        ON CONFLICT(source_id, sheet_name) DO UPDATE SET
            row_count = excluded.row_count,
            col_count = excluded.col_count,
            header_row = excluded.header_row,
            structure_type = excluded.structure_type,
            classification = excluded.classification,
            quality_score = excluded.quality_score,
            analysis_status = 'completed',
            summary_json = excluded.summary_json,
            updated_at = excluded.updated_at
    """, (
        source_id,
        sheet_name,
        profile.get("row_count", 0),
        profile.get("column_count", 0),
        profile.get("header_rows", [1])[0],
        profile.get("structure_type", "tabular"),
        profile.get("classification", "unknown"),
        profile.get("quality_score", 100.0),
        json.dumps({
            "quality_issues": profile.get("quality_issues", []),
            "duplicate_candidates": profile.get("duplicate_candidates", []),
            "header_rows": profile.get("header_rows", [1]),
            "data_start_row": profile.get("data_start_row", 2)
        }),
        now_iso,
        now_iso
    ))

    # Save dynamic column metadata: purge old columns first so deleted columns are removed
    cursor.execute("DELETE FROM dynamic_column_metadata WHERE source_id = ? AND sheet_name = ?", (source_id, sheet_name))

    for col in profile.get("columns", []):
        col_idx = col["column_index"]
        cursor.execute("""
            INSERT INTO dynamic_column_metadata (
                source_id, sheet_name, column_index, original_col, normalized_col,
                inferred_role, inferred_type, confidence, sample_values_json,
                stats_json, mapping_status, requires_review, reason, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            source_id,
            sheet_name,
            col_idx,
            col.get("original_name", f"Col_{col_idx+1}"),
            col.get("normalized_name", f"col_{col_idx+1}"),
            col.get("inferred_role", "unknown"),
            col.get("data_type", "text"),
            col.get("confidence", 0.5),
            json.dumps(col.get("sample_values", [])),
            json.dumps({
                "populated_pct": col.get("populated_pct", 0),
                "unique_count": col.get("unique_count", 0)
            }),
            col.get("mapping_status", "auto"),
            col.get("requires_review", 0),
            col.get("reason", ""),
            now_iso
        ))

    conn.commit()
    conn.close()


def cleanup_deleted_worksheets(source_id: str, active_sheet_names: set):
    """Purge metadata, columns, records, and inventory for worksheets that no longer exist."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT sheet_name FROM worksheet_metadata WHERE source_id = ?", (source_id,))
    db_sheets = {row["sheet_name"] for row in cursor.fetchall()}
    deleted_sheets = db_sheets - set(active_sheet_names)
    for ds in deleted_sheets:
        cursor.execute("DELETE FROM worksheet_metadata WHERE source_id = ? AND sheet_name = ?", (source_id, ds))
        cursor.execute("DELETE FROM dynamic_column_metadata WHERE source_id = ? AND sheet_name = ?", (source_id, ds))
        cursor.execute("DELETE FROM dynamic_records WHERE source_id = ? AND sheet_name = ?", (source_id, ds))
        cursor.execute("DELETE FROM inventory_records WHERE source_id = ? AND source_sheet = ?", (source_id, ds))
        cursor.execute("DELETE FROM stock_movements WHERE source_id = ? AND source_sheet = ?", (source_id, ds))
        cursor.execute("DELETE FROM spreadsheet_sheets WHERE source_id = ? AND sheet_name = ?", (source_id, ds))
    conn.commit()
    conn.close()


def save_dynamic_records(source_id: str, sheet_name: str, headers: List[str], data_rows: List[List[Any]]):
    """Save raw records preserving all columns and literal values (NA, -)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    now_iso = datetime.now(timezone.utc).isoformat()

    cursor.execute("DELETE FROM dynamic_records WHERE source_id = ? AND sheet_name = ?", (source_id, sheet_name))

    batch = []
    for row_idx, r in enumerate(data_rows, start=1):
        raw_dict = {}
        for c_idx, h in enumerate(headers):
            val = r[c_idx] if c_idx < len(r) else ""
            raw_dict[h] = val

        batch.append((
            source_id,
            sheet_name,
            row_idx,
            json.dumps(raw_dict, ensure_ascii=False),
            "{}",
            now_iso,
            now_iso
        ))

    if batch:
        cursor.executemany("""
            INSERT INTO dynamic_records (
                source_id, sheet_name, row_index, raw_data_json, inferred_data_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, batch)

    conn.commit()
    conn.close()


def get_worksheet_metadata(source_id: str, sheet_name: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    if sheet_name:
        cursor.execute("SELECT * FROM worksheet_metadata WHERE source_id = ? AND sheet_name = ?", (source_id, sheet_name))
    else:
        cursor.execute("SELECT * FROM worksheet_metadata WHERE source_id = ? ORDER BY sheet_name ASC", (source_id,))
    rows = cursor.fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["summary"] = json.loads(d.get("summary_json") or "{}")
        result.append(d)
    return result


def get_dynamic_columns(source_id: str, sheet_name: str) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM dynamic_column_metadata
        WHERE source_id = ? AND sheet_name = ?
        ORDER BY column_index ASC
    """, (source_id, sheet_name))
    rows = cursor.fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["sample_values"] = json.loads(d.get("sample_values_json") or "[]")
        d["stats"] = json.loads(d.get("stats_json") or "{}")
        result.append(d)
    return result


def update_dynamic_column_mapping(
    source_id: str,
    sheet_name: str,
    column_index: int,
    inferred_role: str,
    mapping_status: str = 'approved',
    confidence: float = 1.0
):
    conn = get_db_connection()
    cursor = conn.cursor()
    now_iso = datetime.now(timezone.utc).isoformat()
    cursor.execute("""
        UPDATE dynamic_column_metadata SET
            inferred_role = ?,
            mapping_status = ?,
            confidence = ?,
            requires_review = 0,
            updated_at = ?
        WHERE source_id = ? AND sheet_name = ? AND column_index = ?
    """, (inferred_role, mapping_status, confidence, now_iso, source_id, sheet_name, column_index))
    conn.commit()
    conn.close()


def get_dynamic_records(
    source_id: str,
    sheet_name: str,
    page: int = 1,
    limit: int = 50,
    search: str = ""
) -> Dict[str, Any]:
    """Retrieve raw/dynamic records with pagination and search across all fields."""
    conn = get_db_connection()
    cursor = conn.cursor()

    offset = (max(1, page) - 1) * limit

    if search:
        search_wild = f"%{search.strip().lower()}%"
        cursor.execute("""
            SELECT count(*) FROM dynamic_records
            WHERE source_id = ? AND sheet_name = ? AND LOWER(raw_data_json) LIKE ?
        """, (source_id, sheet_name, search_wild))
        total_row = cursor.fetchone()
        total = total_row[0] if isinstance(total_row, (list, tuple)) else list(total_row.values())[0]

        cursor.execute("""
            SELECT * FROM dynamic_records
            WHERE source_id = ? AND sheet_name = ? AND LOWER(raw_data_json) LIKE ?
            ORDER BY row_index ASC
            LIMIT ? OFFSET ?
        """, (source_id, sheet_name, search_wild, limit, offset))
    else:
        cursor.execute("""
            SELECT count(*) FROM dynamic_records
            WHERE source_id = ? AND sheet_name = ?
        """, (source_id, sheet_name))
        total_row = cursor.fetchone()
        total = total_row[0] if isinstance(total_row, (list, tuple)) else list(total_row.values())[0]

        cursor.execute("""
            SELECT * FROM dynamic_records
            WHERE source_id = ? AND sheet_name = ?
            ORDER BY row_index ASC
            LIMIT ? OFFSET ?
        """, (source_id, sheet_name, limit, offset))

    rows = cursor.fetchall()
    conn.close()

    records = []
    for r in rows:
        d = dict(r)
        d["raw_data"] = json.loads(d.get("raw_data_json") or "{}")
        d["inferred_data"] = json.loads(d.get("inferred_data_json") or "{}")
        records.append(d)

    total_pages = math.ceil(total / limit) if limit > 0 else 1
    return {
        "records": records,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": total_pages
    }


def get_data_quality_report(source_id: str) -> Dict[str, Any]:
    """Calculate comprehensive data quality statistics for a spreadsheet source."""
    conn = get_db_connection()
    cursor = conn.cursor()

    worksheets = get_worksheet_metadata(source_id)
    total_sheets = len(worksheets)

    def _val(row):
        return row[0] if isinstance(row, (list, tuple)) else list(row.values())[0]

    cursor.execute("SELECT count(*) FROM dynamic_records WHERE source_id = ?", (source_id,))
    total_rows = _val(cursor.fetchone())

    cursor.execute("SELECT count(*) FROM dynamic_column_metadata WHERE source_id = ?", (source_id,))
    total_cols = _val(cursor.fetchone())

    cursor.execute("""
        SELECT count(*) FROM dynamic_column_metadata
        WHERE source_id = ? AND inferred_role != 'unknown'
    """, (source_id,))
    recognized_cols = _val(cursor.fetchone())

    unknown_cols = max(0, total_cols - recognized_cols)

    cursor.execute("""
        SELECT count(*) FROM dynamic_column_metadata
        WHERE source_id = ? AND requires_review = 1
    """, (source_id,))
    needs_review_cols = _val(cursor.fetchone())

    conn.close()

    all_duplicates = []
    all_issues = []
    scores = []
    for ws in worksheets:
        scores.append(ws.get("quality_score", 100.0))
        summary = ws.get("summary", {})
        for d in summary.get("duplicate_candidates", []):
            all_duplicates.append(f"{ws['sheet_name']}: {d}")
        for iss in summary.get("quality_issues", []):
            all_issues.append(f"[{ws['sheet_name']}] {iss}")

    avg_score = round(sum(scores) / len(scores), 1) if scores else 100.0

    return {
        "source_id": source_id,
        "total_worksheets": total_sheets,
        "total_rows": total_rows,
        "total_columns": total_cols,
        "recognized_fields": recognized_cols,
        "unknown_fields": unknown_cols,
        "requires_review_count": needs_review_cols,
        "overall_quality_score": avg_score,
        "duplicate_candidates": all_duplicates[:25],
        "quality_issues": all_issues
    }


def get_stock_movements(
    source_id: Optional[str] = None,
    product_id: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    movement_type: Optional[str] = None,
    limit: int = 5000
) -> List[Dict[str, Any]]:
    """Operational retrieval of validated stock movements directly from PostgreSQL/SQLite."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Resolve 'active' source
    sid = source_id
    if sid == 'active':
        act = get_active_source()
        sid = act['source_id'] if act else None

    query = "SELECT * FROM stock_movements"
    conditions = []
    params: List[Any] = []

    if sid and sid != 'all':
        conditions.append("source_id = ?")
        params.append(sid)

    if product_id:
        conditions.append("(product_id = ? OR part_no = ?)")
        params.extend([product_id, product_id])

    if from_date:
        conditions.append("date >= ?")
        params.append(from_date)

    if to_date:
        conditions.append("date <= ?")
        params.append(to_date)

    if movement_type:
        conditions.append("UPPER(movement_type) LIKE ?")
        params.append(f"%{movement_type.strip().upper()}%")

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY date DESC, id DESC"
    if limit > 0:
        query += f" LIMIT {int(limit)}"

    cursor.execute(query, tuple(params))
    rows = cursor.fetchall()
    conn.close()

    results = []
    for r in rows:
        m = dict(r)
        m["validation_flags"] = json.loads(m.get("validation_flags_json") or "[]")
        results.append(m)
    return results


def get_inventory_records(
    source_id: Optional[str] = None,
    category: Optional[str] = None,
    stock_status: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 5000
) -> List[Dict[str, Any]]:
    """Operational retrieval of validated inventory records directly from PostgreSQL/SQLite."""
    conn = get_db_connection()
    cursor = conn.cursor()

    sid = source_id
    if sid == 'active':
        act = get_active_source()
        sid = act['source_id'] if act else None

    query = "SELECT * FROM inventory_records"
    conditions = []
    params: List[Any] = []

    if sid and sid != 'all':
        conditions.append("source_id = ?")
        params.append(sid)

    if category:
        conditions.append("category = ?")
        params.append(category)

    if stock_status:
        conditions.append("stock_status = ?")
        params.append(stock_status)

    if search:
        s_term = f"%{search.strip().lower()}%"
        conditions.append("(LOWER(part_no) LIKE ? OR LOWER(description) LIKE ? OR LOWER(product_id) LIKE ?)")
        params.extend([s_term, s_term, s_term])

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY id ASC"
    if limit > 0:
        query += f" LIMIT {int(limit)}"

    cursor.execute(query, tuple(params))
    rows = cursor.fetchall()
    conn.close()

    results = []
    for r in rows:
        p = dict(r)
        p["extra_fields"] = json.loads(p.get("extra_fields_json") or "{}")
        p["validation_flags"] = json.loads(p.get("validation_flags_json") or "[]")
        results.append(p)
    return results

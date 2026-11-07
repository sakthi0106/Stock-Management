-- Migration: 001_unified_pipeline.sql
-- Description: Unified Database Pipeline supporting PostgreSQL (Render) and SQLite.
-- Creates operational tables for dynamic schemas, inventory master, stock movements, and synchronization tracking.

CREATE TABLE IF NOT EXISTS spreadsheet_sources (
    id SERIAL PRIMARY KEY,
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
);

CREATE TABLE IF NOT EXISTS worksheet_metadata (
    id SERIAL PRIMARY KEY,
    source_id VARCHAR(100) NOT NULL,
    sheet_name VARCHAR(255) NOT NULL,
    row_count INTEGER DEFAULT 0,
    col_count INTEGER DEFAULT 0,
    header_row INTEGER DEFAULT 1,
    structure_type VARCHAR(100) DEFAULT 'tabular',
    classification VARCHAR(100) DEFAULT 'unknown',
    quality_score REAL DEFAULT 100.0,
    analysis_status VARCHAR(50) DEFAULT 'completed',
    summary_json TEXT DEFAULT '{}',
    created_at VARCHAR(100) NOT NULL,
    updated_at VARCHAR(100) NOT NULL,
    UNIQUE(source_id, sheet_name)
);

CREATE TABLE IF NOT EXISTS dynamic_column_metadata (
    id SERIAL PRIMARY KEY,
    source_id VARCHAR(100) NOT NULL,
    sheet_name VARCHAR(255) NOT NULL,
    column_index INTEGER NOT NULL,
    original_col TEXT NOT NULL,
    normalized_col TEXT NOT NULL,
    inferred_role VARCHAR(100) NOT NULL,
    inferred_type VARCHAR(50) DEFAULT 'text',
    confidence REAL DEFAULT 0.5,
    sample_values_json TEXT DEFAULT '[]',
    stats_json TEXT DEFAULT '{}',
    mapping_status VARCHAR(50) DEFAULT 'auto',
    requires_review INTEGER DEFAULT 0,
    reason TEXT DEFAULT '',
    updated_at VARCHAR(100) NOT NULL,
    UNIQUE(source_id, sheet_name, column_index)
);

CREATE TABLE IF NOT EXISTS dynamic_records (
    id SERIAL PRIMARY KEY,
    source_id VARCHAR(100) NOT NULL,
    sheet_name VARCHAR(255) NOT NULL,
    row_index INTEGER NOT NULL,
    raw_data_json TEXT NOT NULL,
    inferred_data_json TEXT DEFAULT '{}',
    created_at VARCHAR(100) NOT NULL,
    updated_at VARCHAR(100) NOT NULL,
    UNIQUE(source_id, sheet_name, row_index)
);

CREATE TABLE IF NOT EXISTS spreadsheet_sheets (
    id SERIAL PRIMARY KEY,
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
);

CREATE TABLE IF NOT EXISTS sheet_column_mappings (
    id SERIAL PRIMARY KEY,
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
    extra_mappings_json TEXT DEFAULT '{}',
    updated_at VARCHAR(100) NOT NULL,
    UNIQUE(source_id, sheet_name)
);

CREATE TABLE IF NOT EXISTS sync_history (
    id SERIAL PRIMARY KEY,
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
);

CREATE TABLE IF NOT EXISTS sync_runs (
    id SERIAL PRIMARY KEY,
    timestamp VARCHAR(100) NOT NULL,
    status VARCHAR(50) NOT NULL,
    sheets_processed INTEGER DEFAULT 0,
    products_count INTEGER DEFAULT 0,
    movements_count INTEGER DEFAULT 0,
    fingerprint VARCHAR(255),
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS inventory_records (
    id SERIAL PRIMARY KEY,
    source_id VARCHAR(100) NOT NULL,
    source_sheet VARCHAR(255) NOT NULL,
    source_row INTEGER NOT NULL,
    product_id VARCHAR(255) NOT NULL,
    part_no TEXT NOT NULL,
    description TEXT NOT NULL,
    category TEXT NOT NULL,
    uom VARCHAR(50) NOT NULL,
    unit_price TEXT, -- Preserves 'NA' and '-'
    opening_stock TEXT,
    current_stock TEXT,
    latest_date VARCHAR(50),
    min_level REAL DEFAULT 10,
    stock_status VARCHAR(50),
    period VARCHAR(50),
    extra_fields_json TEXT DEFAULT '{}',
    validation_flags_json TEXT DEFAULT '[]',
    updated_at VARCHAR(100) NOT NULL,
    UNIQUE(source_id, source_sheet, source_row)
);

CREATE TABLE IF NOT EXISTS stock_movements (
    id SERIAL PRIMARY KEY,
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
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id SERIAL PRIMARY KEY,
    timestamp VARCHAR(100) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    description TEXT NOT NULL,
    details TEXT
);

-- Performance Indexes
CREATE INDEX IF NOT EXISTS idx_inv_source ON inventory_records(source_id, source_sheet);
CREATE INDEX IF NOT EXISTS idx_inv_product ON inventory_records(product_id);
CREATE INDEX IF NOT EXISTS idx_mov_source ON stock_movements(source_id, source_sheet);
CREATE INDEX IF NOT EXISTS idx_mov_date ON stock_movements(date);
CREATE INDEX IF NOT EXISTS idx_mov_prod ON stock_movements(product_id);

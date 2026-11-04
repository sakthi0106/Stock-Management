export type SpecialValue = string | number | null;

export interface SpreadsheetSource {
  source_id: string;
  name: string;
  spreadsheet_id: string;
  description: string;
  period: string;
  status: 'active' | 'archived' | 'disabled';
  is_active: number; // 1 or 0
  poll_interval_seconds: number;
  last_sync_at: string | null;
  last_sync_status: 'pending' | 'success' | 'warning' | 'error';
  last_sync_error: string | null;
  sheets_count: number;
  products_count: number;
  movements_count: number;
  source_type?: 'google_sheets' | 'excel_upload';
  total_worksheets?: number;
  total_records?: number;
  last_analyzed_at?: string | null;
  analysis_status?: 'idle' | 'analyzing' | 'completed' | 'failed';
  live_state?: string;
  is_live_google_sheet?: boolean;
  sheets?: SheetInfo[];
  live_sheets?: SheetSyncStatus[];
  created_at?: string;
  updated_at?: string;
}

export interface SheetInfo {
  sheet_name: string;
  sheet_index: number;
  row_count: number;
  col_count: number;
  status: string;
  last_sync_at: string | null;
  issues: string[];
  headers: string[];
  amount_columns: string[];
  date_columns: string[];
  unit_price_col?: string;
  part_no_col?: string;
}

export interface Product {
  product_id: string;
  description: string;
  part_no: string;
  category: string;
  uom: string;
  unit_price: SpecialValue;
  opening_stock: SpecialValue;
  current_stock: SpecialValue;
  latest_date?: string;
  min_level: number;
  stock_status: 'In Stock' | 'Low Stock' | 'Out of Stock' | 'Unknown';
  source_sheet: string;
  source_row: number;
  extra_fields: Record<string, SpecialValue>;
  validation_flags: string[];
}

export interface Movement {
  movement_id: string;
  date: string;
  product_id: string;
  part_no?: string;
  description?: string;
  movement_type: 'IN' | 'OUT';
  qty: SpecialValue;
  uom: string;
  opening_stock: SpecialValue;
  in_qty: number;
  out_qty: number;
  closing_stock: SpecialValue;
  reference_no?: string;
  party_name?: string;
  remarks?: string;
  source_sheet: string;
  source_row: number;
  validation_flags: string[];
}

export interface InventoryFilters {
  search: string;
  sheet: string;
  category: string;
  partNo: string;
  uom: string;
  status: string;
  fromDate: string;
  toDate: string;
  page: number;
  pageSize: number;
  sortBy: string;
  sortOrder: 'asc' | 'desc';
}

export interface SheetSyncStatus {
  name: string;
  status: 'success' | 'warning' | 'error';
  row_count: number;
  last_sync: string | null;
  issues: string[];
}

export interface SyncStatus {
  state: 'connected' | 'syncing' | 'error' | 'disconnected' | 'demo';
  is_live_google_sheet: boolean;
  lastSuccess: string | null;
  lastError: string | null;
  sheetsProcessed: number;
  sheets: SheetSyncStatus[];
}

export interface DashboardKPI {
  total_products: number;
  in_stock_count: number;
  low_stock_count: number;
  out_of_stock_count: number;
  unknown_stock_count?: number;
  total_movements_count?: number;
  total_in_transactions?: number;
  total_out_transactions?: number;
  uom_quantities: Record<string, number>;
  inward_by_uom: Record<string, number>;
  outward_by_uom: Record<string, number>;
  daily_trends: { date: string; in: number; out: number; transactions?: number }[];
  category_distribution: { category: string; count: number }[];
  status_distribution: { status: string; count: number }[];
  recent_movements?: Movement[];
  last_updated: string | null;
  sync_status?: SyncStatus;
}

export interface DataQualityIssue {
  type: string;
  severity: 'INFO' | 'WARNING' | 'CRITICAL';
  message: string;
}

export interface DataQualityReport {
  total_issues: number;
  issues: DataQualityIssue[];
  duplicate_ids: string[];
  sheets_analyzed: number;
}

// ==========================================
// SPREADSHEET INTELLIGENCE TYPES
// ==========================================

export interface WorksheetMetadata {
  id: number;
  source_id: string;
  sheet_name: string;
  row_count: number;
  col_count: number;
  header_row: number;
  structure_type: string;
  classification: 'inventory_summary' | 'stock_movement' | 'price_catalog' | 'reference_catalog' | 'general_data' | 'unknown';
  quality_score: number;
  analysis_status: string;
  summary: {
    quality_issues?: string[];
    duplicate_candidates?: string[];
    header_rows?: number[];
    data_start_row?: number;
  };
  created_at: string;
  updated_at: string;
}

export interface DynamicColumn {
  id: number;
  source_id: string;
  sheet_name: string;
  column_index: number;
  original_col: string;
  normalized_col: string;
  inferred_role:
    | 'product_id'
    | 'description'
    | 'category'
    | 'uom'
    | 'unit_price'
    | 'opening_stock'
    | 'in_qty'
    | 'out_qty'
    | 'closing_stock'
    | 'date'
    | 'unknown';
  inferred_type: string;
  confidence: number;
  sample_values: string[];
  stats: {
    populated_pct?: number;
    unique_count?: number;
  };
  mapping_status: 'auto' | 'approved' | 'rejected' | 'custom';
  requires_review: number;
  reason: string;
  updated_at: string;
}

export interface DynamicRecord {
  id: number;
  source_id: string;
  sheet_name: string;
  row_index: number;
  raw_data: Record<string, any>;
  inferred_data: Record<string, any>;
  created_at: string;
  updated_at: string;
}

export interface IntelligenceDataQualityReport {
  source_id: string;
  total_worksheets: number;
  total_rows: number;
  total_columns: number;
  recognized_fields: number;
  unknown_fields: number;
  requires_review_count: number;
  overall_quality_score: number;
  duplicate_candidates: string[];
  quality_issues: string[];
}

export interface AnalysisTaskStatus {
  status: 'pending' | 'analyzing' | 'completed' | 'failed' | 'unknown';
  progress?: string;
  error?: string;
  source_id?: string;
  total_sheets?: number;
  total_records?: number;
}


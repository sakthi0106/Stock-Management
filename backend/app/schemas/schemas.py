"""
Pydantic v2 validation schemas
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, EmailStr, Field

# ----------------- User Schemas -----------------
class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    email: str
    full_name: str
    role: str

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    role: str = "PURCHASE_TEAM"

class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    is_active: bool
    last_login_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True

# ----------------- Product Schemas -----------------
class ProductResponse(BaseModel):
    id: int
    product_code: str
    name: str
    category: str
    unit_of_measure: str
    opening_stock: float
    total_inward: float
    total_outward: float
    current_balance: float
    min_threshold: float
    unit_cost: Optional[float] = None
    bin_location: Optional[str] = None
    last_movement_date: Optional[datetime] = None
    status: str = "HEALTHY" # HEALTHY, LOW_STOCK, OUT_OF_STOCK
    is_active: bool

    class Config:
        from_attributes = True

class ProductDetailResponse(ProductResponse):
    threshold_alert_enabled: bool = True
    recent_transactions: List[Any] = []

# ----------------- Transaction Schemas -----------------
class StockTransactionResponse(BaseModel):
    id: int
    product_id: int
    product_code: Optional[str] = None
    product_name: Optional[str] = None
    transaction_date: datetime
    transaction_id_source: Optional[str] = None
    transaction_type: str # INWARD or OUTWARD
    quantity: float
    unit: str
    balance_after: Optional[float] = None
    supplier_or_recipient: Optional[str] = None
    reference_no: Optional[str] = None
    challan_no: Optional[str] = None
    handled_by: Optional[str] = None
    remarks: Optional[str] = None
    source_sheet: str
    sync_run_id: Optional[int] = None

    class Config:
        from_attributes = True

# ----------------- Dashboard Schemas -----------------
class UnitStockSummary(BaseModel):
    unit: str
    total_quantity: float
    product_count: int

class DashboardSummaryResponse(BaseModel):
    total_products: int
    total_stock_by_unit: List[UnitStockSummary]
    low_stock_count: int
    out_of_stock_count: int
    healthy_stock_count: int
    last_sync_time: Optional[datetime] = None
    last_sync_status: Optional[str] = None
    is_data_fresh: bool = True
    data_freshness_warning: Optional[str] = None
    recent_inward: List[StockTransactionResponse]
    recent_outward: List[StockTransactionResponse]
    low_stock_alerts: List[ProductResponse]

# ----------------- Sync & Excel Schemas -----------------
class SheetInspection(BaseModel):
    sheet_name: str
    total_rows: int
    total_cols: int
    sample_headers: List[str]
    sample_rows: List[List[Any]]

class WorkbookInspectResponse(BaseModel):
    file_name: str
    file_hash: str
    sheets: List[SheetInspection]
    detected_recommendations: Dict[str, Any]

class ColumnMappingRequest(BaseModel):
    worksheet_name: str
    header_row_index: int = 1
    sheet_type: str = "SUMMARY" # SUMMARY, INWARD_REGISTER, OUTWARD_REGISTER, LEDGER
    product_code_col: str
    product_name_col: Optional[str] = None
    category_col: Optional[str] = None
    unit_col: Optional[str] = None
    current_balance_col: Optional[str] = None
    opening_stock_col: Optional[str] = None
    inward_qty_col: Optional[str] = None
    outward_qty_col: Optional[str] = None
    min_threshold_col: Optional[str] = None
    unit_cost_col: Optional[str] = None
    location_col: Optional[str] = None
    date_col: Optional[str] = None
    ref_col: Optional[str] = None
    party_col: Optional[str] = None
    remarks_col: Optional[str] = None

class WorkbookConfigResponse(BaseModel):
    id: int
    name: str
    file_path_hint: Optional[str] = None
    worksheet_name: str
    header_row_index: int
    column_mapping: Dict[str, Any]
    dedup_rule: str
    is_active: bool
    last_file_hash: Optional[str] = None
    updated_at: datetime

    class Config:
        from_attributes = True

class SyncRunResponse(BaseModel):
    id: int
    source_type: str
    status: str
    file_name: str
    file_hash: str
    rows_read: int
    rows_inserted: int
    rows_updated: int
    rows_skipped: int
    error_log: Optional[str] = None
    started_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# ----------------- Audit Log Schemas -----------------
class AuditLogResponse(BaseModel):
    id: int
    user_email: Optional[str] = None
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    details: Optional[str] = None
    ip_address: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

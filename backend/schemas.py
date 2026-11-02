from typing import Dict, List, Any, Optional, Union
from pydantic import BaseModel, Field

class Product(BaseModel):
    product_id: str
    description: str
    part_no: Optional[str] = None
    category: Optional[str] = None
    uom: Optional[str] = "PCS"
    unit_price: Union[float, str, None] = None  # May be literal "NA" or "-"
    opening_stock: Union[float, int, str, None] = None
    current_stock: Union[float, int, str, None] = None
    min_level: Union[float, int, None] = None
    stock_status: str = "In Stock"  # In Stock, Low Stock, Out of Stock, Unknown
    source_sheet: str
    source_row: int
    extra_fields: Dict[str, Any] = Field(default_factory=dict)
    validation_flags: List[str] = Field(default_factory=list)

class Movement(BaseModel):
    movement_id: str
    date: str
    product_id: str
    part_no: Optional[str] = None
    description: Optional[str] = None
    movement_type: str  # "IN" or "OUT"
    qty: Union[float, int, str]
    uom: str
    opening_stock: Union[float, int, str, None] = None
    in_qty: Union[float, int, None] = 0
    out_qty: Union[float, int, None] = 0
    closing_stock: Union[float, int, str, None] = None
    reference_no: Optional[str] = None
    party_name: Optional[str] = None
    remarks: Optional[str] = None
    source_sheet: str
    source_row: int
    validation_flags: List[str] = Field(default_factory=list)

class SheetSyncStatus(BaseModel):
    name: str
    status: str  # success, warning, error
    row_count: int
    last_sync: Optional[str] = None
    issues: List[str] = Field(default_factory=list)

class SyncStatusResponse(BaseModel):
    state: str  # connected, syncing, error, disconnected
    is_live_google_sheet: bool
    lastSuccess: Optional[str] = None
    lastError: Optional[str] = None
    sheetsProcessed: int
    sheets: List[SheetSyncStatus] = Field(default_factory=list)

class DashboardKPI(BaseModel):
    total_products: int
    in_stock_count: int
    low_stock_count: int
    out_of_stock_count: int
    uom_quantities: Dict[str, float]  # Quantities separated by UOM
    inward_by_uom: Dict[str, float]
    outward_by_uom: Dict[str, float]
    last_updated: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)

"""
Stock Movement History API Endpoints
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List, Optional
from datetime import datetime

from app.db.session import get_db
from app.models.models import StockTransaction, Product
from app.schemas.schemas import StockTransactionResponse
from app.core.security import require_roles, UserRole

router = APIRouter(prefix="/movements", tags=["Movements"])

@router.get("", response_model=List[StockTransactionResponse])
def get_movements(
    product_code: Optional[str] = Query(None, description="Filter by product code"),
    transaction_type: Optional[str] = Query(None, description="INWARD or OUTWARD"),
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    current_user: dict = Depends(require_roles(UserRole.ALL)),
    db: Session = Depends(get_db)
):
    query = db.query(StockTransaction).join(Product)

    if product_code:
        query = query.filter(Product.product_code.ilike(f"%{product_code.strip()}%"))

    if transaction_type and transaction_type in ["INWARD", "OUTWARD"]:
        query = query.filter(StockTransaction.transaction_type == transaction_type)

    if start_date:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            query = query.filter(StockTransaction.transaction_date >= start_dt)
        except ValueError:
            pass

    if end_date:
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            query = query.filter(StockTransaction.transaction_date <= end_dt)
        except ValueError:
            pass

    txns = query.order_by(desc(StockTransaction.transaction_date)).offset(skip).limit(limit).all()

    return [
        StockTransactionResponse(
            id=t.id,
            product_id=t.product_id,
            product_code=t.product.product_code if t.product else "",
            product_name=t.product.name if t.product else "",
            transaction_date=t.transaction_date,
            transaction_id_source=t.transaction_id_source,
            transaction_type=t.transaction_type,
            quantity=t.quantity,
            unit=t.unit,
            balance_after=t.balance_after,
            supplier_or_recipient=t.supplier_or_recipient,
            reference_no=t.reference_no,
            remarks=t.remarks,
            source_sheet=t.source_sheet,
            sync_run_id=t.sync_run_id
        )
        for t in txns
    ]

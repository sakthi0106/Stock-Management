"""
Dashboard Summary Endpoints
Aggregates key metrics for Directors, Purchase Teams, and Administrators.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from datetime import datetime, timezone, timedelta
from typing import List

from app.db.session import get_db
from app.models.models import Product, StockTransaction, SyncRun
from app.schemas.schemas import DashboardSummaryResponse, UnitStockSummary, StockTransactionResponse, ProductResponse
from app.core.security import require_roles, UserRole

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

@router.get("/summary", response_model=DashboardSummaryResponse)
def get_dashboard_summary(
    current_user: dict = Depends(require_roles(UserRole.ALL)),
    db: Session = Depends(get_db)
):
    total_products = db.query(Product).count()

    # Stock grouped strictly by unit to avoid combining incompatible units into misleading totals
    unit_groups = (
        db.query(
            Product.unit_of_measure,
            func.sum(Product.current_balance).label("total_qty"),
            func.count(Product.id).label("prod_count")
        )
        .group_by(Product.unit_of_measure)
        .all()
    )
    
    total_stock_by_unit = [
        UnitStockSummary(
            unit=u[0] or "PCS",
            total_quantity=round(float(u[1] or 0.0), 2),
            product_count=int(u[2] or 0)
        )
        for u in unit_groups
    ]

    # Status counts
    all_prods = db.query(Product).all()
    out_of_stock_count = 0
    low_stock_count = 0
    healthy_stock_count = 0
    low_stock_alerts = []

    for p in all_prods:
        status_label = "HEALTHY"
        if p.current_balance <= 0.0:
            out_of_stock_count += 1
            status_label = "OUT_OF_STOCK"
            low_stock_alerts.append(p)
        elif p.min_threshold > 0 and p.current_balance <= p.min_threshold:
            low_stock_count += 1
            status_label = "LOW_STOCK"
            low_stock_alerts.append(p)
        else:
            healthy_stock_count += 1

    # Last sync run
    last_sync = db.query(SyncRun).order_by(desc(SyncRun.started_at)).first()
    last_sync_time = last_sync.started_at if last_sync else None
    last_sync_status = last_sync.status if last_sync else "NEVER_RUN"

    # Data freshness calculation
    is_fresh = True
    freshness_warning = None
    if not last_sync:
        is_fresh = False
        freshness_warning = "Workbook has not been synchronized yet. Displaying initial or mock catalog."
    elif last_sync.status == "FAILED":
        is_fresh = False
        freshness_warning = f"Last synchronization failed on {last_sync.started_at.strftime('%Y-%m-%d %H:%M')}. Data may be stale."
    else:
        # Check if more than 24 hours
        now = datetime.now(timezone.utc)
        if last_sync.started_at.tzinfo is None:
            sync_dt = last_sync.started_at.replace(tzinfo=timezone.utc)
        else:
            sync_dt = last_sync.started_at
            
        if now - sync_dt > timedelta(hours=24):
            is_fresh = False
            freshness_warning = f"Data was last synchronized {int((now - sync_dt).total_seconds() / 3600)} hours ago."

    # Recent inward transactions
    recent_inward_records = (
        db.query(StockTransaction)
        .filter(StockTransaction.transaction_type == "INWARD")
        .order_by(desc(StockTransaction.transaction_date))
        .limit(5)
        .all()
    )

    # Recent outward transactions
    recent_outward_records = (
        db.query(StockTransaction)
        .filter(StockTransaction.transaction_type == "OUTWARD")
        .order_by(desc(StockTransaction.transaction_date))
        .limit(5)
        .all()
    )

    def format_txn(t: StockTransaction) -> StockTransactionResponse:
        return StockTransactionResponse(
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

    def format_prod(p: Product) -> ProductResponse:
        st = "HEALTHY"
        if p.current_balance <= 0.0:
            st = "OUT_OF_STOCK"
        elif p.min_threshold > 0 and p.current_balance <= p.min_threshold:
            st = "LOW_STOCK"
        return ProductResponse(
            id=p.id,
            product_code=p.product_code,
            name=p.name,
            category=p.category,
            unit_of_measure=p.unit_of_measure,
            opening_stock=p.opening_stock,
            total_inward=p.total_inward,
            total_outward=p.total_outward,
            current_balance=p.current_balance,
            min_threshold=p.min_threshold,
            unit_cost=p.unit_cost,
            bin_location=p.bin_location,
            last_movement_date=p.last_movement_date,
            status=st,
            is_active=p.is_active
        )

    return DashboardSummaryResponse(
        total_products=total_products,
        total_stock_by_unit=total_stock_by_unit,
        low_stock_count=low_stock_count,
        out_of_stock_count=out_of_stock_count,
        healthy_stock_count=healthy_stock_count,
        last_sync_time=last_sync_time,
        last_sync_status=last_sync_status,
        is_data_fresh=is_fresh,
        data_freshness_warning=freshness_warning,
        recent_inward=[format_txn(t) for t in recent_inward_records],
        recent_outward=[format_txn(t) for t in recent_outward_records],
        low_stock_alerts=[format_prod(p) for p in low_stock_alerts[:10]]
    )

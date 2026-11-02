"""
Product Catalog and Detail Endpoints
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_, desc
from typing import List, Optional

from app.db.session import get_db
from app.models.models import Product, StockTransaction
from app.schemas.schemas import ProductResponse, ProductDetailResponse, StockTransactionResponse
from app.core.security import require_roles, UserRole

router = APIRouter(prefix="/products", tags=["Products"])

@router.get("", response_model=List[ProductResponse])
def get_products(
    search: Optional[str] = Query(None, description="Search by code or name"),
    category: Optional[str] = Query(None, description="Filter by category"),
    status: Optional[str] = Query(None, description="HEALTHY, LOW_STOCK, OUT_OF_STOCK"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    current_user: dict = Depends(require_roles(UserRole.ALL)),
    db: Session = Depends(get_db)
):
    query = db.query(Product).filter(Product.is_active == True)

    if search:
        search_pattern = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Product.product_code.ilike(search_pattern),
                Product.name.ilike(search_pattern)
            )
        )

    if category:
        query = query.filter(Product.category == category)

    products = query.order_by(Product.product_code).all()

    # Filter by status if requested
    filtered = []
    for p in products:
        st = "HEALTHY"
        if p.current_balance <= 0:
            st = "OUT_OF_STOCK"
        elif p.min_threshold > 0 and p.current_balance <= p.min_threshold:
            st = "LOW_STOCK"

        if status and status != "ALL" and st != status:
            continue

        resp = ProductResponse(
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
        filtered.append(resp)

    return filtered[skip : skip + limit]

@router.get("/categories", response_model=List[str])
def get_categories(
    current_user: dict = Depends(require_roles(UserRole.ALL)),
    db: Session = Depends(get_db)
):
    results = db.query(Product.category).distinct().order_by(Product.category).all()
    return [r[0] for r in results if r[0]]

@router.get("/{product_id}", response_model=ProductDetailResponse)
def get_product_details(
    product_id: int,
    current_user: dict = Depends(require_roles(UserRole.ALL)),
    db: Session = Depends(get_db)
):
    p = db.query(Product).filter(Product.id == product_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Product not found.")

    st = "HEALTHY"
    if p.current_balance <= 0:
        st = "OUT_OF_STOCK"
    elif p.min_threshold > 0 and p.current_balance <= p.min_threshold:
        st = "LOW_STOCK"

    # Fetch recent transactions
    txns = (
        db.query(StockTransaction)
        .filter(StockTransaction.product_id == p.id)
        .order_by(desc(StockTransaction.transaction_date))
        .limit(20)
        .all()
    )

    formatted_txns = [
        StockTransactionResponse(
            id=t.id,
            product_id=t.product_id,
            product_code=p.product_code,
            product_name=p.name,
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

    return ProductDetailResponse(
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
        is_active=p.is_active,
        threshold_alert_enabled=True,
        recent_transactions=formatted_txns
    )

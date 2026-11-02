"""
SQLAlchemy ORM Database Models
Designed for PostgreSQL with full compatibility for SQLite.
"""
from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Boolean, ForeignKey, Text, Index, UniqueConstraint
)
from sqlalchemy.orm import relationship
from app.db.session import Base

def utc_now():
    return datetime.now(timezone.utc)

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False, default="PURCHASE_TEAM")  # DIRECTOR, PURCHASE_TEAM, ADMIN
    is_active = Column(Boolean, default=True, nullable=False)
    last_login_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    sync_runs = relationship("SyncRun", back_populates="triggered_by_user")
    audit_logs = relationship("AuditLog", back_populates="user")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    product_code = Column(String(100), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=False, index=True)
    category = Column(String(100), index=True, nullable=False, default="General")
    unit_of_measure = Column(String(50), nullable=False, default="PCS")
    opening_stock = Column(Float, default=0.0, nullable=False)
    total_inward = Column(Float, default=0.0, nullable=False)
    total_outward = Column(Float, default=0.0, nullable=False)
    current_balance = Column(Float, default=0.0, nullable=False)
    min_threshold = Column(Float, default=0.0, nullable=False)
    unit_cost = Column(Float, nullable=True)
    bin_location = Column(String(100), nullable=True)
    last_movement_date = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    transactions = relationship("StockTransaction", back_populates="product", cascade="all, delete-orphan")
    threshold = relationship("StockThreshold", back_populates="product", uselist=False, cascade="all, delete-orphan")


class StockTransaction(Base):
    __tablename__ = "stock_transactions"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    transaction_date = Column(DateTime, nullable=False, index=True)
    transaction_id_source = Column(String(100), nullable=True, index=True)  # From Excel if provided
    transaction_type = Column(String(20), nullable=False, index=True)       # INWARD or OUTWARD
    quantity = Column(Float, nullable=False)
    unit = Column(String(50), nullable=False)
    balance_after = Column(Float, nullable=True)
    supplier_or_recipient = Column(String(255), nullable=True)
    reference_no = Column(String(100), nullable=True, index=True)            # PO or Work Order
    challan_no = Column(String(100), nullable=True)
    handled_by = Column(String(100), nullable=True)
    remarks = Column(Text, nullable=True)
    source_sheet = Column(String(100), nullable=False)
    dedup_hash = Column(String(64), unique=True, index=True, nullable=False) # SHA-256 idempotency hash
    sync_run_id = Column(Integer, ForeignKey("sync_runs.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    product = relationship("Product", back_populates="transactions")
    sync_run = relationship("SyncRun", back_populates="transactions")


class WorkbookConfig(Base):
    __tablename__ = "workbook_configurations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, default="Primary Excel Inventory")
    file_path_hint = Column(String(500), nullable=True)
    worksheet_name = Column(String(100), nullable=False, default="Stock Summary")
    header_row_index = Column(Integer, default=1, nullable=False)
    column_mapping = Column(Text, nullable=False, default="{}") # JSON-serialized mapping
    dedup_rule = Column(String(100), default="COMPOSITE_HASH", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    last_file_hash = Column(String(64), nullable=True)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id = Column(Integer, primary_key=True, index=True)
    triggered_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    source_type = Column(String(50), nullable=False, default="AGENT")  # AGENT, MANUAL_UPLOAD, SCHEDULED
    status = Column(String(50), nullable=False, default="SUCCESS")     # SUCCESS, PARTIAL, FAILED
    file_name = Column(String(255), nullable=False)
    file_hash = Column(String(64), nullable=False, index=True)
    rows_read = Column(Integer, default=0, nullable=False)
    rows_inserted = Column(Integer, default=0, nullable=False)
    rows_updated = Column(Integer, default=0, nullable=False)
    rows_skipped = Column(Integer, default=0, nullable=False)
    error_log = Column(Text, nullable=True) # JSON or text of error details
    started_at = Column(DateTime, default=utc_now, nullable=False)
    completed_at = Column(DateTime, nullable=True)

    triggered_by_user = relationship("User", back_populates="sync_runs")
    transactions = relationship("StockTransaction", back_populates="sync_run")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    user_email = Column(String(255), nullable=True)
    action = Column(String(100), nullable=False, index=True)
    resource_type = Column(String(100), nullable=False)
    resource_id = Column(String(100), nullable=True)
    details = Column(Text, nullable=True)
    ip_address = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False, index=True)

    user = relationship("User", back_populates="audit_logs")


class StockThreshold(Base):
    __tablename__ = "stock_thresholds"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), unique=True, nullable=False)
    min_quantity = Column(Float, nullable=False, default=10.0)
    alert_email_enabled = Column(Boolean, default=True, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    product = relationship("Product", back_populates="threshold")

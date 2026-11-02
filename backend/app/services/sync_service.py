"""
Excel Synchronization and Deduplication Service
Ensures idempotency, transactional safety, and audit logging.
"""
import hashlib
import json
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from app.models.models import Product, StockTransaction, SyncRun, AuditLog, WorkbookConfig
from app.services.excel_service import ExcelService

class SyncService:
    @staticmethod
    def generate_daily_transaction_hash(
        source_id: str,
        sheet_name: str,
        row_index: int,
        date_str: str,
        product_code: str,
        txn_type: str
    ) -> str:
        """Stable identity for a daily stock cell, independent of later quantity edits."""
        key = f"DAILY:{source_id}:{sheet_name}:{row_index}:{date_str}:{product_code}:{txn_type}"
        return hashlib.sha256(key.encode("utf-8")).hexdigest()

    @staticmethod
    def generate_transaction_hash(
        sheet_name: str,
        row_index: int,
        date_str: str,
        product_code: str,
        txn_type: str,
        quantity: float,
        reference: Optional[str]
    ) -> str:
        """Deterministic hash for transaction deduplication."""
        raw_key = f"{sheet_name}|{row_index}|{date_str}|{product_code}|{txn_type}|{quantity:.4f}|{reference or ''}"
        return hashlib.sha256(raw_key.encode('utf-8')).hexdigest()

    @staticmethod
    def execute_sync(
        db: Session,
        file_bytes: bytes,
        file_name: str,
        source_type: str = "MANUAL_UPLOAD",
        triggered_by_user_id: Optional[int] = None,
        override_config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Executes a complete synchronization of the workbook.
        Idempotent: Identical rows already in database are skipped without error.
        """
        file_hash = ExcelService.calculate_file_hash(file_bytes)
        
        # Create sync run record
        sync_run = SyncRun(
            triggered_by_user_id=triggered_by_user_id,
            source_type=source_type,
            status="RUNNING",
            file_name=file_name,
            file_hash=file_hash,
            started_at=datetime.now(timezone.utc)
        )
        db.add(sync_run)
        db.commit()
        db.refresh(sync_run)

        total_read = 0
        total_inserted = 0
        total_updated = 0
        total_skipped = 0
        all_errors = []
        expected_daily_hashes = set()
        daily_source_id = hashlib.sha256(file_name.lower().encode("utf-8")).hexdigest()[:12]
        has_daily_register = False

        try:
            inspected = ExcelService.inspect_workbook(file_bytes, file_name)
            recommendations = inspected["detected_recommendations"]

            # We process each sheet based on detected or configured mappings
            for sheet_name, rec in recommendations.items():
                sheet_type = rec["likely_sheet_type"]
                mapping = rec["mappings"]

                if sheet_type == "DAILY_STOCK_REGISTER":
                    has_daily_register = True
                    parsed = ExcelService.parse_daily_stock_sheet(file_bytes, sheet_name)
                    if parsed is None:
                        all_errors.append({
                            "sheet_name": sheet_name,
                            "reason": "Daily stock register layout could not be parsed."
                        })
                        continue

                    total_read += len(parsed["products"])
                    all_errors.extend(parsed["errors"])

                    products_by_code = {}
                    for row in parsed["products"]:
                        code = row["product_code"]
                        prod = db.query(Product).filter(Product.product_code == code).first()
                        if not prod:
                            prod = Product(product_code=code, name=row["product_name"])
                            db.add(prod)
                            db.flush()
                            total_inserted += 1
                        else:
                            total_updated += 1

                        prod.name = row["product_name"]
                        prod.category = row["category"]
                        prod.unit_of_measure = row["unit"]
                        prod.opening_stock = row["opening_stock"]
                        prod.total_inward = row["total_inward"]
                        prod.total_outward = row["total_outward"]
                        prod.current_balance = row["current_balance"]
                        prod.unit_cost = row["unit_cost"]
                        prod.last_movement_date = row["last_movement_date"]
                        prod.is_active = True
                        products_by_code[code] = (row, prod)

                    for row in parsed["products"]:
                        _, prod = products_by_code[row["product_code"]]
                        for movement in row["movements"]:
                            date_str = movement["transaction_date"].strftime("%Y-%m-%d")
                            marker = (
                                f"DAILY:{daily_source_id}:{sheet_name}:"
                                f"{movement['row_index']}:{date_str}:{movement['transaction_type']}"
                            )
                            dedup_hash = SyncService.generate_daily_transaction_hash(
                                source_id=daily_source_id,
                                sheet_name=sheet_name,
                                row_index=movement["row_index"],
                                date_str=date_str,
                                product_code=movement["product_code"],
                                txn_type=movement["transaction_type"],
                            )
                            expected_daily_hashes.add(dedup_hash)
                            txn = db.query(StockTransaction).filter(
                                StockTransaction.dedup_hash == dedup_hash
                            ).first()

                            if txn is None:
                                txn = StockTransaction(
                                    product_id=prod.id,
                                    transaction_date=movement["transaction_date"],
                                    transaction_id_source=marker,
                                    transaction_type=movement["transaction_type"],
                                    quantity=movement["quantity"],
                                    unit=row["unit"],
                                    balance_after=movement["balance_after"],
                                    source_sheet=f"{sheet_name} [Daily]",
                                    dedup_hash=dedup_hash,
                                    sync_run_id=sync_run.id,
                                )
                                db.add(txn)
                                total_inserted += 1
                            elif txn.quantity != movement["quantity"]:
                                txn.product_id = prod.id
                                txn.transaction_date = movement["transaction_date"]
                                txn.quantity = movement["quantity"]
                                txn.unit = row["unit"]
                                txn.balance_after = movement["balance_after"]
                                txn.sync_run_id = sync_run.id
                                total_updated += 1
                            else:
                                txn.balance_after = movement["balance_after"]
                                txn.sync_run_id = sync_run.id
                                total_skipped += 1
                    continue
                
                # Check if product_code mapping is found
                if "product_code_col" not in mapping:
                    continue

                valid_rows, sheet_errors = ExcelService.parse_sheet_rows(
                    file_bytes=file_bytes,
                    sheet_name=sheet_name,
                    header_row_index=1,
                    column_mapping=mapping
                )
                
                total_read += len(valid_rows) + len(sheet_errors)
                all_errors.extend(sheet_errors)

                if sheet_type == "SUMMARY":
                    for row in valid_rows:
                        code = row["product_code"]
                        prod = db.query(Product).filter(Product.product_code == code).first()
                        
                        opening = row.get("opening_stock", 0.0)
                        inward = row.get("inward_qty", 0.0)
                        outward = row.get("outward_qty", 0.0)
                        balance = row.get("current_balance", 0.0)
                        
                        # Balance reconciliation check: if balance is 0 but opening/in/out exist, calculate
                        if balance == 0.0 and (opening > 0 or inward > 0 or outward > 0):
                            balance = opening + inward - outward

                        if not prod:
                            prod = Product(
                                product_code=code,
                                name=row.get("product_name", code),
                                category=row.get("category", "General"),
                                unit_of_measure=row.get("unit", "PCS"),
                                opening_stock=opening,
                                total_inward=inward,
                                total_outward=outward,
                                current_balance=balance,
                                min_threshold=row.get("min_threshold", 0.0),
                                unit_cost=row.get("unit_cost"),
                                bin_location=row.get("bin_location"),
                                last_movement_date=row.get("date")
                            )
                            db.add(prod)
                            total_inserted += 1
                        else:
                            # Update existing
                            prod.name = row.get("product_name", prod.name)
                            prod.category = row.get("category", prod.category)
                            prod.unit_of_measure = row.get("unit", prod.unit_of_measure)
                            prod.opening_stock = opening
                            prod.total_inward = inward
                            prod.total_outward = outward
                            prod.current_balance = balance
                            prod.min_threshold = row.get("min_threshold", prod.min_threshold)
                            if row.get("unit_cost") is not None:
                                prod.unit_cost = row.get("unit_cost")
                            if row.get("bin_location"):
                                prod.bin_location = row.get("bin_location")
                            total_updated += 1
                    db.commit()

                elif sheet_type in ["INWARD_REGISTER", "OUTWARD_REGISTER", "LEDGER"]:
                    txn_type = "INWARD" if sheet_type == "INWARD_REGISTER" else ("OUTWARD" if sheet_type == "OUTWARD_REGISTER" else "INWARD")
                    
                    for row in valid_rows:
                        code = row["product_code"]
                        prod = db.query(Product).filter(Product.product_code == code).first()
                        if not prod:
                            # Auto-create product stub if it appeared first in movement sheet
                            prod = Product(
                                product_code=code,
                                name=row.get("product_name", code),
                                category=row.get("category", "General"),
                                unit_of_measure=row.get("unit", "PCS"),
                                current_balance=0.0
                            )
                            db.add(prod)
                            db.commit()
                            db.refresh(prod)
                            total_inserted += 1

                        qty = row.get("inward_qty") if txn_type == "INWARD" else row.get("outward_qty", 0.0)
                        if qty == 0.0:
                            qty = row.get("current_balance", 0.0) # In case qty was in standard qty col
                            
                        date_val = row.get("date", datetime.now())
                        date_str = date_val.strftime("%Y-%m-%d")
                        ref = row.get("reference")

                        # Deduplication check
                        dedup_hash = SyncService.generate_transaction_hash(
                            sheet_name=sheet_name,
                            row_index=row["row_index"],
                            date_str=date_str,
                            product_code=code,
                            txn_type=txn_type,
                            quantity=qty,
                            reference=ref
                        )

                        existing_txn = db.query(StockTransaction).filter(StockTransaction.dedup_hash == dedup_hash).first()
                        if existing_txn:
                            total_skipped += 1
                            continue

                        # Insert new transaction
                        prior_balance = prod.current_balance
                        if txn_type == "INWARD":
                            new_balance = prior_balance + qty
                        else:
                            new_balance = max(0.0, prior_balance - qty)

                        txn = StockTransaction(
                            product_id=prod.id,
                            transaction_date=date_val,
                            transaction_id_source=ref,
                            transaction_type=txn_type,
                            quantity=qty,
                            unit=row.get("unit", prod.unit_of_measure),
                            supplier_or_recipient=row.get("party"),
                            reference_no=ref,
                            remarks=row.get("remarks"),
                            source_sheet=sheet_name,
                            balance_after=new_balance,
                            dedup_hash=dedup_hash,
                            sync_run_id=sync_run.id
                        )
                        db.add(txn)
                        total_inserted += 1

                        # Update product running totals and balance
                        if txn_type == "INWARD":
                            prod.total_inward += qty
                            prod.current_balance = new_balance
                        else:
                            prod.total_outward += qty
                            prod.current_balance = new_balance
                            
                        if not prod.last_movement_date or date_val > prod.last_movement_date:
                            prod.last_movement_date = date_val

                    db.commit()

            if has_daily_register:
                previous_daily_transactions = db.query(StockTransaction).filter(
                    StockTransaction.transaction_id_source.like(f"DAILY:{daily_source_id}:%")
                ).all()
                for txn in previous_daily_transactions:
                    if txn.dedup_hash not in expected_daily_hashes:
                        db.delete(txn)
                        total_updated += 1

            if total_read == 0:
                all_errors.append({
                    "reason": "No inventory rows were imported. Check that the workbook headers and product rows are recognized."
                })

            # Record final status
            sync_run.status = (
                "FAILED" if total_read == 0
                else "SUCCESS" if len(all_errors) == 0
                else "PARTIAL"
            )
            sync_run.rows_read = total_read
            sync_run.rows_inserted = total_inserted
            sync_run.rows_updated = total_updated
            sync_run.rows_skipped = total_skipped
            sync_run.error_log = json.dumps(all_errors[:50]) if all_errors else None
            sync_run.completed_at = datetime.now(timezone.utc)
            db.commit()

            # Record audit log
            audit = AuditLog(
                user_id=triggered_by_user_id,
                action="EXCEL_SYNC",
                resource_type="WORKBOOK",
                resource_id=file_name,
                details=f"Read {total_read} rows: {total_inserted} inserted, {total_updated} updated, {total_skipped} skipped, {len(all_errors)} errors."
            )
            db.add(audit)
            db.commit()

            return {
                "sync_run_id": sync_run.id,
                "status": sync_run.status,
                "file_name": file_name,
                "file_hash": file_hash,
                "rows_read": total_read,
                "rows_inserted": total_inserted,
                "rows_updated": total_updated,
                "rows_skipped": total_skipped,
                "errors_count": len(all_errors),
                "errors_sample": all_errors[:10]
            }

        except Exception as e:
            db.rollback()
            sync_run.status = "FAILED"
            sync_run.error_log = json.dumps({"fatal_error": str(e)})
            sync_run.completed_at = datetime.now(timezone.utc)
            db.commit()
            raise

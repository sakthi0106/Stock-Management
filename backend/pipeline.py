import re
import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple, Set
import database
from spreadsheet_reader import UniversalSpreadsheetReader
from intelligence_engine import IntelligenceEngine

logger = logging.getLogger(__name__)

FORBIDDEN_KEYWORDS = ['amount', 'total cost', 'total price', 'closing value', 'total value', 'closing stk val', 'amount (rs)']
SPECIAL_STRINGS = {'N/A', '-', 'NA', 'N.A.', 'nil', 'none', 'null'}


class UnifiedDataPipeline:
    """End-to-End Dynamic Data Pipeline:
    Spreadsheet Source -> Dynamic Extraction -> Dynamic Schema Detection -> Data Validation -> Operational PostgreSQL/SQLite DB.
    
    Powers Dashboard, Inventory Master, and Stock Movements simultaneously from validated spreadsheet data.
    """

    def __init__(self, intelligence_engine: Optional[IntelligenceEngine] = None):
        self.engine = intelligence_engine or IntelligenceEngine()

    @staticmethod
    def is_amount_field(field_name: str) -> bool:
        fn = str(field_name).strip().lower()
        return any(k in fn for k in FORBIDDEN_KEYWORDS)

    @staticmethod
    def parse_number_or_preserve(val: Any) -> Any:
        if val is None:
            return None
        val_str = str(val).strip()
        if not val_str:
            return None
        if val_str in SPECIAL_STRINGS:
            return val_str
        cleaned = re.sub(r'[,\$ ]', '', val_str).replace('₹', '').replace('Rs.', '').replace('Rs', '')
        try:
            f = float(cleaned)
            if f.is_integer():
                return int(f)
            return f
        except ValueError:
            return val_str

    @staticmethod
    def parse_date_string(val: Any) -> Optional[str]:
        if val is None:
            return None
        s = str(val).strip()
        if not s or s.upper() in SPECIAL_STRINGS:
            return None
        # Matches YYYY-MM-DD
        m1 = re.match(r'^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})', s)
        if m1:
            y, m, d = m1.groups()
            return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
        # Matches DD-MM-YYYY
        m2 = re.match(r'^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})', s)
        if m2:
            d, m, y = m2.groups()
            return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
        return None

    def process_and_persist(
        self,
        source_id: str,
        raw_sheets_dict: Dict[str, List[List[Any]]],
        fingerprint: str = "",
        period: str = ""
    ) -> Dict[str, Any]:
        """Atomically processes spreadsheet data, runs dynamic schema detection,
        and synchronizes dynamic_records, inventory_records, and stock_movements.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        database.cleanup_deleted_worksheets(source_id, set(raw_sheets_dict.keys()))

        total_worksheets = len(raw_sheets_dict)
        total_dynamic_records = 0
        all_inventory_records: List[Dict[str, Any]] = []
        all_stock_movements: List[Dict[str, Any]] = []

        for sname, s_values in raw_sheets_dict.items():
            if not s_values:
                continue

            header_rows, headers, data_start_row = UniversalSpreadsheetReader.detect_header_rows(s_values)
            profile = self.engine.profile_worksheet(
                sheet_name=sname,
                values=s_values,
                header_rows=header_rows,
                headers=headers,
                data_start_row=data_start_row
            )

            # Persist worksheet analysis & dynamic columns
            database.save_worksheet_analysis(source_id, profile)

            data_rows = s_values[data_start_row - 1:] if len(s_values) >= data_start_row else []
            database.save_dynamic_records(source_id, sname, headers, data_rows)
            total_dynamic_records += len(data_rows)

            # Build semantic role lookup
            role_to_col: Dict[str, str] = {}
            col_to_role: Dict[str, str] = {}
            date_columns: List[Tuple[int, str]] = []

            for col in profile.get("columns", []):
                col_name = col.get("original_name", "")
                role = col.get("inferred_role", "unknown")
                col_to_role[col_name] = role
                if role != "unknown" and role not in role_to_col:
                    role_to_col[role] = col_name
                if role == "date" or col.get("data_type") == "date":
                    date_columns.append((col.get("column_index", 0), col_name))

            # Transform raw records into operational inventory & movement records
            inv_items, mov_items = self._transform_worksheet_records(
                source_id=source_id,
                sheet_name=sname,
                headers=headers,
                data_rows=data_rows,
                role_to_col=role_to_col,
                col_to_role=col_to_role,
                date_columns=date_columns,
                period=period,
                now_iso=now_iso
            )

            all_inventory_records.extend(inv_items)
            all_stock_movements.extend(mov_items)

        # Atomically replace inventory_records and stock_movements
        database.replace_source_snapshot(
            source_id=source_id,
            period=period,
            products=all_inventory_records,
            movements=all_stock_movements,
            fingerprint=fingerprint
        )

        database.update_source_intelligence_status(
            source_id,
            status="completed",
            total_sheets=total_worksheets,
            total_records=total_dynamic_records
        )

        return {
            "source_id": source_id,
            "total_sheets": total_worksheets,
            "total_dynamic_records": total_dynamic_records,
            "total_inventory_records": len(all_inventory_records),
            "total_stock_movements": len(all_stock_movements),
            "fingerprint": fingerprint
        }

    def _transform_worksheet_records(
        self,
        source_id: str,
        sheet_name: str,
        headers: List[str],
        data_rows: List[List[Any]],
        role_to_col: Dict[str, str],
        col_to_role: Dict[str, str],
        date_columns: List[Tuple[int, str]],
        period: str,
        now_iso: str
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Convert dynamic records into operational inventory records and stock movements."""
        inventory_records = []
        stock_movements = []

        for row_idx, r in enumerate(data_rows, start=1):
            if not r or not any(str(c).strip() for c in r):
                continue

            raw_dict = {}
            for c_idx, h in enumerate(headers):
                val = r[c_idx] if c_idx < len(r) else ""
                raw_dict[h] = val

            # Semantic values
            part_no = str(raw_dict.get(role_to_col.get("product_id", ""), "")).strip()
            desc = str(raw_dict.get(role_to_col.get("description", ""), "")).strip()
            cat = str(raw_dict.get(role_to_col.get("category", ""), "")).strip() or sheet_name
            uom = str(raw_dict.get(role_to_col.get("uom", ""), "")).strip() or "NOS"
            unit_price_raw = raw_dict.get(role_to_col.get("unit_price", ""), "NA")
            opening_raw = raw_dict.get(role_to_col.get("opening_stock", ""), 0)
            closing_raw = raw_dict.get(role_to_col.get("closing_stock", ""), None)

            # Skip header repeats, totals or blank rows
            if not part_no and not desc:
                continue
            if part_no.upper() in ["TOTAL", "SUBTOTAL", "GRAND TOTAL"]:
                continue

            unit_price = self.parse_number_or_preserve(unit_price_raw) or "NA"
            opening_stock = self.parse_number_or_preserve(opening_raw) or 0
            current_stock = self.parse_number_or_preserve(closing_raw) if closing_raw is not None else opening_stock

            min_level = 10.0
            status = "In Stock"
            if isinstance(current_stock, (int, float)):
                if current_stock <= 0:
                    status = "Out of Stock"
                elif current_stock <= min_level:
                    status = "Low Stock"
            elif str(current_stock).strip().upper() in SPECIAL_STRINGS:
                status = "Unknown"

            # Dynamic extra fields: preserve every non-amount column
            extra_fields = {}
            for k, v in raw_dict.items():
                if not self.is_amount_field(k):
                    extra_fields[k] = self.parse_number_or_preserve(v)

            p_id = part_no if part_no and part_no not in SPECIAL_STRINGS else f"{sheet_name}_R{row_idx}"

            inv_item = {
                "source_id": source_id,
                "source_sheet": sheet_name,
                "source_row": row_idx,
                "product_id": p_id,
                "part_no": part_no or f"ITEM-{row_idx}",
                "description": desc or part_no or f"Product {row_idx}",
                "category": cat,
                "uom": uom,
                "unit_price": unit_price,
                "opening_stock": opening_stock,
                "current_stock": current_stock,
                "latest_date": now_iso[:10],
                "min_level": min_level,
                "stock_status": status,
                "period": period,
                "extra_fields": extra_fields,
                "validation_flags": []
            }
            inventory_records.append(inv_item)

            # Synthesize Stock Movements if valid IN / OUT or date transactions exist
            in_qty_raw = raw_dict.get(role_to_col.get("in_qty", ""), 0)
            out_qty_raw = raw_dict.get(role_to_col.get("out_qty", ""), 0)

            in_val = self.parse_number_or_preserve(in_qty_raw)
            out_val = self.parse_number_or_preserve(out_qty_raw)

            in_float = float(in_val) if isinstance(in_val, (int, float)) else 0.0
            out_float = float(out_val) if isinstance(out_val, (int, float)) else 0.0

            if in_float > 0 or out_float > 0:
                mov_type = "IN" if in_float > 0 and out_float == 0 else "OUT" if out_float > 0 and in_float == 0 else "IN/OUT"
                net_qty = in_float if in_float > 0 else out_float
                mov_id = f"{source_id}_{sheet_name}_{row_idx}_TXN"

                stock_movements.append({
                    "movement_id": mov_id,
                    "source_id": source_id,
                    "source_sheet": sheet_name,
                    "source_row": row_idx,
                    "date": now_iso[:10],
                    "product_id": p_id,
                    "part_no": part_no,
                    "description": desc or part_no,
                    "category": cat,
                    "movement_type": mov_type,
                    "qty": net_qty,
                    "uom": uom,
                    "opening_stock": float(opening_stock) if isinstance(opening_stock, (int, float)) else 0.0,
                    "in_qty": in_float,
                    "out_qty": out_float,
                    "closing_stock": float(current_stock) if isinstance(current_stock, (int, float)) else 0.0,
                    "period": period,
                    "reference_no": "",
                    "party_name": "",
                    "remarks": f"Derived from {sheet_name} daily log",
                    "validation_flags": []
                })

        return inventory_records, stock_movements
